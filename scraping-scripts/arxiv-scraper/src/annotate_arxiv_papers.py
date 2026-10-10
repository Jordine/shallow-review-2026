#!/usr/bin/env python3
"""
ArXiv Paper Annotation Script
Uses Claude to add tags to the papers kept by the relevance filter, and Semantic Scholar to add citation counts.

Basic usage (from the arxiv-scraper folder):
    uv run python src/annotate_arxiv_papers.py
Reads results/2-arxiv-papers-highly-relevant.csv and writes results/3-arxiv-papers-annotated.csv by default.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import os
import re
import time
from pathlib import Path
import pandas as pd
import anthropic
import requests
from pydantic import BaseModel
from dotenv import load_dotenv
from terminal import setup_logging, progress_bar, print_summary

# Load environment variables from .env file
load_dotenv()

# Setup logging
log = setup_logging("arxiv-annotate")

# Initialize Claude client (reads ANTHROPIC_API_KEY from the environment / .env)
client = anthropic.Anthropic()

# On a safety-classifier refusal, retry on Anthropic's recommended fallback model
FALLBACK_BETAS = ["server-side-fallback-2026-07-01"]

# Default configuration
DEFAULT_INPUT_FILE = "results/2-arxiv-papers-highly-relevant.csv"
DEFAULT_OUTPUT_FILE = "results/3-arxiv-papers-annotated.csv"
DEFAULT_MODEL = "claude-sonnet-5-5"
BATCH_SIZE = 10  # Papers annotated in parallel per batch

# Semantic Scholar citation lookup (an API key is optional; it raises the rate limit)
SEMANTIC_SCHOLAR_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
SEMANTIC_SCHOLAR_BATCH_SIZE = 500  # Max IDs per batch request
SEMANTIC_SCHOLAR_RETRIES = 5

# Citations per month: papers younger than this count as this old, so a brand-new paper
# with a couple of citations doesn't get an inflated rate
MIN_MONTHS_SINCE_PUBLISHED = 1.0
DAYS_PER_MONTH = 30.44

# System prompt for the LLM
SYSTEM_PROMPT = """You are an expert in technical AI alignment research helping to conduct a shallow review of the field.

Your task is to tag arXiv papers that have already been judged relevant to technical AI alignment.

For each paper, provide 2-5 specific tags categorizing the paper's contribution areas, for example:
- The research area (e.g. mechanistic interpretability, scalable oversight, AI control, reward hacking, jailbreaking, safety evaluations)
- The type of contribution (e.g. new technique, benchmark, empirical finding, theoretical result, case study)

Prefer specific tags over generic ones like "AI safety" or "alignment"."""

USER_PROMPT_TEMPLATE = """Tag this arXiv paper:

Title: {title}

Authors: {authors}

Abstract: {summary}

Categories: {categories}"""


class PaperAnnotation(BaseModel):
    """Structured output for paper annotations."""
    tags: list[str]  # 2-5 tags for the paper's contribution areas


def call_claude_api(paper_info: dict) -> PaperAnnotation | None:
    """
    Call the Claude API with structured output parsing.

    Args:
        paper_info: Dictionary with paper information (title, authors, summary, categories)

    Returns:
        Parsed PaperAnnotation object or None if error
    """
    try:
        user_message = USER_PROMPT_TEMPLATE.format(**paper_info)

        response = client.beta.messages.parse(
            model=DEFAULT_MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            output_format=PaperAnnotation,
            betas=FALLBACK_BETAS,
            fallbacks="default",
        )

        if response.stop_reason == "refusal":
            category = response.stop_details.category if response.stop_details else None
            log.warning(f"Claude declined to annotate this paper (category: {category})")
            return None

        return response.parsed_output

    except anthropic.AuthenticationError:
        raise  # Missing/invalid API key: stop instead of failing every paper
    except Exception as e:
        log.error(f"Error calling Claude API: {e}")
        return None


def fetch_citation_counts(arxiv_ids: list[str]) -> list[int | None]:
    """
    Look up each paper's total citation count on Semantic Scholar.

    Args:
        arxiv_ids: arXiv IDs, with or without a version suffix (e.g. "2610.10301v1")

    Returns:
        Citation counts in the same order as arxiv_ids; None where a paper wasn't found
        or the lookup failed
    """
    headers = {}
    if api_key := os.getenv("SEMANTIC_SCHOLAR_API_KEY"):
        headers["x-api-key"] = api_key

    # Strip the version so citations to every version are counted together
    ids = [f"arXiv:{re.sub(r'v\d+$', '', arxiv_id)}" for arxiv_id in arxiv_ids]
    counts: list[int | None] = []

    for start in range(0, len(ids), SEMANTIC_SCHOLAR_BATCH_SIZE):
        batch = ids[start:start + SEMANTIC_SCHOLAR_BATCH_SIZE]
        papers = None
        backoff = 2.0
        for attempt in range(1, SEMANTIC_SCHOLAR_RETRIES + 1):
            try:
                response = requests.post(
                    SEMANTIC_SCHOLAR_BATCH_URL,
                    params={"fields": "citationCount"},
                    json={"ids": batch},
                    headers=headers,
                    timeout=60,
                )
                # Rate limited or server error: back off and retry
                if response.status_code == 429 or response.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {response.status_code}")
                response.raise_for_status()
                papers = response.json()
                break
            except requests.RequestException as e:
                if attempt == SEMANTIC_SCHOLAR_RETRIES:
                    log.error(f"Semantic Scholar lookup failed for {len(batch)} papers: {e}")
                    break
                log.warning(f"Semantic Scholar request failed ({e}); retrying in {backoff:.0f}s")
                time.sleep(backoff)
                backoff *= 2

        if papers is None:
            counts.extend([None] * len(batch))
        else:
            # Results come back in request order, with null for papers Semantic Scholar doesn't know
            counts.extend(paper["citationCount"] if paper else None for paper in papers)

    return counts


def annotate_paper(row: pd.Series) -> PaperAnnotation | None:
    """
    Annotate a single paper.

    Args:
        row: DataFrame row containing paper information

    Returns:
        Parsed PaperAnnotation object or None if error
    """
    annotation = call_claude_api({
        "title": row["title"],
        "authors": row["authors"],
        "summary": row["summary"],
        "categories": row["categories"],
    })

    if annotation is None:
        log.warning(f"Failed to annotate, leaving it untagged: {row['title'][:60]}")
    else:
        log.info(f"{row['title'][:60]} → {', '.join(annotation.tags)}")

    return annotation


def citations_per_month(citation_counts: pd.Series, published: pd.Series) -> pd.Series:
    """
    Normalize citation counts by paper age: citations divided by months since publication.

    Args:
        citation_counts: Total citations per paper (may contain missing values)
        published: Publication dates as YYYY-MM-DD strings

    Returns:
        Citations per month, rounded to 2 decimal places; missing where the count is missing
    """
    days_since_published = (pd.Timestamp.today().normalize() - pd.to_datetime(published)).dt.days
    months = (days_since_published / DAYS_PER_MONTH).clip(lower=MIN_MONTHS_SINCE_PUBLISHED)
    return (citation_counts.astype("Float64") / months).round(2)


def annotate_papers(input_path: Path, output_path: Path):
    """
    Add annotations to each paper and save the result.

    Args:
        input_path: Path to input CSV file (papers kept by the relevance filter)
        output_path: Path for annotated output CSV
    """
    log.info(f"Reading input file: {input_path}")
    df = pd.read_csv(input_path)
    log.info(f"Found {len(df)} papers to annotate")

    # Citation counts first: one batch request per 500 papers
    log.info("Fetching citation counts from Semantic Scholar...")
    df["citation_count"] = pd.array(fetch_citation_counts(df["arxiv_id"].astype(str).tolist()), dtype="Int64")
    df["citations_per_month"] = citations_per_month(df["citation_count"], df["published"])
    citations_found = df["citation_count"].notna().sum()

    df["tags"] = None
    failed = 0

    # Annotate papers in batches: fire off one API call per paper in parallel, then gather the batch's results
    rows = [row for _, row in df.iterrows()]
    with progress_bar() as progress, ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
        task = progress.add_task("Annotating papers", total=len(df))
        for start in range(0, len(rows), BATCH_SIZE):
            batch = rows[start:start + BATCH_SIZE]
            # map() returns results in input order and re-raises a worker's exception (e.g. a bad API key)
            for row, annotation in zip(batch, executor.map(annotate_paper, batch)):
                if annotation is None:
                    failed += 1
                    continue
                # Convert tags list to comma-separated string for CSV storage
                df.at[row.name, "tags"] = ", ".join(annotation.tags)
            progress.advance(task, len(batch))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    log.info(f"Saved annotated papers to: {output_path}")
    print_summary("Annotation summary", [
        ("Papers annotated", f"{len(df) - failed}/{len(df)}"),
        ("Failed", str(failed)),
        ("Citation counts found", f"{citations_found}/{len(df)}"),
    ])


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Add tags and citation counts to arXiv papers kept by the relevance filter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default files
  python src/annotate_arxiv_papers.py

  # Specify custom input and output files
  python src/annotate_arxiv_papers.py --input my_filtered.csv --output my_annotated.csv

  # Process with custom model
  python src/annotate_arxiv_papers.py --model claude-haiku-5-5
        """
    )

    parser.add_argument(
        "--input",
        type=str,
        default=DEFAULT_INPUT_FILE,
        help=f"Input CSV file with filtered papers (default: {DEFAULT_INPUT_FILE})"
    )

    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_OUTPUT_FILE,
        help=f"Output CSV file for annotated papers (default: {DEFAULT_OUTPUT_FILE})"
    )

    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"Claude model to use (default: {DEFAULT_MODEL})"
    )

    return parser.parse_args()


def main():
    """Main execution function."""
    args = parse_arguments()

    # Set model
    global DEFAULT_MODEL
    DEFAULT_MODEL = args.model

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        log.error(f"Input file not found: {input_path}")
        log.error("Please run src/filter_arxiv_papers.py first.")
        return

    log.info("Starting annotation...")
    annotate_papers(input_path, output_path)
    log.info("Annotation complete!")


if __name__ == "__main__":
    main()
