#!/usr/bin/env python3
"""
ArXiv Relevance Filter Script
Uses Claude to rate arXiv papers by relevance to technical AI alignment and keeps the highly relevant ones.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd
import anthropic
from pydantic import BaseModel
from typing import Literal
from dotenv import load_dotenv
from terminal import setup_logging, progress_bar, print_summary

# Load environment variables from .env file
load_dotenv()

# Setup logging
log = setup_logging("arxiv-filter")

# Initialize Claude client (reads ANTHROPIC_API_KEY from the environment / .env)
client = anthropic.Anthropic()

# Default configuration
DEFAULT_INPUT_FILE = "results/1-arxiv-papers-raw.csv"
DEFAULT_RATED_OUTPUT = "results/2-arxiv-papers-rated.csv"
DEFAULT_FILTERED_OUTPUT = "results/2-arxiv-papers-highly-relevant.csv"
DEFAULT_MODEL = "claude-haiku-5-5"
BATCH_SIZE = 10  # Papers rated in parallel per batch

# System prompt for the LLM
SYSTEM_PROMPT = """You are an expert in technical AI alignment research helping to conduct a 2025 shallow review of the field.

Your task is to analyze arXiv papers and determine their relevance to technical AI alignment work. We are specifically interested in papers that:

**Core Technical AI Alignment Areas:**
- AI safety and alignment methodologies (RLHF, RLAIF, constitutional AI, etc.)
- Mechanistic interpretability and transparency
- Scalable oversight techniques
- Adversarial robustness and jailbreaking
- Model evaluation and benchmarking for safety
- Reward hacking and specification gaming
- Deceptive alignment and misalignment
- Value alignment and preference learning
- AI control and monitoring
- Red teaming and adversarial testing

**Novel Contributions We're Looking For:**
- New techniques, frameworks, or methodologies
- Empirical findings that advance understanding
- Novel theoretical insights
- Practical tools and benchmarks
- Case studies revealing important failure modes
- Interdisciplinary approaches bringing new perspectives

**What to Deprioritize:**
- Pure capabilities research without safety implications
- Generic ML papers not specifically addressing alignment
- Applications of AI in specific domains (unless they reveal alignment insights)
- Papers that only tangentially mention safety/alignment
- Purely philosophical discussions without technical content

For each paper, rate its relevance as "not relevant", "moderately relevant", or "highly relevant":
- "highly relevant": Core technical alignment work with novel contributions
- "moderately relevant": Related to alignment but peripheral or applied
- "not relevant": Not about AI alignment or safety

Be selective - only rate papers as "highly relevant" if they make meaningful technical contributions to AI alignment."""

USER_PROMPT_TEMPLATE = """Analyze this arXiv paper for relevance to technical AI alignment:

Title: {title}

Authors: {authors}

Abstract: {summary}

Categories: {categories}

Provide a relevance rating."""


class PaperRelevance(BaseModel):
    """Structured output for a paper's relevance rating."""
    relevance: Literal["not relevant", "moderately relevant", "highly relevant"]
    reasoning: str  # Brief explanation of the rating


def call_claude_api(paper_info: dict, response_format: type[BaseModel]) -> PaperRelevance | None:
    """
    Call the Claude API with structured output parsing.

    Args:
        paper_info: Dictionary with paper information (title, authors, summary, categories)
        response_format: The Pydantic model class for response parsing

    Returns:
        Parsed PaperRelevance object or None if error
    """
    try:
        # Format the user prompt with the paper information
        user_message = USER_PROMPT_TEMPLATE.format(
            title=paper_info["title"],
            authors=paper_info["authors"],
            summary=paper_info["summary"],
            categories=paper_info["categories"]
        )

        # No refusal fallback: Claude Haiku 5.5 doesn't support server-side fallbacks
        response = client.messages.parse(
            model=DEFAULT_MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            output_format=response_format,
        )

        if response.stop_reason == "refusal":
            category = response.stop_details.category if response.stop_details else None
            log.warning(f"Claude declined to analyze this paper (category: {category})")
            return None

        # Get the parsed response
        return response.parsed_output

    except anthropic.AuthenticationError:
        raise  # Missing/invalid API key: stop instead of failing every paper
    except Exception as e:
        log.error(f"Error calling Claude API: {e}")
        return None


def rate_paper(row: pd.Series) -> dict:
    """
    Rate a single paper's relevance.

    Args:
        row: DataFrame row containing paper information

    Returns:
        Dictionary with relevance and reasoning
    """
    paper_info = {
        "title": row["title"],
        "authors": row["authors"],
        "summary": row["summary"],
        "categories": row["categories"]
    }

    analysis = call_claude_api(paper_info, PaperRelevance)

    if analysis is None:
        log.warning(f"Failed to rate, skipping: {row['title'][:60]}")
        return {
            "relevance": "not relevant",
            "reasoning": "Error during analysis"
        }

    log.info(f"{analysis.relevance}: {row['title'][:60]}")

    return {
        "relevance": analysis.relevance,
        "reasoning": analysis.reasoning
    }


def process_results(input_path: Path, rated_output: Path, filtered_output: Path):
    """
    Process arXiv results: rate each paper, then filter.

    Args:
        input_path: Path to input CSV file
        rated_output: Path for output CSV with every paper and its rating
        filtered_output: Path for filtered (highly relevant only) output CSV
    """
    # Read input CSV
    log.info(f"Reading input file: {input_path}")
    df = pd.read_csv(input_path)
    log.info(f"Found {len(df)} papers to rate")

    # Initialize new columns
    df["relevance"] = None
    df["reasoning"] = None

    # Rate papers in batches: fire off one API call per paper in parallel, then gather the batch's results
    rows = [row for _, row in df.iterrows()]
    with progress_bar() as progress, ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
        task = progress.add_task("Rating papers", total=len(df))
        for start in range(0, len(rows), BATCH_SIZE):
            batch = rows[start:start + BATCH_SIZE]
            # map() returns results in input order and re-raises a worker's exception (e.g. a bad API key)
            for row, analysis_result in zip(batch, executor.map(rate_paper, batch)):
                df.at[row.name, "relevance"] = analysis_result["relevance"]
                df.at[row.name, "reasoning"] = analysis_result["reasoning"]
            progress.advance(task, len(batch))

    # Save rated results
    rated_output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(rated_output, index=False)
    log.info(f"Saved rated results to: {rated_output}")

    # Filter for highly relevant papers
    highly_relevant_df = df[df["relevance"] == "highly relevant"].copy()
    highly_relevant_df.to_csv(filtered_output, index=False)
    log.info(f"Saved {len(highly_relevant_df)} highly relevant papers to: {filtered_output}")

    # Print summary statistics
    rows = [("Total papers rated", str(len(df)))]
    for relevance in ["highly relevant", "moderately relevant", "not relevant"]:
        count = (df["relevance"] == relevance).sum()
        rows.append((relevance.capitalize(), f"{count} ({count / len(df) * 100:.1f}%)"))
    print_summary("Relevance summary", rows)


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Filter arXiv papers by relevance to technical AI alignment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default files
  python src/filter_arxiv_papers.py

  # Specify custom input and output files
  python src/filter_arxiv_papers.py --input my_results.csv --rated my_rated.csv --filtered my_filtered.csv

  # Process with custom model
  python src/filter_arxiv_papers.py --model claude-sonnet-5-5
        """
    )

    parser.add_argument(
        "--input",
        type=str,
        default=DEFAULT_INPUT_FILE,
        help=f"Input CSV file with raw arXiv results (default: {DEFAULT_INPUT_FILE})"
    )

    parser.add_argument(
        "--rated",
        type=str,
        default=DEFAULT_RATED_OUTPUT,
        help=f"Output CSV file with every paper and its rating (default: {DEFAULT_RATED_OUTPUT})"
    )

    parser.add_argument(
        "--filtered",
        type=str,
        default=DEFAULT_FILTERED_OUTPUT,
        help=f"Output CSV file for highly relevant results (default: {DEFAULT_FILTERED_OUTPUT})"
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

    # Convert paths
    input_path = Path(args.input)
    rated_output = Path(args.rated)
    filtered_output = Path(args.filtered)

    # Check if input file exists
    if not input_path.exists():
        log.error(f"Input file not found: {input_path}")
        log.error("Please run src/scrape_arxiv_papers.py first to generate arXiv results.")
        return

    # Process results
    log.info("Starting relevance rating...")
    process_results(input_path, rated_output, filtered_output)
    log.info("Rating complete!")


if __name__ == "__main__":
    main()
