#!/usr/bin/env python3
"""
Forum Post Relevance Filter Script
Uses Claude to rate forum posts by relevance to technical AI alignment and keeps the highly relevant ones.

Basic usage (from the AF-and-LW-scraper folder):
    uv run python src/filter_forum_posts.py
Reads results/1-lw-posts-raw.csv and writes results/2-lw-posts-rated.csv and
results/2-lw-posts-highly-relevant.csv by default (af- files with --site alignment-forum).
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal
import pandas as pd
import anthropic
from pydantic import BaseModel
from dotenv import load_dotenv
from terminal import setup_logging, progress_bar, print_summary

# Load environment variables from .env file
load_dotenv()

# Setup logging
log = setup_logging("forum-filter")

# Initialize Claude client (reads ANTHROPIC_API_KEY from the environment / .env)
client = anthropic.Anthropic()

# Default configuration
SITE_PREFIXES = {"lesswrong": "lw", "alignment-forum": "af"}
DEFAULT_SITE = "lesswrong"
DEFAULT_MODEL = "claude-haiku-5-5"
BATCH_SIZE = 30  # Posts rated in parallel per batch

# System prompt for the LLM
SYSTEM_PROMPT = """You are an expert in technical AI alignment research helping to conduct a shallow review of the field.

Your task is to analyze posts from LessWrong and the Alignment Forum and determine their relevance to technical AI alignment work. Forum posts are often less formal than papers: research updates, conceptual arguments, agendas and critiques all count. We are specifically interested in posts that:

**Core Technical AI Alignment Areas:**
- AI safety and alignment methodologies (RLHF, RLAIF, constitutional AI, etc.)
- Mechanistic interpretability and transparency
- Scalable oversight techniques
- Adversarial robustness and jailbreaking
- Model evaluation and benchmarking for safety
- Reward hacking and specification gaming
- Deceptive alignment, scheming and misalignment
- Value alignment and preference learning
- AI control and monitoring
- Agent foundations and theoretical alignment
- Research agendas and strategy for technical alignment work

**Contributions We're Looking For:**
- Empirical results, including preliminary or negative results
- New techniques, frameworks, or methodologies
- Conceptual or theoretical arguments that advance understanding of alignment problems
- Research agendas and critiques of existing approaches
- Practical tools and benchmarks

**What to Deprioritize:**
- Posts not about AI (rationality, personal, community, other cause areas)
- AI news, forecasting or opinion pieces without research content
- AI governance and policy without a technical component
- Pure capabilities discussion without safety implications
- Event announcements, job postings, and link roundups

For each post, rate its relevance as "not relevant", "moderately relevant", or "highly relevant":
- "highly relevant": Substantive technical or conceptual alignment work
- "moderately relevant": Related to alignment but peripheral, applied, or light on content
- "not relevant": Not about AI alignment or safety

Be selective - only rate posts as "highly relevant" if they make a meaningful contribution to technical AI alignment."""

USER_PROMPT_TEMPLATE = """Analyze this forum post for relevance to technical AI alignment:

Title: {title}

Authors: {authors}

Forum tags: {tags}

Excerpt: {excerpt}

Provide a relevance rating."""


class PostRelevance(BaseModel):
    """Structured output for a post's relevance rating."""
    relevance: Literal["not relevant", "moderately relevant", "highly relevant"]
    reasoning: str  # Brief explanation of the rating


def call_claude_api(post_info: dict) -> PostRelevance | None:
    """
    Call the Claude API with structured output parsing.

    Args:
        post_info: Dictionary with post information (title, authors, tags, excerpt)

    Returns:
        Parsed PostRelevance object or None if error
    """
    try:
        user_message = USER_PROMPT_TEMPLATE.format(**post_info)

        # No refusal fallback: Claude Haiku 5.5 doesn't support server-side fallbacks
        response = client.messages.parse(
            model=DEFAULT_MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            output_format=PostRelevance,
        )

        if response.stop_reason == "refusal":
            category = response.stop_details.category if response.stop_details else None
            log.warning(f"Claude declined to analyze this post (category: {category})")
            return None

        return response.parsed_output

    except anthropic.AuthenticationError:
        raise  # Missing/invalid API key: stop instead of failing every post
    except Exception as e:
        log.error(f"Error calling Claude API: {e}")
        return None


def rate_post(row: pd.Series) -> dict:
    """
    Rate a single post's relevance.

    Args:
        row: DataFrame row containing post information

    Returns:
        Dictionary with relevance and reasoning
    """
    analysis = call_claude_api({
        "title": row["title"],
        "authors": row["authors"],
        "tags": row["tags"],
        "excerpt": row["excerpt"],
    })

    if analysis is None:
        log.warning(f"Failed to rate, skipping: {row['title'][:60]}")
        return {"relevance": "not relevant", "reasoning": "Error during analysis"}

    log.info(f"{analysis.relevance}: {row['title'][:60]}")
    return {"relevance": analysis.relevance, "reasoning": analysis.reasoning}


def process_posts(input_path: Path, rated_output: Path, filtered_output: Path, limit: int | None = None):
    """
    Rate each post, then filter.

    Args:
        input_path: Path to input CSV file
        rated_output: Path for output CSV with every post and its rating
        filtered_output: Path for filtered (highly relevant only) output CSV
        limit: Only rate the first N posts (for test runs); None rates all
    """
    log.info(f"Reading input file: {input_path}")
    df = pd.read_csv(input_path, keep_default_na=False)
    if limit is not None:
        df = df.head(limit)
        log.info(f"--limit {limit}: rating only the first {len(df)} posts")
    log.info(f"Found {len(df)} posts to rate")

    df["relevance"] = None
    df["reasoning"] = None

    # Rate posts in batches: fire off one API call per post in parallel, then gather the batch's results
    rows = [row for _, row in df.iterrows()]
    with progress_bar() as progress, ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
        task = progress.add_task("Rating posts", total=len(df))
        for start in range(0, len(rows), BATCH_SIZE):
            batch = rows[start:start + BATCH_SIZE]
            # map() returns results in input order and re-raises a worker's exception (e.g. a bad API key)
            for row, result in zip(batch, executor.map(rate_post, batch)):
                df.at[row.name, "relevance"] = result["relevance"]
                df.at[row.name, "reasoning"] = result["reasoning"]
            progress.advance(task, len(batch))

    rated_output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(rated_output, index=False)
    log.info(f"Saved rated posts to: {rated_output}")

    highly_relevant_df = df[df["relevance"] == "highly relevant"].copy()
    highly_relevant_df.to_csv(filtered_output, index=False)
    log.info(f"Saved {len(highly_relevant_df)} highly relevant posts to: {filtered_output}")

    rows = [("Total posts rated", str(len(df)))]
    for relevance in ["highly relevant", "moderately relevant", "not relevant"]:
        count = (df["relevance"] == relevance).sum()
        rows.append((relevance.capitalize(), f"{count} ({count / len(df) * 100:.1f}%)"))
    print_summary("Relevance summary", rows)


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Filter forum posts by relevance to technical AI alignment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default files (LessWrong)
  python src/filter_forum_posts.py

  # Alignment Forum files
  python src/filter_forum_posts.py --site alignment-forum

  # Process with custom model
  python src/filter_forum_posts.py --model claude-sonnet-5-5

  # Test run on the first 100 posts
  python src/filter_forum_posts.py --limit 100
        """
    )
    parser.add_argument("--site", choices=list(SITE_PREFIXES), default=DEFAULT_SITE,
                        help=f"Which site's files to use for the default paths (default: {DEFAULT_SITE})")
    parser.add_argument("--input", type=str, default=None,
                        help="Input CSV of raw posts (default: results/1-<lw|af>-posts-raw.csv)")
    parser.add_argument("--rated", type=str, default=None,
                        help="Output CSV with every post and its rating (default: results/2-<lw|af>-posts-rated.csv)")
    parser.add_argument("--filtered", type=str, default=None,
                        help="Output CSV with highly relevant posts (default: results/2-<lw|af>-posts-highly-relevant.csv)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only rate the first N posts, e.g. for a test run (default: all)")
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
    input_path = Path(args.input or f"results/1-{prefix}-posts-raw.csv")
    rated_output = Path(args.rated or f"results/2-{prefix}-posts-rated.csv")
    filtered_output = Path(args.filtered or f"results/2-{prefix}-posts-highly-relevant.csv")

    if not input_path.exists():
        log.error(f"Input file not found: {input_path}")
        log.error("Please run src/scrape_forum_posts.py first.")
        return

    log.info("Starting relevance rating...")
    process_posts(input_path, rated_output, filtered_output, args.limit)
    log.info("Rating complete!")


if __name__ == "__main__":
    main()
