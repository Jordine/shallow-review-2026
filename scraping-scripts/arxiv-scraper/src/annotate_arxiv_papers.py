#!/usr/bin/env python3
"""
ArXiv Paper Annotation Script
Uses Claude to add tags to the papers kept by the relevance filter.

Basic usage (from the arxiv-scraper folder):
    uv run python src/annotate_arxiv_papers.py
Reads results/2-arxiv-papers-highly-relevant.csv and writes results/3-arxiv-papers-annotated.csv by default.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd
import anthropic
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

Abstract: {abstract}

Categories: {categories}"""


class PaperAnnotation(BaseModel):
    """Structured output for paper annotations."""
    tags: list[str]  # 2-5 tags for the paper's contribution areas


def call_claude_api(paper_info: dict) -> PaperAnnotation | None:
    """
    Call the Claude API with structured output parsing.

    Args:
        paper_info: Dictionary with paper information (title, authors, abstract, categories)

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
        "abstract": row["abstract"],
        "categories": row["categories"],
    })

    if annotation is None:
        log.warning(f"Failed to annotate, leaving it untagged: {row['title'][:60]}")
    else:
        log.info(f"{row['title'][:60]} → {', '.join(annotation.tags)}")

    return annotation


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
    ])


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Add tags to arXiv papers kept by the relevance filter",
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
