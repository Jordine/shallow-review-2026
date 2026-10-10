#!/usr/bin/env python3
"""
Create Taxonomy and Editorial from Annotated Forum Posts
Uses Claude to generate a Markdown document with an editorial, a taxonomy, and post listings.

Basic usage (from the AF-and-LW-scraper folder):
    uv run python src/generate_taxonomy_and_editorial.py
Reads results/3-lw-posts-annotated.csv and writes results/4-lw-taxonomy-and-editorial.md by default
(af- files with --site alignment-forum).
"""

import argparse
from pathlib import Path
import pandas as pd
import anthropic
from pydantic import BaseModel
from dotenv import load_dotenv
from terminal import console, setup_logging, print_summary

# Load environment variables from .env file
load_dotenv()

# Setup logging
log = setup_logging("forum-taxonomy-editorial")

# Initialize Claude client (reads ANTHROPIC_API_KEY from the environment / .env)
client = anthropic.Anthropic()

# On a safety-classifier refusal, retry on Anthropic's recommended fallback model
FALLBACK_BETAS = ["server-side-fallback-2026-07-01"]

# Default configuration
SITE_PREFIXES = {"lesswrong": "lw", "alignment-forum": "af"}
SITE_NAMES = {"lesswrong": "LessWrong", "alignment-forum": "Alignment Forum"}
DEFAULT_SITE = "lesswrong"
DEFAULT_MODEL = "claude-sonnet-5-5"

# System prompt for taxonomy generation
TAXONOMY_SYSTEM_PROMPT = """You are an expert in technical AI alignment research creating a taxonomy of recent work.

Your task is to analyze a collection of curated LessWrong and Alignment Forum posts and create:
1. A hierarchical taxonomy that organizes the posts by their main themes and contributions
2. An insightful editorial summarizing the state and progress of AI alignment in 2026

The taxonomy should:
- Group posts into coherent themes/categories
- Use clear, descriptive category names
- Be hierarchical (main categories with subcategories where appropriate)
- Cover all major themes present in the posts
- Be formatted as nested Markdown bullet points

The editorial should:
- Be 100-500 words
- Provide a high-level overview of AI alignment progress in 2026 as seen on the forums
- Highlight key trends, themes, debates, and important developments
- Be engaging and insightful
- Focus on technical advancements and their implications

Base your analysis ONLY on the provided posts."""

TAXONOMY_USER_PROMPT_TEMPLATE = """Based on these curated AI alignment forum posts from 2026, create a taxonomy and editorial.

Posts:
{posts_text}

Generate:
1. A hierarchical taxonomy organizing these posts by themes
2. A 100-500 word editorial on AI alignment progress in 2026"""


class TaxonomyAndEditorial(BaseModel):
    """Structured output for taxonomy and editorial generation."""
    taxonomy: str  # Hierarchical taxonomy as nested Markdown bullet points
    editorial: str  # 100-500 word editorial


def format_posts_for_prompt(df: pd.DataFrame) -> str:
    """
    Format posts into a text representation for the LLM prompt.

    Args:
        df: DataFrame with annotated posts

    Returns:
        Formatted string of all posts
    """
    posts = []
    for idx, row in df.iterrows():
        posts.append(f"""Post {idx + 1}:
Title: {row['title']}
Authors: {row['authors']}
Karma: {row['karma']}
Tags: {row['llm_tags']}
Summary: {row['summary']}
""")
    return "\n\n".join(posts)


def generate_taxonomy_and_editorial(posts_text: str, model: str) -> TaxonomyAndEditorial | None:
    """
    Generate taxonomy and editorial using the Claude API.

    Args:
        posts_text: Formatted string of all posts
        model: Claude model to use

    Returns:
        TaxonomyAndEditorial object or None if error
    """
    try:
        log.info("Generating taxonomy and editorial...")
        user_message = TAXONOMY_USER_PROMPT_TEMPLATE.format(posts_text=posts_text)

        # Stream: the prompt holds every post and the output is long
        with console.status("Waiting for Claude to write the taxonomy and editorial..."), client.beta.messages.stream(
            model=model,
            max_tokens=64000,
            system=TAXONOMY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            output_config={"effort": "high"},
            output_format=TaxonomyAndEditorial,
            betas=FALLBACK_BETAS,
            fallbacks="default",
        ) as stream:
            response = stream.get_final_message()

        if response.stop_reason == "refusal":
            category = response.stop_details.category if response.stop_details else None
            log.error(f"Claude declined to generate the taxonomy (category: {category})")
            return None

        return response.parsed_output

    except Exception as e:
        log.error(f"Error calling Claude API: {e}")
        return None


def create_output_document(df: pd.DataFrame, taxonomy: str, editorial: str,
                           site: str, output_path: Path):
    """
    Create the final Markdown document with posts, taxonomy, and editorial.

    Args:
        df: DataFrame with annotated posts
        taxonomy: Generated taxonomy text
        editorial: Generated editorial text
        site: "lesswrong" or "alignment-forum"
        output_path: Path to save the Markdown file
    """
    lines = [f"# {SITE_NAMES[site]} Taxonomy and Editorial", ""]

    lines += ["## Editorial", "", editorial, ""]
    lines += ["## Taxonomy", "", taxonomy, ""]

    lines += ["## TODO: Posts to Review", ""]
    lines += [f"- [ ] {row['title']}" for _, row in df.iterrows()]
    lines.append("")

    lines += ["## Post Summaries", ""]
    for _, row in df.iterrows():
        lines += [
            f"### {row['title']}",
            "",
            f"- Link: {row['url']}",
            f"- Authors: {row['authors']}",
            f"- Posted: {row['posted']} · Karma: {row['karma']} ({row['karma_per_month']}/month)",
            f"- Tags: {row['llm_tags']}",
            f"- Summary: {row['summary']}",
            "",
        ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"Saved output to: {output_path}")


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate a taxonomy and editorial from annotated forum posts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default files (LessWrong)
  python src/generate_taxonomy_and_editorial.py

  # Alignment Forum files
  python src/generate_taxonomy_and_editorial.py --site alignment-forum

  # Use a different model
  python src/generate_taxonomy_and_editorial.py --model claude-opus-5-5
        """
    )
    parser.add_argument("--site", choices=list(SITE_PREFIXES), default=DEFAULT_SITE,
                        help=f"Which site's files to use for the default paths (default: {DEFAULT_SITE})")
    parser.add_argument("--input", type=str, default=None,
                        help="Input CSV of annotated posts (default: results/3-<lw|af>-posts-annotated.csv)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output Markdown file (default: results/4-<lw|af>-taxonomy-and-editorial.md)")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
                        help=f"Claude model to use (default: {DEFAULT_MODEL})")
    return parser.parse_args()


def main():
    """Main execution function."""
    args = parse_arguments()
    prefix = SITE_PREFIXES[args.site]
    input_csv = Path(args.input or f"results/3-{prefix}-posts-annotated.csv")
    output_md = Path(args.output or f"results/4-{prefix}-taxonomy-and-editorial.md")

    if not input_csv.exists():
        log.error(f"Input CSV file not found: {input_csv}")
        log.error("Please run src/annotate_forum_posts.py first.")
        return

    df = pd.read_csv(input_csv, keep_default_na=False)
    log.info(f"Loaded {len(df)} annotated posts")

    result = generate_taxonomy_and_editorial(format_posts_for_prompt(df), args.model)
    if result is None:
        log.error("Failed to generate taxonomy and editorial")
        return

    create_output_document(df, result.taxonomy, result.editorial, args.site, output_md)
    print_summary("Generation complete", [
        ("Posts processed", str(len(df))),
        ("Editorial length", f"{len(result.editorial.split())} words"),
        ("Output saved to", str(output_md)),
    ])


if __name__ == "__main__":
    main()
