#!/usr/bin/env python3
"""
Paper tagging script
Asks Claude to tag each shortlisted paper along every facet in facets.yaml, plus the 2025 agendas
(input/taxonomy-2025.yaml).

Basic usage (from the taxonomy folder):
    uv run python src/tag_papers.py
Reads input/arxiv-papers-shortlisted.csv and appends one JSON line per paper to output/tags.jsonl.
Papers already tagged with the current facets version are skipped, so reruns only tag new papers.
"""

import argparse
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

import anthropic
import pandas as pd
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, create_model

ROOT = Path(__file__).resolve().parent.parent

# Load ANTHROPIC_API_KEY from taxonomy/.env
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("tag-papers")

client = anthropic.Anthropic()

# On a safety-classifier refusal, retry on Anthropic's recommended fallback model
FALLBACK_BETAS = ["server-side-fallback-2026-07-01"]

DEFAULT_INPUT = ROOT / "input" / "arxiv-papers-shortlisted.csv"
DEFAULT_OUTPUT = ROOT / "output" / "tags.jsonl"
FACETS_PATH = ROOT / "facets.yaml"
TAXONOMY_2025_PATH = ROOT / "input" / "taxonomy-2025.yaml"
DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_EFFORT = "medium"
MAX_TOKENS = 16000
MAX_PARALLEL = 8

# The 2025 taxonomy's lab group lists organisations, not research agendas
SKIP_2025_GROUPS = {"labs_giant_companies"}


def leaves(nodes: list[dict], path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], dict]]:
    """
    Flatten a taxonomy tree into (ancestor names, leaf) pairs, one per node without children.
    Parent nodes don't get their own pair; they only appear as names in their descendants' paths. E.g. for
    Black-box safety > Model psychology > Emergent misalignment:
        (("Black-box safety (...)", "Model psychology"), {"id": "emergent_misalignment", "name": ..., "description": ...})
    """
    out = []
    for node in nodes:
        if node.get("children"):
            out += leaves(node["children"], path + (node["name"],))
        else:
            out.append((path, node))
    return out


def load_agendas(path: Path, skip: set[str] = frozenset()) -> list[dict]:
    """
    Return [{'name', 'group', 'description'}] for every leaf of a taxonomy file, skipping top-level groups in `skip`.
    - name: the leaf's name. Only leaves are agendas, so these are the values Claude can tag papers with.
    - group: the leaf's top-level category (e.g. "Black-box safety (...)"), used to add headings to the prompt.
      Any middle level is dropped: Emergent misalignment's group is Black-box safety, not Model psychology.
    - description: the leaf's description, shown to Claude in the prompt.
    """
    tree = [n for n in yaml.safe_load(path.read_text())["taxonomy"] if n["id"] not in skip]
    return [{"name": leaf["name"], "group": path_[0] if path_ else "", "description": leaf.get("description", "")}
            for path_, leaf in leaves(tree)]


def enum(values: list[str]):
    return Literal[tuple(values)]


def build_schema(facet_config: dict, agendas_2025: list[dict]) -> type[BaseModel]:
    """Build the structured-output model, with every tag field constrained to its vocabulary."""
    fields = {"summary": (str, Field(description="One or two plain sentences on what the paper does and finds."))}
    for facet in facet_config["facets"]:
        tags = enum(list(facet["tags"]))
        if facet.get("primary"):
            fields[f"{facet['id']}_primary"] = (tags, ...)
            fields[f"{facet['id']}_secondary"] = (list[tags], ...)
        elif facet["multi"]:
            fields[facet["id"]] = (list[tags], ...)
        else:
            fields[facet["id"]] = (tags, ...)
    fields["agenda_2025"] = (list[enum([a["name"] for a in agendas_2025])], ...)
    fields["new_agenda"] = (str, Field(description="Empty unless no 2025 agenda fits; then a short name for the new agenda."))
    return create_model("PaperTags", **fields)


def build_system_prompt(facet_config: dict, agendas_2025: list[dict]) -> str:
    lines = [
        "You are an expert in technical AI alignment research tagging papers for the 2026 Shallow Review of AI safety, "
        "a reader's map of the field published on LessWrong.",
        "",
        "For each paper you receive, assign tags along every facet below. Use only tags from the lists. "
        "Tag what the paper actually does, based on its title and abstract; do not tag a concept just because it is "
        "mentioned in passing. Fewer, accurate tags are better than many loose ones. Multi-tag facets may be empty "
        "when nothing fits.",
        "",
    ]
    for facet in facet_config["facets"]:
        kind = "exactly one tag" if not facet["multi"] else "any number of tags"
        if facet.get("primary"):
            kind = "one primary tag (the paper's main contribution) plus any secondary tags"
        lines += [f"## {facet['name']} ({facet['id']}): {kind}", "", facet["description"], ""]
        lines += [f"- {tag}: {desc}" for tag, desc in facet["tags"].items()]
        lines.append("")

    lines += ["## 2025 agenda (agenda_2025): usually one, at most two", ""]
    lines.append("The research agendas from last year's Shallow Review. Pick the agenda(s) this paper most directly "
                 "advances. If none is a reasonable fit, leave the list empty and name the new agenda in new_agenda "
                 "(2-5 words, general enough that other papers could share it, e.g. 'persona science').")
    group = None
    for a in agendas_2025:
        if a["group"] != group:
            group = a["group"]
            lines += ["", f"### {group}", ""]
        lines.append(f"- {a['name']}: {a['description']}")
    return "\n".join(lines)


def format_paper(row: pd.Series) -> str:
    def value(field):
        return row[field] if pd.notna(row.get(field)) and str(row[field]).strip() else "none"
    return (f"Title: {row['title']}\nAuthors: {row['authors']}\nPublished: {row['published']}\n"
            f"arXiv categories: {value('categories')}\nComment: {value('comment')}\nVenue: {value('venue')}\n\n"
            f"Abstract:\n{row['abstract']}")


def user_message(row: pd.Series) -> str:
    return f"Tag this paper.\n\n{format_paper(row)}"


def tag_paper(row: pd.Series, schema: type[BaseModel], system_prompt: str, model: str, effort: str) -> dict | None:
    try:
        response = client.beta.messages.parse(
            model=model,
            max_tokens=MAX_TOKENS,
            # The prompt is identical for every paper, so cache it
            system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_message(row)}],
            output_config={"effort": effort},
            output_format=schema,
            betas=FALLBACK_BETAS,
            fallbacks="default",
        )
    except anthropic.AuthenticationError:
        raise  # Missing/invalid API key: stop instead of failing every paper
    except anthropic.APIError as e:
        log.error(f"{row['arxiv_id']}: error calling Claude API: {e}")
        return None

    if response.stop_reason == "refusal":
        category = response.stop_details.category if response.stop_details else None
        log.warning(f"{row['arxiv_id']}: Claude declined to tag (category: {category})")
        return None
    if response.stop_reason == "max_tokens":
        log.error(f"{row['arxiv_id']}: response hit max_tokens ({MAX_TOKENS})")
        return None
    return response.parsed_output.model_dump()


def load_done(output_path: Path, facets_version: int) -> set[str]:
    if not output_path.exists():
        return set()
    done = set()
    for line in output_path.read_text().splitlines():
        record = json.loads(line)
        if record.get("facets_version") == facets_version:
            done.add(record["arxiv_id"])
    return done


def parse_arguments():
    parser = argparse.ArgumentParser(description="Tag shortlisted papers along the facets in facets.yaml using Claude")
    parser.add_argument("--input", default=DEFAULT_INPUT, type=Path, help=f"Papers CSV (default: {DEFAULT_INPUT})")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, type=Path, help=f"Tags JSONL (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--limit", type=int, help="Only tag the first N untagged papers (for trying out the prompt)")
    parser.add_argument("--overwrite", action="store_true", help="Retag papers that already have tags")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Claude model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--effort", default=DEFAULT_EFFORT, choices=["low", "medium", "high", "xhigh", "max"],
                        help=f"Effort level (default: {DEFAULT_EFFORT})")
    return parser.parse_args()


def main():
    args = parse_arguments()
    facet_config = yaml.safe_load(FACETS_PATH.read_text())
    agendas_2025 = load_agendas(TAXONOMY_2025_PATH, SKIP_2025_GROUPS)
    schema = build_schema(facet_config, agendas_2025)
    system_prompt = build_system_prompt(facet_config, agendas_2025)

    papers = pd.read_csv(args.input, dtype={"arxiv_id": str})
    done = set() if args.overwrite else load_done(args.output, facet_config["version"])
    todo = papers[~papers["arxiv_id"].isin(done)]
    if args.limit:
        todo = todo.head(args.limit)
    log.info(f"{len(papers)} papers, {len(done)} already tagged, tagging {len(todo)} with {args.model}")
    if todo.empty:
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_lock = threading.Lock()
    failed = []

    def work(row: pd.Series):
        tags = tag_paper(row, schema, system_prompt, args.model, args.effort)
        if tags is None:
            failed.append(row["arxiv_id"])
            return
        record = {"arxiv_id": row["arxiv_id"], "model": args.model, "facets_version": facet_config["version"], **tags}
        with write_lock, args.output.open("a") as f:
            f.write(json.dumps(record) + "\n")
        log.info(f"Tagged {row['arxiv_id']}: {row['title'][:70]}")

    # map() re-raises a worker's exception (e.g. a bad API key)
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as executor:
        list(executor.map(work, (row for _, row in todo.iterrows())))

    log.info(f"Done: {len(todo) - len(failed)} tagged, {len(failed)} failed {failed if failed else ''}")


if __name__ == "__main__":
    main()
