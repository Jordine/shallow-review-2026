"""
Semantic Scholar lookups for arXiv papers (citations, venue, author h-index), shared by the arXiv scraper scripts.
An API key (SEMANTIC_SCHOLAR_API_KEY in the environment / .env) is optional; it raises the rate limit.
"""

import os
import re
import time
import pandas as pd
import requests
from terminal import setup_logging

log = setup_logging("semantic-scholar")

SEMANTIC_SCHOLAR_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
SEMANTIC_SCHOLAR_BATCH_SIZE = 500  # Max IDs per batch request
SEMANTIC_SCHOLAR_RETRIES = 5
SEMANTIC_SCHOLAR_FIELDS = "citationCount,venue,authors.name,authors.hIndex"

# Citations per month: papers younger than this count as this old, so a brand-new paper
# with a couple of citations doesn't get an inflated rate
MIN_MONTHS_SINCE_PUBLISHED = 1.0
DAYS_PER_MONTH = 30.44


def fetch_paper_metadata(arxiv_ids: list[str]) -> list[dict | None]:
    """
    Look up each paper's citation count, venue and authors' h-indexes on Semantic Scholar.

    Args:
        arxiv_ids: arXiv IDs, with or without a version suffix (e.g. "2610.10301v1")

    Returns:
        Semantic Scholar paper records in the same order as arxiv_ids; None where a paper
        wasn't found or the lookup failed
    """
    headers = {}
    if api_key := os.getenv("SEMANTIC_SCHOLAR_API_KEY"):
        headers["x-api-key"] = api_key

    # Strip the version so citations to every version are counted together
    ids = [f"arXiv:{re.sub(r'v\d+$', '', arxiv_id)}" for arxiv_id in arxiv_ids]
    records: list[dict | None] = []

    for start in range(0, len(ids), SEMANTIC_SCHOLAR_BATCH_SIZE):
        batch = ids[start:start + SEMANTIC_SCHOLAR_BATCH_SIZE]
        papers = None
        backoff = 2.0
        for attempt in range(1, SEMANTIC_SCHOLAR_RETRIES + 1):
            try:
                response = requests.post(
                    SEMANTIC_SCHOLAR_BATCH_URL,
                    params={"fields": SEMANTIC_SCHOLAR_FIELDS},
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

        # Results come back in request order, with null for papers Semantic Scholar doesn't know
        records.extend(papers if papers is not None else [None] * len(batch))

    return records


def top_author(record: dict | None) -> tuple[int | None, str | None]:
    """
    Find the author with the highest h-index on a paper.

    Args:
        record: A Semantic Scholar paper record (or None)

    Returns:
        (h-index, name) of that author, or (None, None) if no author has an h-index
    """
    authors = [a for a in (record or {}).get("authors") or [] if a.get("hIndex") is not None]
    if not authors:
        return None, None
    best = max(authors, key=lambda a: a["hIndex"])
    return best["hIndex"], best["name"]


def venue(record: dict | None) -> str | None:
    """Return a paper's venue, treating arXiv itself (preprint only) as no venue."""
    name = ((record or {}).get("venue") or "").strip()
    return None if name.lower() in ("", "arxiv", "arxiv.org") else name


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


def add_semantic_scholar_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add citation_count, citations_per_month, venue, max_author_h_index and max_h_index_author
    columns to a DataFrame of papers.

    Args:
        df: Papers with arxiv_id and published (YYYY-MM-DD) columns

    Returns:
        The same DataFrame with the Semantic Scholar columns added
    """
    log.info(f"Fetching citations, venues and author h-indexes for {len(df)} papers from Semantic Scholar...")
    records = fetch_paper_metadata(df["arxiv_id"].astype(str).tolist())
    df["citation_count"] = pd.array([r["citationCount"] if r else None for r in records], dtype="Int64")
    df["citations_per_month"] = citations_per_month(df["citation_count"], df["published"])
    df["venue"] = [venue(r) for r in records]
    authors = [top_author(r) for r in records]
    df["max_author_h_index"] = pd.array([h for h, _ in authors], dtype="Int64")
    df["max_h_index_author"] = [name for _, name in authors]
    log.info(f"Papers found on Semantic Scholar: {sum(r is not None for r in records)}/{len(df)}")
    return df
