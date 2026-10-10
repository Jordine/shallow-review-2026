#!/usr/bin/env python3
"""
Forum Post Scraper
Fetches a year of posts from LessWrong or the Alignment Forum and saves them to CSV.

LessWrong is recommended: every Alignment Forum post is also on LessWrong (with af=True),
so one LessWrong scrape covers both sites. Scraping the Alignment Forum directly is a backup.

Basic usage (from the AF-and-LW-scraper folder):
    uv run python src/scrape_forum_posts.py
Writes to results/1-lw-posts-raw.csv by default (results/1-af-posts-raw.csv with --site alignment-forum).
"""

import argparse
import calendar
import random
import re
import time
from pathlib import Path
import pandas as pd
import requests
from pydantic import BaseModel
from terminal import setup_logging, progress_bar, print_summary

# Setup logging
log = setup_logging("forum-scrape")

# Default configuration
DEFAULT_SITE = "lesswrong"
DEFAULT_YEAR = 2026
DEFAULT_DELAY_SECONDS = 1.0
DEFAULT_MAX_PAGES = 1000
PAGE_SIZE = 50  # Posts per request
MAX_RETRIES = 6

SITES = {
    "lesswrong": {"endpoint": "https://www.lesswrong.com/graphql", "prefix": "lw"},
    "alignment-forum": {"endpoint": "https://www.alignmentforum.org/graphql", "prefix": "af"},
}

POSTS_QUERY = """
query PostsInWindow($after: String!, $before: String!, $limit: Int!, $offset: Int!) {
  posts(input: {terms: {view: "new", limit: $limit, offset: $offset, after: $after, before: $before}}) {
    results {
      _id
      title
      pageUrl
      url
      postedAt
      af
      baseScore
      afBaseScore
      commentCount
      wordCount
      user { displayName }
      coauthors { displayName }
      tags { name }
      contents { plaintextDescription }
    }
  }
}
"""


class ForumPost(BaseModel):
    """One forum post, flattened for CSV output."""
    id: str
    title: str
    url: str  # Post page on the site that was scraped
    link_url: str | None  # External link, for link posts
    authors: str  # comma-separated, main author first
    posted: str  # YYYY-MM-DD
    af: bool  # Also published on the Alignment Forum
    karma: int
    af_karma: int  # Alignment Forum karma (only meaningful when af is True)
    comment_count: int
    word_count: int
    tags: str  # comma-separated forum tags
    excerpt: str  # Start of the post text (the API returns up to ~2,000 characters)


def post_with_retries(endpoint: str, body: dict) -> dict:
    """POST a GraphQL query, retrying rate limits, server errors and network errors with backoff."""
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.post(endpoint, json=body, headers=headers, timeout=60)
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.HTTPError(f"HTTP {response.status_code}")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            if attempt == MAX_RETRIES:
                raise
            delay = 2.0 * 2**attempt + random.uniform(0, 0.25)
            log.warning(f"Request failed ({e}); retrying in {delay:.0f}s")
            time.sleep(delay)
    raise RuntimeError("unreachable")


def to_forum_post(item: dict) -> ForumPost:
    """Convert one GraphQL result into a ForumPost."""
    names = [(item.get("user") or {}).get("displayName")]
    names += [c.get("displayName") for c in item.get("coauthors") or []]
    description = (item.get("contents") or {}).get("plaintextDescription") or ""
    return ForumPost(
        id=item["_id"],
        title=item.get("title") or "",
        url=item.get("pageUrl") or "",
        link_url=item.get("url") or None,
        authors=", ".join(n for n in names if n),
        posted=(item.get("postedAt") or "")[:10],
        af=bool(item.get("af")),
        karma=item.get("baseScore") or 0,
        af_karma=item.get("afBaseScore") or 0,
        comment_count=item.get("commentCount") or 0,
        word_count=item.get("wordCount") or 0,
        tags=", ".join(t["name"] for t in item.get("tags") or [] if t.get("name")),
        excerpt=re.sub(r"\s+", " ", description).strip(),
    )


def scrape_posts(site: str, year: int, delay_seconds: float, max_pages: int) -> list[ForumPost]:
    """
    Fetch every post from one year, one calendar month at a time (avoids deep offsets).

    Args:
        site: "lesswrong" or "alignment-forum"
        year: Year to fetch
        delay_seconds: Pause between requests
        max_pages: Safety cap on the total number of requests

    Returns: list[ForumPost]
    """
    endpoint = SITES[site]["endpoint"]
    posts: list[ForumPost] = []
    seen: set[str] = set()
    pages = 0

    with progress_bar() as progress:
        task = progress.add_task(f"Scraping {year} months", total=12)
        for month in range(1, 13):
            last_day = calendar.monthrange(year, month)[1]
            variables = {
                "after": f"{year}-{month:02d}-01T00:00:00Z",
                "before": f"{year}-{month:02d}-{last_day:02d}T23:59:59Z",
                "limit": PAGE_SIZE,
                "offset": 0,
            }
            month_count = 0
            while True:
                if pages >= max_pages:
                    log.warning(f"Reached --max-pages ({max_pages}); stopping early")
                    return posts
                data = post_with_retries(endpoint, {"query": POSTS_QUERY, "variables": variables})
                pages += 1
                items = ((data.get("data") or {}).get("posts") or {}).get("results") or []
                for item in items:
                    if item["_id"] not in seen:
                        seen.add(item["_id"])
                        posts.append(to_forum_post(item))
                        month_count += 1
                if len(items) < PAGE_SIZE:
                    break
                variables["offset"] += PAGE_SIZE
                if delay_seconds > 0:
                    time.sleep(delay_seconds)
            log.info(f"{year}-{month:02d}: {month_count} posts")
            progress.advance(task)
            if delay_seconds > 0:
                time.sleep(delay_seconds)

    return posts


def save_posts_to_csv(posts: list[ForumPost], output_path: Path):
    """Save posts to a CSV file, sorted from earliest to latest."""
    df = pd.DataFrame([post.model_dump() for post in posts])
    if not df.empty:
        df = df.sort_values(["posted", "id"]).reset_index(drop=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    log.info(f"Saved posts to {output_path}")
    return df


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Scrape a year of LessWrong or Alignment Forum posts into CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # LessWrong (recommended; includes every Alignment Forum post, flagged af=True)
  python src/scrape_forum_posts.py

  # Alignment Forum only (backup)
  python src/scrape_forum_posts.py --site alignment-forum

  # A different year and output file
  python src/scrape_forum_posts.py --year 2025 --output results/lw-2025.csv
        """
    )
    parser.add_argument("--site", choices=list(SITES), default=DEFAULT_SITE,
                        help=f"Site to scrape (default: {DEFAULT_SITE})")
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR,
                        help=f"Year to fetch (default: {DEFAULT_YEAR})")
    parser.add_argument("--output", type=str, default=None,
                        help="Output CSV path (default: results/1-lw-posts-raw.csv or results/1-af-posts-raw.csv)")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS,
                        help=f"Seconds between requests (default: {DEFAULT_DELAY_SECONDS})")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES,
                        help=f"Safety cap on requests of {PAGE_SIZE} posts each (default: {DEFAULT_MAX_PAGES})")
    return parser.parse_args()


def main():
    """Main execution function."""
    args = parse_arguments()
    output_path = Path(args.output or f"results/1-{SITES[args.site]['prefix']}-posts-raw.csv")

    log.info(f"Scraping {args.site} posts from {args.year}")
    posts = scrape_posts(args.site, args.year, args.delay, args.max_pages)
    df = save_posts_to_csv(posts, output_path)

    print_summary("Scrape summary", [
        ("Site", args.site),
        ("Posts", str(len(df))),
        ("Alignment Forum posts", str(int(df["af"].sum())) if not df.empty else "0"),
        ("Date range", f"{df['posted'].min()} to {df['posted'].max()}" if not df.empty else "-"),
        ("Output", str(output_path)),
    ])


if __name__ == "__main__":
    main()
