#!/usr/bin/env python3
"""
Forum Post Annotation Script
Uses Claude to add tags and a one-sentence summary to the posts kept by the relevance filter,
and adds karma per month since posting.

Basic usage (from the AF-and-LW-scraper folder):
    uv run python src/annotate_forum_posts.py
Reads results/2-lw-posts-highly-relevant.csv and writes results/3-lw-posts-annotated.csv by default
(af- files with --site alignment-forum).
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
log = setup_logging("forum-annotate")

# Initialize Claude client (reads ANTHROPIC_API_KEY from the environment / .env)
client = anthropic.Anthropic()

# On a safety-classifier refusal, retry on Anthropic's recommended fallback model
FALLBACK_BETAS = ["server-side-fallback-2026-07-01"]

# Default configuration
SITE_PREFIXES = {"lesswrong": "lw", "alignment-forum": "af"}
DEFAULT_SITE = "lesswrong"
DEFAULT_MODEL = "claude-sonnet-5-5"
BATCH_SIZE = 10  # Posts annotated in parallel per batch

# Karma per month: posts younger than this count as this old, so a brand-new post
# with a burst of early votes doesn't get an inflated rate
MIN_MONTHS_SINCE_POSTED = 1.0
DAYS_PER_MONTH = 30.44

# System prompt for the LLM
SYSTEM_PROMPT = """You are an expert in technical AI alignment research helping to conduct a shallow review of the field.

Your task is to annotate LessWrong and Alignment Forum posts that have already been judged relevant to technical AI alignment.

For each post, provide:
1. 2-5 specific tags categorizing the post's contribution areas, for example:
   - The research area (e.g. mechanistic interpretability, scalable oversight, AI control, reward hacking, agent foundations, safety evaluations)
   - The type of contribution (e.g. empirical result, conceptual argument, research agenda, critique, technique, benchmark)
   Prefer specific tags over generic ones like "AI safety" or "alignment".
2. A one-sentence summary of the post's main claim or contribution, based only on the information given."""

USER_PROMPT_TEMPLATE = """Annotate this forum post:

Title: {title}

Authors: {authors}

Forum tags: {tags}

Excerpt: {excerpt}"""


class PostAnnotation(BaseModel):
    """Structured output for post annotations."""
    tags: list[str]  # 2-5 tags for the post's contribution areas
    summary: str  # One-sentence summary of the main claim or contribution


def call_claude_api(post_info: dict) -> PostAnnotation | None:
    """
    Call the Claude API with structured output parsing.

    Args:
        post_info: Dictionary with post information (title, authors, tags, excerpt)

    Returns:
        Parsed PostAnnotation object or None if error
    """
    try:
        user_message = USER_PROMPT_TEMPLATE.format(**post_info)

        response = client.beta.messages.parse(
            model=DEFAULT_MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            output_format=PostAnnotation,
            betas=FALLBACK_BETAS,
            fallbacks="default",
        )

        if response.stop_reason == "refusal":
            category = response.stop_details.category if response.stop_details else None
            log.warning(f"Claude declined to annotate this post (category: {category})")
            return None

        return response.parsed_output

    except anthropic.AuthenticationError:
        raise  # Missing/invalid API key: stop instead of failing every post
    except Exception as e:
        log.error(f"Error calling Claude API: {e}")
        return None


def annotate_post(row: pd.Series) -> PostAnnotation | None:
    """
    Annotate a single post.

    Args:
        row: DataFrame row containing post information

    Returns:
        Parsed PostAnnotation object or None if error
    """
    annotation = call_claude_api({
        "title": row["title"],
        "authors": row["authors"],
        "tags": row["tags"],
        "excerpt": row["excerpt"],
    })

    if annotation is None:
        log.warning(f"Failed to annotate, leaving it untagged: {row['title'][:60]}")
    else:
        log.info(f"{row['title'][:60]} → {', '.join(annotation.tags)}")

    return annotation


def karma_per_month(karma: pd.Series, posted: pd.Series) -> pd.Series:
    """
    Normalize karma by post age: karma divided by months since posting.

    Args:
        karma: Karma per post
        posted: Posting dates as YYYY-MM-DD strings

    Returns:
        Karma per month, rounded to 2 decimal places
    """
    days_since_posted = (pd.Timestamp.today().normalize() - pd.to_datetime(posted)).dt.days
    months = (days_since_posted / DAYS_PER_MONTH).clip(lower=MIN_MONTHS_SINCE_POSTED)
    return (karma / months).round(2)


def annotate_posts(input_path: Path, output_path: Path):
    """
    Add annotations to each post and save the result.

    Args:
        input_path: Path to input CSV file (posts kept by the relevance filter)
        output_path: Path for annotated output CSV
    """
    log.info(f"Reading input file: {input_path}")
    df = pd.read_csv(input_path, keep_default_na=False)
    log.info(f"Found {len(df)} posts to annotate")

    df["karma_per_month"] = karma_per_month(df["karma"], df["posted"])
    df["llm_tags"] = None
    df["summary"] = None
    failed = 0

    # Annotate posts in batches: fire off one API call per post in parallel, then gather the batch's results
    rows = [row for _, row in df.iterrows()]
    with progress_bar() as progress, ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
        task = progress.add_task("Annotating posts", total=len(df))
        for start in range(0, len(rows), BATCH_SIZE):
            batch = rows[start:start + BATCH_SIZE]
            # map() returns results in input order and re-raises a worker's exception (e.g. a bad API key)
            for row, annotation in zip(batch, executor.map(annotate_post, batch)):
                if annotation is None:
                    failed += 1
                    continue
                # Convert tags list to comma-separated string for CSV storage
                df.at[row.name, "llm_tags"] = ", ".join(annotation.tags)
                df.at[row.name, "summary"] = annotation.summary
            progress.advance(task, len(batch))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    log.info(f"Saved annotated posts to: {output_path}")
    print_summary("Annotation summary", [
        ("Posts annotated", f"{len(df) - failed}/{len(df)}"),
        ("Failed", str(failed)),
    ])


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Add tags, summaries and karma per month to forum posts kept by the relevance filter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default files (LessWrong)
  python src/annotate_forum_posts.py

  # Alignment Forum files
  python src/annotate_forum_posts.py --site alignment-forum

  # Process with custom model
  python src/annotate_forum_posts.py --model claude-haiku-5-5
        """
    )
    parser.add_argument("--site", choices=list(SITE_PREFIXES), default=DEFAULT_SITE,
                        help=f"Which site's files to use for the default paths (default: {DEFAULT_SITE})")
    parser.add_argument("--input", type=str, default=None,
                        help="Input CSV of filtered posts (default: results/2-<lw|af>-posts-highly-relevant.csv)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output CSV for annotated posts (default: results/3-<lw|af>-posts-annotated.csv)")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
                        help=f"Claude model to use (default: {DEFAULT_MODEL})")
    return parser.parse_args()


def main():
    """Main execution function."""
    args = parse_arguments()

    # Set model
    global DEFAULT_MODEL
    DEFAULT_MODEL = args.model

    prefix = SITE_PREFIXES[args.site]
    input_path = Path(args.input or f"results/2-{prefix}-posts-highly-relevant.csv")
    output_path = Path(args.output or f"results/3-{prefix}-posts-annotated.csv")

    if not input_path.exists():
        log.error(f"Input file not found: {input_path}")
        log.error("Please run src/filter_forum_posts.py first.")
        return

    log.info("Starting annotation...")
    annotate_posts(input_path, output_path)
    log.info("Annotation complete!")


if __name__ == "__main__":
    main()
