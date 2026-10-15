#!/usr/bin/env python3
"""
Create Taxonomy and Editorial from Curated Links
Generates a structured output with paper listings, taxonomy, and editorial overview.
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
log = setup_logging("arxiv-taxonomy-editorial")

# Initialize Claude client (reads ANTHROPIC_API_KEY from the environment / .env)
client = anthropic.Anthropic()

# On a safety-classifier refusal, retry on Anthropic's recommended fallback model
FALLBACK_BETAS = ["server-side-fallback-2026-07-01"]

# Default configuration
DEFAULT_INPUT_CSV = "results/3-arxiv-papers-annotated.csv"
DEFAULT_OUTPUT_MD = "results/4-arxiv-taxonomy-and-editorial.md"
DEFAULT_MODEL = "claude-sonnet-5-5"
TAXONOMY_MODEL = "claude-sonnet-5-5"  # taxonomy + editorial call only; per-paper tagging uses DEFAULT_MODEL

# System prompt for taxonomy generation
TAXONOMY_SYSTEM_PROMPT = """You are an expert in technical AI alignment research creating a taxonomy of recent work.

Your task is to analyze a collection of curated arXiv papers and create:
1. A hierarchical taxonomy that organizes the papers by their main themes and contributions
2. An insightful editorial summarizing the state and progress of AI alignment in 2026

The taxonomy should:
- Group papers into coherent themes/categories
- Use clear, descriptive category names
- Be hierarchical (main categories with subcategories where appropriate)
- Cover all major themes present in the papers
- Be formatted as nested Markdown bullet points

The editorial should:
- Be 100-500 words
- Provide a high-level overview of AI alignment progress in 2026
- Highlight key trends, themes, and important developments
- Be engaging and insightful
- Focus on technical advancements and their implications

Base your analysis ONLY on the provided papers."""

TAXONOMY_USER_PROMPT_TEMPLATE = """Based on these curated AI alignment papers from 2026, create a taxonomy and editorial.

Papers:
{papers_text}

Generate:
1. A hierarchical taxonomy organizing these papers by themes
2. A 100-500 word editorial on AI alignment progress in 2026"""


class TaxonomyAndEditorial(BaseModel):
    """Structured output for taxonomy and editorial generation."""
    taxonomy: str  # Hierarchical taxonomy as formatted text with bullet points
    editorial: str  # 100-500 word editorial paragraph


class PaperTags(BaseModel):
    """Structured output for individual paper taxonomy tags."""
    tags: list[str]  # List of 2-5 taxonomy tags for this paper


def load_papers(csv_path: Path) -> pd.DataFrame:
    """
    Load the curated papers CSV.
    
    Args:
        csv_path: Path to the CSV file
        
    Returns:
        DataFrame with paper information
    """
    df = pd.read_csv(csv_path)
    log.info(f"Loaded {len(df)} curated papers")
    return df


def format_papers_for_prompt(df: pd.DataFrame) -> str:
    """
    Format papers into a text representation for the LLM prompt.
    
    Args:
        df: DataFrame with paper information
        
    Returns:
        Formatted string of all papers
    """
    papers = []
    for idx, row in df.iterrows():
        paper_text = f"""Paper {idx + 1}:
Title: {row['title']}
Authors: {row['authors']}
Abstract: {row['abstract']}
Existing Agenda: {row.get('agenda', 'N/A')}
"""
        papers.append(paper_text)
    
    return "\n\n".join(papers)


def generate_taxonomy_and_editorial(papers_text: str) -> TaxonomyAndEditorial | None:
    """
    Generate taxonomy and editorial using the Claude API.
    
    Args:
        papers_text: Formatted string of all papers
        
    Returns:
        TaxonomyAndEditorial object or None if error
    """
    try:
        log.info("Generating taxonomy and editorial...")
        
        user_message = TAXONOMY_USER_PROMPT_TEMPLATE.format(
            papers_text=papers_text
        )
        
        # Stream: the prompt holds every paper and the output is long
        with console.status("Waiting for Claude to write the taxonomy and editorial..."), client.beta.messages.stream(
            model=TAXONOMY_MODEL,
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


def generate_paper_tags(paper_title: str, paper_abstract: str, taxonomy: str) -> list[str]:
    """
    Generate taxonomy tags for a single paper based on the overall taxonomy.
    
    Args:
        paper_title: Paper title
        paper_abstract: Paper abstract
        taxonomy: The generated taxonomy
        
    Returns:
        List of taxonomy tags
    """
    system_prompt = f"""You are tagging a paper based on this taxonomy:

{taxonomy}

Provide 2-5 specific tags from the taxonomy that best describe this paper."""
    
    user_prompt = f"""Paper Title: {paper_title}

Abstract: {paper_abstract}

What taxonomy tags apply to this paper?"""
    
    try:
        response = client.beta.messages.parse(
            model=DEFAULT_MODEL,
            max_tokens=16000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            output_config={"effort": "high"},
            output_format=PaperTags,
            betas=FALLBACK_BETAS,
            fallbacks="default",
        )
        
        if response.stop_reason == "refusal":
            log.warning(f"Claude declined to tag: {paper_title[:60]}")
            return []
        
        return response.parsed_output.tags
        
    except Exception as e:
        log.error(f"Error generating tags: {e}")
        return []


def create_output_document(df: pd.DataFrame, taxonomy: str, editorial: str, 
                          output_path: Path):
    """
    Create the final Markdown document with papers, taxonomy, and editorial.
    
    Args:
        df: DataFrame with paper information and tags
        taxonomy: Generated taxonomy text
        editorial: Generated editorial text
        output_path: Path to save the Markdown file
    """
    lines = ["# arXiv Taxonomy and Editorial", ""]
    
    # 1. Add editorial section first
    log.info("Adding editorial...")
    lines.append("## Editorial")
    lines.append("")
    lines.append(editorial)
    lines.append("")
    
    # 2. Add taxonomy section
    log.info("Adding taxonomy...")
    lines.append("## Taxonomy")
    lines.append("")
    lines.append(taxonomy)
    lines.append("")
    
    # 3. Add checklist/todo section
    log.info("Adding checklist...")
    lines.append("## TODO: Papers to Review")
    lines.append("")
    for _, row in df.iterrows():
        title = row['title']
        lines.append(f"- [ ] {title}")
    lines.append("")
    
    # 4. Add paper listings
    log.info("Formatting paper listings...")
    lines.append("## Paper Summaries")
    lines.append("")
    for idx, row in df.iterrows():
        title = row['title']
        pdf_url = row['pdf_url']
        abstract = row['abstract']
        # tags = row.get('taxonomy_tags', 'N/A')  # per-paper tagging disabled
        
        lines.append(f"### {title}")
        lines.append("")
        lines.append(f"- Link: {pdf_url}")
        lines.append(f"- Abstract: {abstract}")
        # lines.append(f"- Taxonomy tags: {tags}")
        lines.append("")  # Blank line between papers
    
    # Write to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"Saved output to: {output_path}")


def process_papers(input_csv: Path, output_md: Path):
    """
    Main processing function.
    
    Args:
        input_csv: Path to input CSV with curated papers
        output_md: Path to output Markdown file
    """
    # Load papers
    df = load_papers(input_csv)
    
    # Format papers for the prompt
    papers_text = format_papers_for_prompt(df)
    
    # Generate taxonomy and editorial
    result = generate_taxonomy_and_editorial(papers_text)
    
    if result is None:
        log.error("Failed to generate taxonomy and editorial")
        return
    
    log.info("Successfully generated taxonomy and editorial")
    log.info(f"Taxonomy length: {len(result.taxonomy)} characters")
    log.info(f"Editorial length: {len(result.editorial.split())} words")
    
    # Per-paper tagging disabled: only the taxonomy and editorial are generated.
    # # Generate individual paper tags based on taxonomy
    # log.info("Generating taxonomy tags for each paper...")
    # taxonomy_tags = []
    # for idx, row in df.iterrows():
    #     log.info(f"Tagging paper {idx + 1}/{len(df)}: {row['title'][:60]}...")
    #     tags = generate_paper_tags(row['title'], row['abstract'], result.taxonomy)
    #     taxonomy_tags.append(", ".join(tags) if tags else "N/A")
    #
    # df['taxonomy_tags'] = taxonomy_tags
    
    # Create output document
    create_output_document(df, result.taxonomy, result.editorial, output_md)
    
    # Print summary
    print_summary("Generation complete", [
        ("Papers processed", str(len(df))),
        ("Output saved to", str(output_md)),
    ])


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate taxonomy and editorial from curated ArXiv papers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default files
  python src/generate_taxonomy_and_editorial.py

  # Specify custom input and output
  python src/generate_taxonomy_and_editorial.py --input my_papers.csv --output my_output.md

  # Use different model
  python src/generate_taxonomy_and_editorial.py --model claude-opus-5-5
        """
    )
    
    parser.add_argument(
        "--input",
        type=str,
        default=DEFAULT_INPUT_CSV,
        help=f"Input CSV file with curated papers (default: {DEFAULT_INPUT_CSV})"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_OUTPUT_MD,
        help=f"Output Markdown file for taxonomy and editorial (default: {DEFAULT_OUTPUT_MD})"
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
    input_csv = Path(args.input)
    output_md = Path(args.output)
    
    # Check if input file exists
    if not input_csv.exists():
        log.error(f"Input CSV file not found: {input_csv}")
        log.error("Please run src/annotate_arxiv_papers.py first.")
        return
    
    # Process papers
    log.info("Starting taxonomy and editorial generation...")
    process_papers(input_csv, output_md)
    log.info("Complete!")


if __name__ == "__main__":
    main()
