### ArXiv Scraper

Scripts to search arXiv for AI safety/alignment papers, filter them for relevance and tag them with an LLM, and generate a taxonomy and editorial overview.

### Setup

Steps 2–4 call Claude: step 2 uses `claude-haiku-5-5` and steps 3–4 use `claude-sonnet-5-5` by default (change it with `--model`). Copy `.env.example` to `.env` in this folder and add your Anthropic API key:

```bash
cp .env.example .env
```

### Usage

Run each script from this folder, in order. Each script's defaults read the previous step's output.

| Step | Command | What it does | Output |
| --- | --- | --- | --- |
| 1 | `uv run python src/scrape_arxiv_papers.py` | Searches arXiv (default: CS papers mentioning "ai safety" or "ai alignment", submitted in 2026) | `results/1-arxiv-papers-raw.csv`: all papers found (title, authors, dates, abstract, categories, IDs, PDF link) |
| 2 | `uv run python src/filter_arxiv_papers.py` | Rates each paper's relevance to technical AI alignment and keeps the highly relevant ones | `results/2-arxiv-papers-rated.csv`: every paper with its relevance rating and reasoning<br>`results/2-arxiv-papers-highly-relevant.csv`: only papers rated "highly relevant" |
| 3 | `uv run python src/annotate_arxiv_papers.py` | Tags the highly relevant papers and adds citation counts from Semantic Scholar | `results/3-arxiv-papers-annotated.csv`: highly relevant papers with LLM tags, citation counts, and citations per month since publication |
| 4 | `uv run python src/generate_taxonomy_and_editorial.py` | Generates a taxonomy and editorial from the annotated papers | `results/4-arxiv-taxonomy-and-editorial.md`: taxonomy, editorial overview, and paper listings |

### Options

- `scrape_arxiv_papers.py`
  - `--base-query`: topic query; the date range is added automatically
  - `--start-date` / `--end-date`: `YYYYMMDDHHMM`
  - `--query`: full arXiv query, overriding the base query and dates
  - `--max-results` (default 1000), `--output`, `--page-size`, `--delay`
- `filter_arxiv_papers.py`: `--input`, `--rated`, `--filtered`, `--model`
- `annotate_arxiv_papers.py`: `--input`, `--output`, `--model`
- `generate_taxonomy_and_editorial.py`: `--input`, `--output`, `--model`

Run any script with `--help` for details.
