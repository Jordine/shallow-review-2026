#!/usr/bin/env python3
"""
ArXiv Relevance Filter Script
Uses Claude to rate arXiv papers from 1 to 5 by relevance to technical AI alignment and keeps the ones at or above a
minimum score, month by month.

Basic usage (from the arxiv-scraper folder):
    uv run python src/filter_arxiv_papers.py
For each results/raw/<year>/<month>/arxiv-papers-raw.csv, writes results/filtered/<year>/<month>/ with
arxiv-papers-rated.csv (every paper with its score) and arxiv-papers-filtered.csv (papers rated at least --min-score).
Papers that already have a score are not rated again, so reruns only rate new papers.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import pandas as pd
import anthropic
from pydantic import BaseModel
from typing import Literal
from dotenv import load_dotenv
from terminal import setup_logging, progress_bar, print_summary
from semantic_scholar import DAYS_PER_MONTH
from scrape_arxiv_papers import MONTH_FILENAME as RAW_FILENAME

# Load environment variables from .env file
load_dotenv()

# Setup logging
log = setup_logging("arxiv-filter")

# Initialize Claude client (reads ANTHROPIC_API_KEY from the environment / .env)
client = anthropic.Anthropic()

# Default configuration
DEFAULT_RAW_DIR = "results/raw"
DEFAULT_OUTPUT_DIR = "results/filtered"
RATED_FILENAME = "arxiv-papers-rated.csv"
FILTERED_FILENAME = "arxiv-papers-filtered.csv"
DEFAULT_MODEL = "claude-haiku-5-5"
BATCH_SIZE = 30  # Papers rated in parallel per batch
DEFAULT_MIN_SCORE = 4  # Papers rated at least this are kept

# Columns added by scrape_arxiv_papers.py that the prompt shows the model
REQUIRED_METADATA_COLUMNS = [
    "comment", "journal_ref", "citation_count", "citations_per_month",
    "venue", "max_author_h_index", "max_h_index_author",
]

# System prompt for the LLM
SYSTEM_PROMPT = """You are an expert in technical AI alignment research helping to conduct a 2026 shallow review of the field.

Your task is to analyze arXiv papers and determine their relevance to technical AI alignment work.

We are conducting a survey of the field of AI safety and AI alignment that will be published on LessWrong. Our goal is to find papers that:
- Make novel and interesting contributions to the field of AI safety such as improving AI alignment techniques, advancing the field of interpretability, developing new AI safety techniques, or discovering novel phenomena in models.
- Contributions to an existing taxonomy or vanguard contributions that establish a new one.

We are specifically interested in papers that are in the following categories:

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

Papers that are highly relevant:
- Papers in the taxonomy described
- Papers that are about AI alignment or AI safety but are novel enough to be part of some new taxonomy that is not part of the ones above (e.g. multi-agent safety, model welfare, human-AI coevolution)

Papers I'm not interested in:
- FAT (Fairness, Accountability, and Transparency) AI papers that are not relevant to existential AI safety
- AI safety techniques that are narrowly focused on a specific industry like avoiding mistakes in medical classification
- Generic AI capabilities papers focused on making models more accurate or capable on a specific task. Exceptions: AGI benchmarks that measure broad capabilities progress
- Papers too focused on short-term risks like producing toxic content, bias, or addiction

For each paper, rate its relevance on a score of 1 to 5 where 1 is not relevant and 5 is highly relevant and provide reasoning for your rating.

Besides the abstract, you will see metadata that can adjust your rating by at most one point. Judge relevance from the abstract first; never raise an off-topic paper because of its metadata.
- Comment and venue: acceptance at a main ML venue (NeurIPS, ICML, ICLR) or a released code repository is a positive signal. Affiliations mentioned in the comment (e.g. a frontier lab or safety organisation) are a mild positive.
- Citations: given as citations per month and percentile within this set. Only treat this as informative for papers older than 3 months; a new paper with zero citations is not a negative signal. High citations alone do not make a paper relevant.
- Authors: upweight papers by recognizable AI safety researchers (e.g. Yoshua Bengio, Alex Turner, Stephen Casper, Neel Nanda). Unknown authors are not a negative.
- Top author h-index: the highest h-index among the authors. A high h-index means an established researcher, but not necessarily one in AI safety, and h-indexes for common names may be wrong; treat it as a weak signal.

Examples:
- Paper: "Frontier LLMs strategically comply with training objectives they disagree with to avoid having their values modified"
- Rating: 5
- Reasoning: The paper gives empirical evidence of a novel and important phenomenon, deceptive alignment, in current frontier models. This bears directly on whether alignment training can be trusted and opens new research directions.

- Paper: "A variant of DPO that reduces reward over-optimization on standard preference datasets"
- Rating: 4
- Reasoning: The paper addresses reward hacking in preference learning, a core alignment area, with a solid empirical improvement. However, it is an incremental refinement of an existing method rather than a new technique or finding.

- Paper: "Measuring sycophancy in LLMs giving medical advice when users push back on correct answers"
- Rating: 3
- Reasoning: The paper is framed around a specific domain (medicine), but sycophancy is a general alignment failure mode and the findings may carry over to other settings. It is moderately relevant, not a core contribution.

- Paper: "A lightweight classifier for filtering toxic language from customer service chatbot outputs"
- Rating: 2
- Reasoning: The paper is safety-adjacent but focuses on short-term content moderation for a specific industry application. It offers little insight into alignment or risks from advanced AI.

- Paper: "A new fine-tuning method that improves LLM accuracy on math reasoning benchmarks"
- Rating: 1
- Reasoning: This is pure capabilities research aimed at improving performance on a specific task, with no safety or alignment implications.
"""

USER_PROMPT_TEMPLATE = """Analyze this arXiv paper for relevance to technical AI alignment:

Title: {title}

Authors: {authors}

Abstract: {abstract}

Categories: {categories}

Comment: {comment}

Journal ref: {journal_ref}

Venue: {venue}

Published: {published} ({months_old} months ago)

Citations: {citations}

Top author h-index: {top_author}

Provide a relevance rating."""


class PaperRelevance(BaseModel):
    """Structured output for a paper's relevance rating."""
    reasoning: str  # Brief explanation of the rating, written before the score
    relevance: Literal[1, 2, 3, 4, 5]  # 1 = not relevant, 5 = highly relevant


def call_claude_api(paper_info: dict, response_format: type[BaseModel]) -> PaperRelevance | None:
    """
    Call the Claude API with structured output parsing.

    Args:
        paper_info: Dictionary with the fields in USER_PROMPT_TEMPLATE
        response_format: The Pydantic model class for response parsing

    Returns:
        Parsed PaperRelevance object or None if error
    """
    try:
        # Format the user prompt with the paper information
        user_message = USER_PROMPT_TEMPLATE.format(**paper_info)

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


def format_citations(row: pd.Series) -> str:
    """
    Describe a paper's citations for the prompt: total, per month, and percentile within the input set.

    Args:
        row: DataFrame row with citation_count, citations_per_month and citation_top_percent

    Returns:
        A short description, or "unknown" if Semantic Scholar had no count
    """
    if pd.isna(row["citation_count"]):
        return "unknown"
    return (
        f"{int(row['citation_count'])} total, {row['citations_per_month']:.2f}/month "
        f"(top {int(row['citation_top_percent'])}% of this set)"
    )


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
        "abstract": row["abstract"],
        "categories": row["categories"],
        "comment": row["comment"] if pd.notna(row["comment"]) else "N/A",
        "journal_ref": row["journal_ref"] if pd.notna(row["journal_ref"]) else "N/A",
        "published": row["published"],
        "months_old": f"{row['months_old']:.1f}",
        "citations": format_citations(row),
        "venue": row["venue"] if pd.notna(row["venue"]) else "N/A",
        "top_author": (
            f"{int(row['max_author_h_index'])} ({row['max_h_index_author']})"
            if pd.notna(row["max_author_h_index"]) else "unknown"
        ),
    }

    analysis = call_claude_api(paper_info, PaperRelevance)

    if analysis is None:
        log.warning(f"Failed to rate, skipping: {row['title'][:60]}")
        return {
            "relevance": None,
            "reasoning": "Error during analysis"
        }

    log.info(f"{analysis.relevance}/5: {row['title'][:60]}")

    return {
        "relevance": analysis.relevance,
        "reasoning": analysis.reasoning
    }


def find_months(raw_dir: Path) -> list[tuple[datetime, Path]]:
    """
    Find the scraped months under raw_dir (raw_dir/<year>/<month>/arxiv-papers-raw.csv).

    Returns:
        (first day of month, month folder relative to raw_dir) pairs, earliest first
    """
    months = []
    for path in raw_dir.glob(f"*/*/{RAW_FILENAME}"):
        month_folder = path.parent.relative_to(raw_dir)
        year, month = month_folder.parts
        months.append((datetime.strptime(f"{year} {month}", "%Y %b"), month_folder))
    return sorted(months)


def rate_month(raw_path: Path, out_dir: Path, min_score: int, rerate: bool) -> dict:
    """
    Rate one month's papers and write its rated and filtered CSVs. Scores from a previous run are reused unless
    rerate is set, so only new (or previously failed) papers are sent to Claude.

    Args:
        raw_path: The month's raw CSV
        out_dir: The month's folder under the filtered output directory
        min_score: Lowest relevance score (1-5) to keep
        rerate: Ignore previous scores and rate every paper again

    Returns:
        Counts for the summary table
    """
    df = pd.read_csv(raw_path, dtype={"arxiv_id": str})
    missing = [column for column in REQUIRED_METADATA_COLUMNS if column not in df.columns]
    if missing:
        log.error(f"{raw_path} is missing columns {missing}; re-run src/scrape_arxiv_papers.py to add them.")
        return {"papers": len(df), "rated_now": 0, "failed": len(df), "kept": 0}

    # Prompt context the model can't work out itself: paper age, and where its citation rate ranks in this month
    days_since_published = (pd.Timestamp.today().normalize() - pd.to_datetime(df["published"])).dt.days
    df_context = pd.DataFrame({
        "months_old": days_since_published / DAYS_PER_MONTH,
        "citation_top_percent": (df["citations_per_month"].rank(pct=True, ascending=False) * 100).clip(lower=1).round(),
    })

    # Start from previous scores, if any
    df["relevance"] = pd.array([None] * len(df), dtype="Int64")
    df["reasoning"] = None
    rated_path = out_dir / RATED_FILENAME
    if rated_path.exists() and not rerate:
        previous = pd.read_csv(rated_path, dtype={"arxiv_id": str}).dropna(subset=["relevance"]).set_index("arxiv_id")
        known = df["arxiv_id"].isin(previous.index)
        df.loc[known, "relevance"] = df.loc[known, "arxiv_id"].map(previous["relevance"]).astype("Int64")
        df.loc[known, "reasoning"] = df.loc[known, "arxiv_id"].map(previous["reasoning"])

    # Rate the rest in batches: fire off one API call per paper in parallel, then gather the batch's results
    todo = df.index[df["relevance"].isna()]
    rows = [row for _, row in pd.concat([df, df_context], axis=1).loc[todo].iterrows()]
    if rows:
        with progress_bar() as progress, ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
            task = progress.add_task("Rating papers", total=len(rows))
            for start in range(0, len(rows), BATCH_SIZE):
                batch = rows[start:start + BATCH_SIZE]
                # map() returns results in input order and re-raises a worker's exception (e.g. a bad API key)
                for row, analysis_result in zip(batch, executor.map(rate_paper, batch)):
                    df.at[row.name, "relevance"] = analysis_result["relevance"]
                    df.at[row.name, "reasoning"] = analysis_result["reasoning"]
                progress.advance(task, len(batch))

    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(rated_path, index=False)
    kept_df = df[df["relevance"] >= min_score]
    kept_df.to_csv(out_dir / FILTERED_FILENAME, index=False)
    log.info(f"Saved {len(kept_df)}/{len(df)} papers rated {min_score}+ to {out_dir / FILTERED_FILENAME}")

    return {
        "papers": len(df),
        "rated_now": len(rows),
        "failed": int(df["relevance"].isna().sum()),
        "kept": len(kept_df),
        **{f"score_{score}": int((df["relevance"] == score).sum()) for score in range(1, 6)},
    }


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Filter arXiv papers by relevance to technical AI alignment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Rate every scraped month (only papers without a score yet)
  python src/filter_arxiv_papers.py

  # Only some months
  python src/filter_arxiv_papers.py --start-month 2026-01 --end-month 2026-03

  # Rate everything again from scratch
  python src/filter_arxiv_papers.py --overwrite

  # Process with custom model
  python src/filter_arxiv_papers.py --model claude-sonnet-5-5

  # Keep only papers rated 5
  python src/filter_arxiv_papers.py --min-score 5
        """
    )

    parser.add_argument(
        "--raw-dir",
        type=str,
        default=DEFAULT_RAW_DIR,
        help=f"Folder of per-month raw results from scrape_arxiv_papers.py (default: {DEFAULT_RAW_DIR})"
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Folder for per-month rated and filtered results (default: {DEFAULT_OUTPUT_DIR})"
    )

    parser.add_argument(
        "--start-month",
        type=str,
        help="First month to rate, YYYY-MM (default: earliest scraped month)"
    )

    parser.add_argument(
        "--end-month",
        type=str,
        help="Last month to rate, YYYY-MM (default: latest scraped month)"
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Ignore previous scores and rate every paper again"
    )

    parser.add_argument(
        "--min-score",
        type=int,
        choices=range(1, 6),
        default=DEFAULT_MIN_SCORE,
        help=f"Lowest relevance score (1-5) to keep (default: {DEFAULT_MIN_SCORE})"
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

    raw_dir = Path(args.raw_dir)
    months = find_months(raw_dir)
    if args.start_month:
        months = [(m, folder) for m, folder in months if m >= datetime.strptime(args.start_month, "%Y-%m")]
    if args.end_month:
        months = [(m, folder) for m, folder in months if m <= datetime.strptime(args.end_month, "%Y-%m")]
    if not months:
        log.error(f"No scraped months found in {raw_dir}. Please run src/scrape_arxiv_papers.py first.")
        return

    log.info(f"Rating {len(months)} month(s) with {DEFAULT_MODEL}, keeping papers rated {args.min_score}+")
    summary = []
    for month, folder in months:
        log.info(f"{month:%Y-%m}: rating papers in {raw_dir / folder / RAW_FILENAME}")
        counts = rate_month(raw_dir / folder / RAW_FILENAME, Path(args.output_dir) / folder, args.min_score, args.overwrite)
        summary.append((f"{month:%Y-%m}", counts))

    rows = [
        (month, f"{c['kept']}/{c['papers']} kept ({c['rated_now']} rated now"
                + (f", {c['failed']} failed)" if c["failed"] else ")"))
        for month, c in summary
    ]
    total_kept = sum(c["kept"] for _, c in summary)
    total_papers = sum(c["papers"] for _, c in summary)
    rows.append(("Total", f"{total_kept}/{total_papers} kept ({sum(c['rated_now'] for _, c in summary)} rated now)"))
    print_summary(f"Relevance filter ({args.min_score}+)", rows)


if __name__ == "__main__":
    main()
