#!/usr/bin/env python3
"""
ArXiv Search Script
Searches arXiv month by month for papers matching specified criteria, adds Semantic Scholar citation counts, venues
and author h-indexes, and saves one CSV per month.

Basic usage (from the arxiv-scraper folder):
    uv run python src/scrape_arxiv_papers.py
Writes results/raw/<year>/<month>/arxiv-papers-raw.csv (e.g. results/raw/2026/jan/arxiv-papers-raw.csv) for each
month from January 2026 to the current month. Months already scraped are skipped, so an interrupted run resumes.
"""

import argparse
import time
from pathlib import Path
import arxiv
import pandas as pd
from pydantic import BaseModel
from dotenv import load_dotenv
from terminal import setup_logging, progress_bar
from semantic_scholar import add_semantic_scholar_columns

# Load environment variables from .env file (SEMANTIC_SCHOLAR_API_KEY is optional)
load_dotenv()

# Default configuration
# Default query: papers in the main ML categories matching any keyword below. Keywords were chosen by measuring,
# over 2025, each one's arXiv result count against how many of the arXiv papers linked from the 2025 shallow
# review it matches. On 2025 data: ~720 papers/month (~8.7k/year, out of ~7.4k/month
# in these categories) and 70% of the review's papers. The LLM filter then narrows that to ~1k/year.
# arXiv search notes, learned the hard way:
#   - It stems words, so "jailbreak" also matches "jailbreaks"/"jailbreaking". Don't add plural variants.
#   - Trailing * wildcards are unreliable (interpretab* returns 1% of what "interpretability" does). Avoid them.
#   - Stemming can collide with common words: "scheming" matches "scheme", "monitorability" matches "monitor".
#   - Unquoted hyphenated words are split ("power-seeking" matches power OR seeking), so use spaces.
QUERY_CATEGORIES = ["cs.AI", "cs.LG", "cs.CL", "cs.CR"]
QUERY_TERM_GROUPS = {
    "general": [
        "ai safety", "ai alignment", "ai risk", "existential risk", "catastrophic risk", "frontier ai",
        "frontier model", "superintelligence", "alignment research",
    ],
    "misalignment": [
        "emergent misalignment", "alignment faking", "deceptive alignment", "goal misgeneralization",
        "specification gaming", "reward hacking", "scheming propensity", "sandbagging", "power seeking",
        "self preservation", "self replication", "sycophancy", "honesty", "deception", "deceptive",
        "model organism", "inoculation", "evaluation awareness",
    ],
    "oversight and control": [
        "ai control", "scalable oversight", "cot monitoring", "chain of thought monitoring", "alignment auditing",
        "steganography",
    ],
    "interpretability": [
        "mechanistic interpretability", "sparse autoencoder", "transcoders", "monosemanticity", "activation steering",
        "steering vector", "representation engineering", "logit lens", "linear probe", "activation probes",
        "activation patching",
    ],
    "misuse and jailbreaks": [
        "jailbreak", "red teaming", "red team", "refusal", "prompt injection", "unlearning", "dangerous capabilities",
        "dual use", "biosecurity",
    ],
    # Broader terms: lower share of safety papers, but they fill gaps the specific terms miss
    "broad": [
        "oversight", "persona", "guardrail", "RLHF", "backdoor", "safeguards", "situational awareness",
        "misalignment", "harmful", "toxicity", "superposition", "weak to strong", "collusion", "unfaithful",
        "value alignment",
    ],
}
QUERY_TERMS = [term for group in QUERY_TERM_GROUPS.values() for term in group]


def any_term(terms: list[str]) -> str:
    """OR together search terms across all fields, quoting multi-word phrases."""
    return "(" + " OR ".join(f'all:"{t}"' if " " in t else f"all:{t}" for t in terms) + ")"


CATEGORY_QUERY = "(" + " OR ".join(f"cat:{c}" for c in QUERY_CATEGORIES) + ")"
DEFAULT_QUERY = f"{CATEGORY_QUERY} AND {any_term(QUERY_TERMS)}"
# arXiv times out (HTTP 500) fetching results for the full query, so the default search runs one query per group
GROUP_QUERIES = {group: f"{CATEGORY_QUERY} AND {any_term(terms)}" for group, terms in QUERY_TERM_GROUPS.items()}
DEFAULT_MAX_RESULTS = 5_000  # Safety cap per month; the default query matches ~720 papers a month
DEFAULT_START_MONTH = "2026-01"
DEFAULT_OUTPUT_DIR = "results/raw"
MONTH_FILENAME = "arxiv-papers-raw.csv"
# arXiv papers can take a couple of days to appear in search; a month saved sooner than this after it ended is re-scraped
MONTH_COMPLETE_AFTER = pd.Timedelta(days=3)
DEFAULT_PAGE_SIZE = 500
DEFAULT_DELAY_SECONDS = 3.0
DEFAULT_RETRIES = 5

# Setup logging
log = setup_logging("arxiv-search")


class ArxivPaper(BaseModel):
    """One arXiv search result, flattened for CSV output."""
    title: str
    authors: str  # comma-separated
    published: str  # YYYY-MM-DD
    updated: str  # YYYY-MM-DD
    abstract: str  # arXiv API calls this "summary"; newlines collapsed
    primary_category: str
    categories: str  # comma-separated
    arxiv_id: str
    pdf_url: str | None
    doi: str
    comment: str  # author comments, often venue acceptance or page count; newlines collapsed
    journal_ref: str


def search_arxiv(
    query: str,
    limit: int = 10_000,
    page_size: int = 500,
    delay_seconds: float = 3.0,
    retries: int = 5,
    sort_by: arxiv.SortCriterion = arxiv.SortCriterion.SubmittedDate,
    sort_order: arxiv.SortOrder = arxiv.SortOrder.Descending,
) -> list[ArxivPaper]:
    """
    Robust arXiv fetcher that:
      - Uses Client.results(search, offset=...) (correct for v2 API)
      - Recovers from UnexpectedEmptyPageError / HTTPError by resuming at the current offset
      - De-dups by arXiv ID
    Returns: list[ArxivPaper]
    """
    client = arxiv.Client(
        page_size=page_size,
        delay_seconds=delay_seconds,
        num_retries=retries,
    )

    search = arxiv.Search(
        query=query,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    results, seen = [], set()
    offset = 0
    consecutive_failures = 0
    backoff = delay_seconds

    def add_result(r):
        arxiv_id = r.entry_id.split("/")[-1]
        if arxiv_id in seen:
            return False
        seen.add(arxiv_id)
        results.append(ArxivPaper(
            title=r.title,
            authors=", ".join(a.name for a in r.authors),
            published=r.published.strftime("%Y-%m-%d"),
            updated=r.updated.strftime("%Y-%m-%d"),
            abstract=(r.summary or "").replace("\n", " ").strip(),
            primary_category=r.primary_category,
            categories=", ".join(r.categories or []),
            arxiv_id=arxiv_id,
            pdf_url=r.pdf_url,
            doi=r.doi or "N/A",
            comment=(r.comment or "N/A").replace("\n", " ").strip(),
            journal_ref=r.journal_ref or "N/A",
        ))
        return True

    log.info(f"Starting fetch (limit={limit}, page_size={page_size})")

    with progress_bar() as progress:
        task = progress.add_task("Fetching papers", total=limit)
        while len(results) < limit:
            try:
                # Stream from current offset to the end (or until we hit our limit)
                for r in client.results(search, offset=offset):
                    if add_result(r):
                        progress.advance(task)
                    offset += 1  # offset is count of yielded records so far
                    if len(results) >= limit:
                        break

                # If we got here without exceptions, we reached the end cleanly.
                log.info("Reached end of result set.")
                break

            except (arxiv.UnexpectedEmptyPageError, arxiv.HTTPError) as e:
                consecutive_failures += 1
                log.warning(f"{type(e).__name__} at offset={offset}. "
                            f"Retrying after {backoff:.1f}s (failure #{consecutive_failures})…")
                time.sleep(backoff)
                # Exponential backoff, capped
                backoff = min(backoff * 1.5, 30.0)
                # Loop will restart generator from the same offset

                # Optional safety: give up after too many consecutive failures
                if consecutive_failures >= 8:
                    log.error("Too many consecutive failures; returning partial results.")
                    break
            else:
                # On success, reset failure counters/backoff
                consecutive_failures = 0
                backoff = delay_seconds

    log.info(f"Done. Collected {len(results)} results.")
    return results


def month_dir(output_dir: Path, month: pd.Period) -> Path:
    """Folder for one month's results, e.g. results/raw/2026/jan."""
    return output_dir / str(month.year) / month.strftime("%b").lower()


def is_complete(path: Path, month: pd.Period) -> bool:
    """Whether a month's CSV exists and was saved after the month had fully ended (so no papers can be missing)."""
    if not path.exists():
        return False
    saved_at = pd.Timestamp(path.stat().st_mtime, unit="s")
    return saved_at > month.end_time + MONTH_COMPLETE_AFTER


def month_query(base_query: str, month: pd.Period) -> str:
    """Restrict a query to papers submitted during one calendar month."""
    return (f"{base_query} AND submittedDate:"
            f"[{month.start_time.strftime('%Y%m%d')}0000 TO {month.end_time.strftime('%Y%m%d')}2359]")


def save_results_to_csv(results: list[ArxivPaper], output_path, matched_groups: dict[str, list[str]] | None = None):
    """
    Save search results with Semantic Scholar metadata to a CSV file, sorted from earliest to latest published date.

    Args:
        results: Papers to save
        output_path: CSV path
        matched_groups: Optional arxiv_id -> names of the query groups that found the paper
    """
    df = pd.DataFrame([paper.model_dump() for paper in results])
    if matched_groups is not None and not df.empty:
        df["matched_groups"] = df["arxiv_id"].map(lambda i: ", ".join(matched_groups[i]))
    # arXiv returns newest first; arxiv_id breaks ties between papers published the same day
    if not df.empty:
        df = df.sort_values(["published", "arxiv_id"]).reset_index(drop=True)
        df = add_semantic_scholar_columns(df)

    # Create results directory if it doesn't exist
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    df.to_csv(output_path, index=False)
    log.info(f"Results saved to {output_path}")
    log.info(f"Total papers saved: {len(df)}")


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Search arXiv for papers and save results to CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default query, January 2026 to the current month (skipping months already scraped)
  python src/scrape_arxiv_papers.py

  # One month only
  python src/scrape_arxiv_papers.py --start-month 2026-03 --end-month 2026-03

  # All of 2025, re-scraping months that already have results
  python src/scrape_arxiv_papers.py --start-month 2025-01 --end-month 2025-12 --overwrite

  # Custom query into a separate folder
  python src/scrape_arxiv_papers.py --query "cat:cs.LG AND all:unlearning" --output-dir results/raw-unlearning
        """
    )
    
    parser.add_argument(
        "--query",
        type=str,
        default=DEFAULT_QUERY,
        help="arXiv search query without a date range; each month's date range is added automatically "
             "(default: QUERY_TERM_GROUPS within QUERY_CATEGORIES, one query per group)"
    )

    parser.add_argument(
        "--start-month",
        type=str,
        default=DEFAULT_START_MONTH,
        help=f"First month to scrape, YYYY-MM (default: {DEFAULT_START_MONTH})"
    )

    parser.add_argument(
        "--end-month",
        type=str,
        help="Last month to scrape, YYYY-MM (default: the current month)"
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-scrape months that already have complete results"
    )

    parser.add_argument(
        "--max-results",
        type=int,
        default=DEFAULT_MAX_RESULTS,
        help=f"Maximum number of results per month (default: {DEFAULT_MAX_RESULTS})"
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Folder for the per-month results (default: {DEFAULT_OUTPUT_DIR})"
    )

    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help=f"Page size for API requests (default: {DEFAULT_PAGE_SIZE})"
    )
    
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY_SECONDS,
        help=f"Delay between requests in seconds (default: {DEFAULT_DELAY_SECONDS})"
    )
    
    return parser.parse_args()


def main():
    """Main execution function."""
    args = parse_arguments()

    if "submittedDate:" in args.query:
        log.error("--query must not include a submittedDate range; use --start-month / --end-month instead.")
        return

    current_month = pd.Timestamp.today().to_period("M")
    end_month = pd.Period(args.end_month, "M") if args.end_month else current_month
    if end_month > current_month:
        log.info(f"Stopping at the current month ({current_month}); later months have no papers yet.")
        end_month = current_month
    months = pd.period_range(pd.Period(args.start_month, "M"), end_month, freq="M")

    # Default: one query per keyword group (the combined query is too slow for arXiv); custom: the query as given
    queries = GROUP_QUERIES if args.query == DEFAULT_QUERY else {"custom": args.query}
    log.info(f"Search query: {args.query}")
    log.info(f"Months: {months[0]} to {months[-1]}, max results per month: {args.max_results}")

    output_dir = Path(args.output_dir)
    scraped = skipped = 0
    for month in months:
        output_path = month_dir(output_dir, month) / MONTH_FILENAME
        if not args.overwrite and is_complete(output_path, month):
            log.info(f"{month}: already scraped ({output_path}), skipping")
            skipped += 1
            continue

        papers: dict[str, ArxivPaper] = {}
        matched_groups: dict[str, list[str]] = {}
        for group, query in queries.items():
            log.info(f"{month}: searching arXiv ({group})...")
            results = search_arxiv(
                query=month_query(query, month),
                limit=args.max_results,
                page_size=args.page_size,
                delay_seconds=args.delay,
                retries=DEFAULT_RETRIES
            )
            if len(results) >= args.max_results:
                log.warning(f"{month} ({group}): hit --max-results ({args.max_results}); some papers may be missing")
            for paper in results:
                papers.setdefault(paper.arxiv_id, paper)
                matched_groups.setdefault(paper.arxiv_id, []).append(group)
        log.info(f"{month}: {len(papers)} unique papers across {len(queries)} queries")
        save_results_to_csv(list(papers.values()), output_path, matched_groups)
        scraped += 1

    log.info(f"Search completed: {scraped} month(s) scraped, {skipped} already done.")


if __name__ == "__main__":
    main()

