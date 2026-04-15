# litscout

![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-alpha-orange.svg)

**Automated literature search, screening, and prioritization pipeline powered by LLMs.**

## What It Does

`litscout` is an automated literature discovery and screening pipeline for academic researchers. It uses AI to:

1. **Generate smart search queries** based on your research angle
2. **Search academic databases** (OpenAlex, Semantic Scholar, arXiv, PubMed, CORE) for candidate papers
3. **Download PDFs** (with Elsevier ScienceDirect API fallback for paywalled papers)
4. **Screen papers using an LLM** for relevance to your research angle
5. **Keep medium/high relevance papers**, discard the rest
6. **Repeat until sufficient coverage** is achieved
7. **Generate a final Markdown report** summarizing everything found

## Installation

### From PyPI (coming soon)

```bash
pip install litscout
```

### From Source

```bash
git clone https://github.com/your-username/litscout.git
cd litscout
pip install -e .
```

## Quick Start

### 1. Initialize a Project

```bash
litscout init
```

This scaffolds a new litscout project in your current directory with all the necessary config files and directories.

### 2. Configure API Keys

```bash
# Edit .env with your API keys
# At minimum: LLM_BASE_URL, LLM_API_KEY, LLM_MODEL
```

### 3. Configure Sources

```bash
# Edit input/settings.yaml to enable your sources
# At least one source with role 'search_and_pdf' must be enabled
```

### 4. Write Research Angle

```bash
# Edit input/research.md with your research focus
```

### 5. Run the Pipeline

```bash
litscout run
```

### 6. Check Results

```bash
ls output/kept_papers/   # Downloaded PDFs
ls output/reports/       # Final Markdown reports
cat output/manifest.json # Full log of all papers
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `litscout init` | Scaffold a new litscout project directory |
| `litscout run` | Run the literature search and screening pipeline |
| `litscout report` | Regenerate the markdown report from existing manifest.json |
| `litscout clean` | Clean output and temp directories |
| `litscout status` | Show quick summary of current project state |
| `litscout --help` | Show help message and exit |

### `litscout init`

Scaffolds a new litscout project in the current directory (or specified path):

```bash
litscout init              # Use current directory
litscout init ./my-project # Use specified directory
```

Creates:
- `input/research.md` — Your research angle
- `input/settings.yaml` — Source and target settings
- `.env` — API keys
- `config.yaml` — Advanced technical settings
- `output/`, `temp/` — Output and temp directories

### `litscout run`

Runs the full literature search and screening pipeline:

```bash
litscout run                    # Use default config.yaml
litscout run --config my.yaml   # Use custom config path
```

### `litscout report`

Regenerates the markdown report from an existing manifest.json without re-running the pipeline:

```bash
litscout report
litscout report --config my.yaml
```

### `litscout clean`

Cleans output and temp directories:

```bash
litscout clean           # Ask for confirmation
litscout clean --confirm # Skip confirmation
```

### `litscout status`

Shows a quick summary of the current project state:

```bash
litscout status
litscout status --config my.yaml
```

Output includes:
- Active sources and their roles
- Target papers
- Iterations run
- Papers kept (high/medium breakdown)
- Papers discarded
- Last updated timestamp

## Configuring Search Sources

Edit `input/settings.yaml` to enable the sources you have access to:

| Source | Role | Key Required? | Coverage | Best For |
|--------|------|---------------|----------|----------|
| OpenAlex | Search + PDF | No (email optional) | 250M+ works, all disciplines | General academic research |
| Semantic Scholar | Search + PDF | No (optional for speed) | 200M+ papers, AI-ranked | CS, biomedical, broad coverage |
| Elsevier | PDF only | Yes (institutional) | Paywalled Elsevier journals | University-subscribed content |
| arXiv | Search + PDF | No | 2.4M+ preprints | Physics, math, CS, quantitative biology |
| PubMed | Search + PDF | No (optional for speed) | 36M+ citations | Biomedical and life sciences |
| CORE | Search + PDF | Yes (free) | 300M+ metadata, 40M+ full texts | Open access aggregation |

**Default enabled sources:** OpenAlex (search+pdf), Elsevier (pdf-only)

## Configuration Files

### `.env` (API Keys)

Required:
- `LLM_BASE_URL` — OpenAI-compatible endpoint URL
- `LLM_API_KEY` — Your LLM API key
- `LLM_MODEL` — Model name (e.g., `qwen3.6-plus`)

Optional (enable sources as needed):
- `OPENALEX_EMAIL` — For faster OpenAlex rate limits
- `S2_API_KEY` — Semantic Scholar (optional, for guaranteed 1 req/sec)
- `ELSEVIER_API_KEY` — Elsevier ScienceDirect (required for pdf_only role)
- `ELSEVIER_INST_TOKEN` — Elsevier institutional token (for off-campus access)
- `PUBMED_API_KEY` — PubMed (optional, for 10 req/sec vs 3 req/sec)
- `CORE_API_KEY` — CORE (required if enabled)

### `input/settings.yaml` (User Settings)

```yaml
target_papers: 20          # Stop when this many papers are kept
max_iterations: 0          # 0 = unlimited
auto_stop: false           # true = stop automatically; false = ask user

sources:
  openalex:
    enabled: true
    role: search_and_pdf
  semantic_scholar:
    enabled: false
    role: search_and_pdf
  elsevier:
    enabled: true
    role: pdf_only
  arxiv:
    enabled: false
    role: search_and_pdf
  pubmed:
    enabled: false
    role: search_and_pdf
  core:
    enabled: false
    role: search_and_pdf
```

### `config.yaml` (Technical Settings — rarely needs editing)

| Setting | Description | Default |
|---------|-------------|---------|
| `api.max_tokens` | Max tokens for LLM responses | 16384 |
| `api.temperature` | LLM temperature (0.0-1.0) | 0.3 |
| `api.max_concurrent_requests` | Concurrent LLM requests | 3 |
| `search.queries_per_iteration` | Queries per round | 5 |
| `search.results_per_query` | Max results per query | 20 |
| `search.year_range` | Papers from last N years | 5 |
| `download.concurrency` | Max simultaneous downloads | 5 |
| `download.timeout` | Download timeout (seconds) | 60 |
| `download.max_pdf_size_mb` | Skip PDFs larger than this | 50 |
| `screening.batch_size` | Papers per LLM screening call | 10 |
| `screening.max_tokens_per_batch` | Token budget per batch | 200000 |
| `sufficiency.min_high_relevance` | Min high-relevance papers | 5 |
| `sufficiency.min_medium_relevance` | Min medium-relevance papers | 8 |

## Adding New Sources

litscout uses a plugin-based source architecture. To add a new source:

1. Create a new file in `litscout/sources/` (e.g., `my_source.py`)
2. Subclass `ScholarSource` from `litscout.sources.base`
3. Implement the required methods:
   - `name()` — Return the source identifier
   - `search(query, limit, year_min, credentials)` — Search for papers
   - `fetch_pdf(paper, credentials, session)` — Fetch PDF content
4. Register it in `litscout/sources/__init__.py`

Example:

```python
from litscout.sources.base import PaperMetadata, ScholarSource

class MySource(ScholarSource):
    @classmethod
    def name(cls) -> str:
        return "my_source"

    async def search(self, query, limit, year_min, credentials):
        # Implement search logic
        return []

    async def fetch_pdf(self, paper, credentials, session):
        # Implement PDF fetch logic
        return None
```

## Output Format

The final report is a Markdown file with:

1. **Header**: Generation timestamp, iteration count, paper statistics
2. **Research Angle**: Your original research prompt
3. **Summary Table**: All kept papers with relevance and brief descriptions
4. **Detailed Evaluations**: Full analysis for each kept paper
5. **Coverage Analysis**: Gaps identified by the LLM
6. **Search Queries Used**: All queries across all iterations

## Graceful Shutdown

Press `Ctrl+C` to gracefully stop the pipeline. It will:

1. Finish the current iteration
2. Save the manifest
3. Generate a final report
4. Clean up temporary files

## Note on Language Support

Currently supports English-language papers only. Japanese language support is planned for a future release.

## License

MIT License — see [LICENSE](LICENSE) for details.

## Acknowledgments

- **Semantic Scholar** (Allen Institute for AI) — Free academic paper search API
- **OpenAlex** — Open bibliographic database
- **Elsevier** — ScienceDirect API for paywalled paper access
- **arXiv** — Open-access preprint repository
- **PubMed / NCBI** — Biomedical literature database
- **CORE** — Open access aggregator

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for details.
