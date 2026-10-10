"""
Shared Rich terminal output for the arXiv scraper scripts: logging, progress bars and summary tables.
"""

import logging
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

# One console for logs, progress bars and tables, so they don't overwrite each other
console = Console()


def setup_logging(name: str) -> logging.Logger:
    """Route logging through Rich (colours, timestamps, readable tracebacks) and return a named logger."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
    )
    # Hide per-request lines ("HTTP Request: POST ...", "Requesting page ...") from client libraries
    for noisy_logger in ("httpx", "httpx2", "arxiv"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
    return logging.getLogger(name)


def progress_bar() -> Progress:
    """Progress bar with count, elapsed and remaining time. Use as a context manager."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )


def print_summary(title: str, rows: list[tuple[str, str]]) -> None:
    """Print a two-column summary table of (label, value) rows."""
    table = Table(title=title, show_header=False, title_style="bold")
    table.add_column(style="cyan")
    table.add_column()
    for label, value in rows:
        table.add_row(label, value)
    console.print(table)
