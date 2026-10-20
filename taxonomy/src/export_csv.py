#!/usr/bin/env python3
"""
CSV exporter
Writes output/arxiv-papers-tagged.csv: the input CSV with Claude's summary and tags added as extra columns,
so the tags can be sorted and filtered in a spreadsheet.

Basic usage (from the taxonomy folder):
    uv run python src/export_csv.py
Added columns, after all the input columns:
    summary               Claude's one- or two-sentence summary
    <facet> (one each)    that facet's tags, separated by "; " (empty if none)
    new_agenda            the proposed new agenda, when no 2025 agenda fits
    tags                  every tag from every facet, separated by "; "
Papers that haven't been tagged yet keep their row, with the added columns left empty.
"""

import argparse
from pathlib import Path

import pandas as pd
import yaml

from tag_papers import DEFAULT_INPUT, DEFAULT_OUTPUT as DEFAULT_TAGS, FACETS_PATH
from build_site import load_tags

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = ROOT / "output" / "arxiv-papers-tagged.csv"
SEPARATOR = "; "


def tag_columns(facet_config: dict) -> list[str]:
    """Tag columns in prompt order; the primary/secondary split of the contribution facet is kept."""
    columns = []
    for facet in facet_config["facets"]:
        columns += [f"{facet['id']}_primary", f"{facet['id']}_secondary"] if facet.get("primary") else [facet["id"]]
    return columns + ["agenda_2025"]


def main():
    parser = argparse.ArgumentParser(description="Add Claude's tags to the papers CSV as extra columns")
    parser.add_argument("--input", default=DEFAULT_INPUT, type=Path, help=f"Papers CSV (default: {DEFAULT_INPUT})")
    parser.add_argument("--tags", default=DEFAULT_TAGS, type=Path, help=f"Tags JSONL (default: {DEFAULT_TAGS})")
    parser.add_argument("--output", default=DEFAULT_CSV, type=Path, help=f"Tagged CSV (default: {DEFAULT_CSV})")
    args = parser.parse_args()

    facet_config = yaml.safe_load(FACETS_PATH.read_text())
    papers = pd.read_csv(args.input, dtype={"arxiv_id": str})
    tags = load_tags(args.tags)
    columns = tag_columns(facet_config)

    def added(arxiv_id: str) -> dict:
        record = tags.get(arxiv_id)
        if record is None:
            return {"summary": "", **{c: "" for c in columns}, "new_agenda": "", "tags": ""}
        values = {c: record[c] if isinstance(record[c], list) else [record[c]] for c in columns}
        every_tag = list(dict.fromkeys(t for c in columns for t in values[c]))  # dedupe, keep order
        return {"summary": record["summary"], **{c: SEPARATOR.join(v) for c, v in values.items()},
                "new_agenda": record["new_agenda"], "tags": SEPARATOR.join(every_tag)}

    tagged = pd.concat([papers, pd.DataFrame([added(i) for i in papers["arxiv_id"]])], axis=1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tagged.to_csv(args.output, index=False)
    n_untagged = sum(i not in tags for i in papers["arxiv_id"])
    print(f"Wrote {args.output} ({len(tagged)} papers, {n_untagged} untagged)")


if __name__ == "__main__":
    main()
