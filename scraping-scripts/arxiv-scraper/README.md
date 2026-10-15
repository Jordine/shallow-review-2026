### ArXiv Scraper

Scripts to search arXiv for AI safety/alignment papers, filter them for relevance and tag them with an LLM, and generate a taxonomy and editorial overview.

### Funnel

The pipeline narrows arXiv down in stages, each run month by month. Counts are from the January to October 9, 2026 run; full-year figures are rough extrapolations.

| Stage | How | Per month | Jan–Oct 9, 2026 | Full year (approx.) |
| --- | --- | --- | --- | --- |
| arXiv | All papers in cs.AI, cs.LG, cs.CL and cs.CR | ~8,000–13,000 | ~100,000 | ~130,000 |
| 1. Scrape | Keyword search (`QUERY_TERM_GROUPS`): about 12% of those papers, and ~70% of the arXiv papers the 2025 shallow review cited | ~1,000–1,800 | 12,183 | ~15,000 |
| 2. Filter | Claude Haiku rates each paper 1–5 on its own; keeps 4+ (~13%) | ~100–270 | 1,537 | ~2,000 |
| 2b. Shortlist | Claude Opus compares each month's filtered papers side by side; keeps the best ~9% | ~8–24 | 135 | ~170 |

Monthly volume varies a lot: May (NeurIPS deadline) and September (ICLR deadline) are the busiest months. Keyword-matched papers roughly doubled from 2025 to 2026, faster than arXiv overall (~40%).

### Setup

Steps 2–4 call Claude: step 2 uses `claude-haiku-5-5`, step 2b uses `claude-opus-5-5`, and steps 3–4 use `claude-sonnet-5-5` by default (change it with `--model`). Copy `.env.example` to `.env` in this folder and add your Anthropic API key:

```bash
cp .env.example .env
```

### Usage

Run each script from this folder, in order. Each script's defaults read the previous step's output.

The annotate and editorial steps still read a single CSV: point `--input` at a year's `results/shortlisted/<year>/arxiv-papers-shortlisted.csv`.

| Step | Command | What it does | Output |
| --- | --- | --- | --- |
| 1 | `uv run python src/scrape_arxiv_papers.py` | Searches arXiv (default: cs.AI/LG/CL/CR papers submitted in 2026 matching a list of safety keywords; see `QUERY_TERM_GROUPS` in the script) month by month and looks up citations, venues and author h-indexes on Semantic Scholar. Months already scraped are skipped, so a rerun resumes | `results/raw/<year>/<month>/arxiv-papers-raw.csv` (e.g. `results/raw/2026/jan/arxiv-papers-raw.csv`), one per month: all papers found (title, authors, dates, abstract, categories, IDs, PDF link, comment, journal ref) with citation counts, citations per month since publication, venue, and the highest author h-index from Semantic Scholar |
| 2 | `uv run python src/filter_arxiv_papers.py` | Rates each paper's relevance to technical AI alignment from 1 to 5, using the abstract plus comment, venue, citation and author signals, and keeps papers rated 4+, month by month. Papers that already have a score aren't rated again | `results/filtered/<year>/<month>/arxiv-papers-rated.csv`: every paper with its relevance score and reasoning<br>`results/filtered/<year>/<month>/arxiv-papers-filtered.csv`: only papers rated at least `--min-score` (default 4) |
| 2b | `uv run python src/shortlist_arxiv_papers.py` | Compares each month's filtered papers side by side with Claude Opus 5.5 and picks the most important ~9% (about 100–150 a year), best first. Months whose shortlist is newer than their filtered file are skipped | `results/shortlisted/<year>/<month>/arxiv-papers-shortlisted.csv`: the picked papers with `shortlist_rank` and `shortlist_reason`<br>`results/shortlisted/<year>/arxiv-papers-shortlisted.csv`: the whole year's shortlist |
| 3 | `uv run python src/annotate_arxiv_papers.py` | Tags the highly relevant papers | `results/3-arxiv-papers-annotated.csv`: highly relevant papers with LLM tags |
| 4 | `uv run python src/generate_taxonomy_and_editorial.py` | Generates a taxonomy and editorial from the annotated papers | `results/4-arxiv-taxonomy-and-editorial.md`: taxonomy, editorial overview, and paper listings |

### Options

- `scrape_arxiv_papers.py`
  - `--query`: arXiv query without dates; each month's date range is added automatically
  - `--start-month` / `--end-month`: `YYYY-MM` (default: January 2026 to the current month)
  - `--overwrite`: re-scrape months that already have results (months saved before they ended are always re-scraped)
  - `--max-results` per month (default 5,000), `--output-dir` (default `results/raw`), `--page-size`, `--delay`
- `filter_arxiv_papers.py`: `--raw-dir` (default `results/raw`), `--output-dir` (default `results/filtered`), `--start-month` / `--end-month`, `--overwrite` (rate every paper again), `--model`, `--min-score` (default 4)
- `shortlist_arxiv_papers.py`: `--filtered-dir` (default `results/filtered`), `--output-dir` (default `results/shortlisted`), `--share` (default 0.09) or `--per-month N`, `--start-month` / `--end-month`, `--overwrite`, `--model` (default `claude-opus-5-5`), `--effort` (default `high`)
- `annotate_arxiv_papers.py`: `--input`, `--output`, `--model`
- `generate_taxonomy_and_editorial.py`: `--input`, `--output`, `--model`

Run any script with `--help` for details.
