#!/usr/bin/env python3
"""
Site builder
Joins the shortlisted papers with their Claude tags and writes site/data.js, which site/index.html reads.

Basic usage (from the taxonomy folder):
    uv run python src/build_site.py
Then open site/index.html in a browser (no server needed).
"""

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

from tag_papers import (DEFAULT_INPUT, DEFAULT_OUTPUT as DEFAULT_TAGS, FACETS_PATH, TAXONOMY_2025_PATH,
                        SKIP_2025_GROUPS, load_agendas)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SITE_DATA = ROOT / "site" / "data.js"

# Chip colour per facet (names of palettes defined in site/index.html)
COLORS = {
    "evidence": "ink", "contribution": "violet", "paper_type": "blue", "concept": "green", "method": "orange",
    "substrate": "olive", "agenda_2025": "rose", "developer": "outline", "month": "grey",
}
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def load_tags(path: Path) -> dict[str, dict]:
    """Latest tag record per paper (reruns with --overwrite append newer records)."""
    tags = {}
    for line in path.read_text().splitlines():
        record = json.loads(line)
        tags[record["arxiv_id"]] = record
    return tags


def build_facets(facet_config: dict) -> list[dict]:
    facets = [{"id": f["id"], "name": f["name"], "multi": f["multi"], "tags": list(f["tags"]),
               "descriptions": f["tags"], "color": COLORS[f["id"]]} for f in facet_config["facets"]]
    agendas = load_agendas(TAXONOMY_2025_PATH, SKIP_2025_GROUPS)
    facets += [
        {"id": "agenda_2025", "name": "2025 agenda", "multi": True, "tags": [a["name"] for a in agendas],
         "descriptions": {a["name"]: a["description"] for a in agendas}, "color": COLORS["agenda_2025"]},
        {"id": "month", "name": "Month", "multi": False, "tags": [m.capitalize() for m in MONTHS],
         "descriptions": {}, "color": COLORS["month"]},
    ]
    # Keep the site's facet order: what the paper shows, how, on what, where it fits, whose models
    order = ["evidence", "contribution", "paper_type", "concept", "method", "substrate", "agenda_2025", "developer",
             "month"]
    return sorted(facets, key=lambda f: order.index(f["id"]))


def paper_record(row: pd.Series, tags: dict) -> dict:
    def clean(value):
        return None if pd.isna(value) or str(value).strip() == "" else value

    agendas = list(tags["agenda_2025"])
    if tags.get("new_agenda"):
        agendas.append(f"new 2026: {tags['new_agenda'].strip().lower()}")
    paper_tags = {
        "evidence": [tags["evidence"]],
        "contribution": [tags["contribution_primary"]] + [t for t in tags["contribution_secondary"]
                                                          if t != tags["contribution_primary"]],
        "paper_type": [tags["paper_type"]],
        "concept": tags["concept"], "method": tags["method"], "substrate": tags["substrate"],
        "agenda_2025": agendas, "developer": tags["developer"],
        "month": [str(row["month"]).capitalize()],
    }
    citations = clean(row.get("citation_count"))
    return {
        "id": row["arxiv_id"], "title": " ".join(str(row["title"]).split()), "authors": row["authors"],
        "published": row["published"], "url": f"https://arxiv.org/abs/{row['arxiv_id']}",
        "venue": clean(row.get("venue")), "citations": int(citations) if citations is not None else None,
        "summary": tags["summary"], "abstract": " ".join(str(row["abstract"]).split()),
        "shortlist_reason": clean(row.get("shortlist_reason")), "rank": int(row["shortlist_rank"]),
        "tags": paper_tags,
    }


def main():
    parser = argparse.ArgumentParser(description="Build site/data.js from the papers and their tags")
    parser.add_argument("--input", default=DEFAULT_INPUT, type=Path, help=f"Papers CSV (default: {DEFAULT_INPUT})")
    parser.add_argument("--tags", default=DEFAULT_TAGS, type=Path, help=f"Tags JSONL (default: {DEFAULT_TAGS})")
    parser.add_argument("--output", default=DEFAULT_SITE_DATA, type=Path,
                        help=f"Site data file (default: {DEFAULT_SITE_DATA})")
    args = parser.parse_args()

    facet_config = yaml.safe_load(FACETS_PATH.read_text())
    papers = pd.read_csv(args.input, dtype={"arxiv_id": str})
    tags = load_tags(args.tags)
    untagged = papers[~papers["arxiv_id"].isin(tags)]
    if not untagged.empty:
        print(f"Warning: {len(untagged)} papers have no tags yet and are left out; run src/tag_papers.py")

    models = sorted({t["model"] for t in tags.values()})
    data = {
        "meta": {"n_papers": len(papers) - len(untagged), "models": models, "facets_version": facet_config["version"],
                 "built": date.today().isoformat()},
        "facets": build_facets(facet_config),
        "papers": [paper_record(row, tags[row["arxiv_id"]]) for _, row in papers.iterrows()
                   if row["arxiv_id"] in tags],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("window.SR_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n")
    print(f"Wrote {args.output} ({len(data['papers'])} papers)")


if __name__ == "__main__":
    main()
