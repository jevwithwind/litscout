# litscout

![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-alpha-orange.svg)

**Automated literature search, screening, and prioritization pipeline powered by LLMs.**

## What It Does

`litscout` is an automated literature discovery and screening pipeline for academic researchers. It uses AI to:

1. **Generate smart search queries** based on your research angle
2. **Search academic databases** (Semantic Scholar, OpenAlex) for candidate papers
3. **Download PDFs** (with Elsevier ScienceDirect API fallback for paywalled papers)
4. **Screen papers using an LLM** for relevance to your research angle
5. **Keep medium/high relevance papers**, discard the rest
6. **Repeat until sufficient coverage** is achieved
7. **Generate a final Markdown report** summarizing everything found

The tool runs as a CLI application. It loops indefinitely until stopped by the user (Ctrl+C for graceful shutdown) or until configurable thresholds are met.

## How It Works

```mermaid
flowchart TD
    A[Research Angle] --> B[Query Generator]
    B --> C[Search APIs]
    C --> D{New Papers?}
    D -->|Yes| E[Download PDFs]
    D -->|No| F[No Candidates]
    E --> G[Screen with LLM]
    G --> H[Filter Results]
    H --> I{Sufficient?}
    I -->|No| C
    I -->|Yes| J[Stop or Continue]
    J --> K[Generate Report]
```

### Pipeline Flow

1. **Query Generation**: The LLM analyzes your research angle and generates targeted search queries
2. **Academic Search**: Papers are fetched from Semantic Scholar and OpenAlex APIs
3. **Deduplication**: Papers are tracked by DOI to avoid duplicates across iterations
4. **PDF Download**: Open-access PDFs are downloaded; Elsevier API is used as fallback
5. **LLM Screening**: Each paper is evaluated against your research angle
6. **Relevance Filtering**: High/medium papers are kept; low papers are discarded
7. **Sufficiency Check**: The LLM assesses if enough papers have been collected
8. **Report Generation**: A comprehensive Markdown report is created

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/litscout.git
cd litscout
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -e .
```

### 4. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
# Edit .env with your API keys
```

See the [API Setup Guide](#api-setup-guide) for details on obtaining each key.

### 5. Set Up Your Research Angle

Edit `prompts/research.md` with your research focus:

```markdown
# Research Angle

## My Research Focus
(Describe your research question and specific angles you're investigating)

## My Data
(Describe your dataset, methodology, or experimental setup)

## What I'm Looking For
- (Type of papers, methods, findings you need)
- (Specific methodologies or frameworks)
- (Particular datasets or benchmarks)
```

### 6. Run litscout

```bash
litscout
# or
python -m litscout.main
```

### 7. Find Your Results

After the pipeline completes, you'll find:

- **`output/kept_papers/`**: Downloaded PDFs of relevant papers
- **`output/reports/`**: Final Markdown reports
- **`output/manifest.json`**: Running log of all papers processed

## Configuration

The pipeline is configured via `config.yaml`. Key settings:

| Setting | Description | Default |
|---------|-------------|---------|
| `api.max_tokens` | Maximum tokens for LLM responses | 16384 |
| `api.temperature` | LLM temperature (0.0-1.0) | 0.3 |
| `search.queries_per_iteration` | Queries generated per round | 5 |
| `search.results_per_query` | Max results per query | 20 |
| `search.year_range` | Only papers from last N years | 5 |
| `download.concurrency` | Max simultaneous downloads | 5 |
| `screening.batch_size` | Papers per LLM screening call | 10 |
| `sufficiency.target_kept_papers` | Stop when this many papers kept | 20 |
| `sufficiency.min_high_relevance` | Min high-relevance papers | 5 |
| `sufficiency.min_medium_relevance` | Min medium-relevance papers | 8 |
| `sufficiency.max_iterations` | 0 = unlimited, otherwise max rounds | 0 |
| `sufficiency.auto_stop` | Auto-stop when sufficient | false |

## API Setup Guide

### LLM (OpenAI-compatible)

Any OpenAI-compatible endpoint works. Default is Alibaba DashScope:

- **DashScope**: Get your API key at [Alibaba Cloud](https://dashscope.console.aliyun.com/)
- **OpenAI**: Get your API key at [OpenAI Platform](https://platform.openai.com/api-keys)
- **Azure OpenAI**: Get your key from Azure Portal
- **Ollama**: Run locally at `http://localhost:11434`

### Semantic Scholar

Free API with optional key for higher rate limits:

- **Without key**: 10 requests/minute shared across all users
- **With key**: 1 request/second guaranteed
- **Get a key**: [Semantic Scholar API Key Request](https://www.semanticscholar.org/product/api#api-key)

### OpenAlex

Free API, no key required but providing an email is polite:

- **No key required**: Free and open
- **Add email for polite pool**: [OpenAlex Documentation](https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication)
- **Format**: `OPENALEX_EMAIL=your_email@example.com`

### Elsevier / ScienceDirect

Optional API for paywalled paper access:

- **Get API key**: [Elsevier Developer Portal](https://dev.elsevier.com/)
- **Institutional token**: Email `datasupport@elsevier.com` from your university email
- **On-campus/VPN**: API key alone may be sufficient

## Output Format

The final report is a Markdown file with:

1. **Header**: Generation timestamp, iteration count, paper statistics
2. **Research Angle**: Your original research prompt
3. **Summary Table**: All kept papers with relevance and brief descriptions
4. **Detailed Evaluations**: Full analysis for each kept paper
5. **Coverage Analysis**: Gaps identified by the LLM
6. **Search Queries Used**: All queries across all iterations

Example report structure:

```markdown
# litscout Report
**Generated**: 2026-04-13 10:30:00
**Total iterations**: 3
**Papers screened**: 67
**Papers kept**: 18 (7 high, 11 medium)
**Papers discarded**: 49

## Research Angle
> [your research angle text]

## Summary Table
| # | Paper | Year | Relevance | Why Relevant |
|---|-------|------|-----------|--------------|
| 1 | smith_2024_rag_survey.pdf | 2024 | High | Directly surveys RAG... |

## Detailed Evaluations
### 1. smith_2024_rag_survey.pdf
- **Relevance rating:** High
- **Why it's useful:** Directly surveys RAG architectures...
- **Key pages to read:** 3, 7-9, 14
- **Key findings:**
  - Finding 1
  - Finding 2
  - Finding 3
- **Methodology & data:** Benchmarks seven open-source RAG systems...
```

## CLI Options

```bash
litscout [OPTIONS]

Options:
  --config PATH         Path to config file (default: config.yaml)
  --continue            Ignore sufficiency, keep running until stopped
  --stop                Run one more iteration then stop
  --target-papers N     Override target kept papers
  --max-iterations N    Override max iterations
  --help                Show this message and exit
```

Examples:

```bash
# Run with default config
litscout

# Use custom config file
litscout --config myconfig.yaml

# Ignore sufficiency and keep running
litscout --continue

# Override target papers
litscout --target-papers 30
```

## Graceful Shutdown

Press `Ctrl+C` to gracefully stop the pipeline. It will:

1. Finish the current iteration
2. Save the manifest
3. Generate a final report
4. Clean up temporary files

## Note on Language Support

Currently supports English-language papers only. Japanese language support is planned for a future release.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- **Semantic Scholar** (Allen Institute for AI) - Free academic paper search API
- **OpenAlex** - Open bibliographic database
- **Elsevier** - ScienceDirect API for paywalled paper access

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## Citation

If you use litscout in your research, please cite:

```bibtex
@software{litscout2026,
  title={litscout: Automated Literature Search and Screening Pipeline},
  author={litscout contributors},
  year={2026},
  url={https://github.com/your-username/litscout}
}
```
