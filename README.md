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

The tool runs as a CLI application. It loops indefinitely until stopped by the user (Ctrl+C for graceful shutdown) or until configurable thresholds are met.

## Project Structure

```
litscout/
├── input/                          # ← YOUR INPUT GOES HERE
│   ├── research.md                 #   Your research angle (gitignored)
│   ├── research.example.md         #   Template for research.md
│   ├── settings.yaml               #   Your source & target settings (gitignored)
│   └── settings.example.yaml       #   Template for settings.yaml
├── .env                            # ← YOUR API KEYS GO HERE (gitignored)
├── .env.example                    #   Template for .env
├── config.yaml                     #   Advanced technical settings (rarely edit)
├── prompts/                        #   LLM system prompts
│   ├── query_gen.md                #   Query generation system prompt
│   ├── screening.md                #   Paper screening system prompt
│   └── sufficiency.md              #   Sufficiency checking system prompt
├── litscout/                       #   Source code
│   ├── __init__.py
│   ├── config.py                   #   Config loading & validation
│   ├── main.py                     #   CLI entry point & orchestrator
│   ├── llm_client.py               #   Async OpenAI-compatible API client
│   ├── pdf_reader.py               #   PDF text extraction (PyMuPDF)
│   ├── batcher.py                  #   Token-aware batching
│   ├── report_writer.py            #   Final Markdown report generation
│   ├── search/
│   │   ├── scholar_client.py       #   Multi-source academic search (6 sources)
│   │   ├── query_generator.py      #   LLM-powered query generation
│   │   └── deduplicator.py         #   DOI/ID tracking across iterations
│   ├── download/
│   │   ├── pdf_fetcher.py          #   Async PDF downloads with Elsevier fallback
│   │   └── temp_manager.py         #   Temp directory lifecycle
│   ├── screen/
│   │   ├── prompt_builder.py       #   Screening prompt assembly
│   │   └── screener.py             #   Paper screening orchestrator
│   └── decide/
│       ├── relevance_filter.py     #   Keep/discard filtering
│       ├── paper_store.py          #   Manifest updates & PDF copying
│       └── sufficiency_judge.py    #   Continue/stop decision
└── output/                         #   Results appear here (gitignored)
    ├── kept_papers/                #   Downloaded PDFs of relevant papers
    ├── reports/                    #   Final Markdown reports
    └── manifest.json               #   Running log of all papers
```

## Three Things to Configure

```
1. API keys      → .env
2. Sources       → input/settings.yaml
3. Research angle → input/research.md
```

## Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/your-username/litscout.git
cd litscout
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

### 2. Configure API Keys

```bash
cp .env.example .env
# Edit .env with your API keys (at minimum: LLM_API_KEY)
```

### 3. Configure Sources

```bash
cp input/settings.example.yaml input/settings.yaml
# Edit input/settings.yaml to enable your sources
```

### 4. Write Research Angle

```bash
cp input/research.example.md input/research.md
# Edit input/research.md with your research focus
```

### 5. Run

```bash
litscout
# or
python -m litscout.main
```

### 6. Check Results

```bash
ls output/kept_papers/   # Downloaded PDFs
ls output/reports/       # Final Markdown reports
cat output/manifest.json # Full log of all papers
```

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

## CLI Options

| Flag | Description | Overrides |
|------|-------------|-----------|
| `--config PATH` | Path to technical config | `config.yaml` |
| `--target-papers N` | Target number of relevant papers | `input/settings.yaml → target_papers` |
| `--max-iterations N` | Maximum search-screen cycles | `input/settings.yaml → max_iterations` |
| `--continue` | Ignore sufficiency, keep running | — |
| `--stop` | Run one more iteration then stop | — |
| `--help` | Show help message and exit | — |

## Clean Command

Remove generated output and temporary files to reset the project:

```bash
python -m litscout.clean
```

This will show what would be deleted and ask for confirmation. To skip the prompt:

```bash
python -m litscout.clean --confirm
```

**What gets deleted:**
- Everything in `output/` except `.gitkeep` (manifest.json, reports/, kept_papers/)
- Everything in `temp/` if it exists

**What is NOT touched:**
- `input/` (your research angle and settings)
- `prompts/` (LLM prompts)
- `config.yaml`, `.env` (configuration files)

## API Setup Guide

### LLM (Required)

Any OpenAI-compatible endpoint works. Default is Alibaba DashScope:

- **DashScope**: Get your API key at [Alibaba Cloud](https://dashscope.console.aliyun.com/)
- **OpenAI**: Get your API key at [OpenAI Platform](https://platform.openai.com/api-keys)
- **Azure OpenAI**: Get your key from Azure Portal
- **Ollama**: Run locally at `http://localhost:11434`

### OpenAlex (Free, no key needed)

- No key required. Provide email in `.env` for faster rate limits ("polite pool").
- [Documentation](https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication)

### Semantic Scholar (Free, key optional)

- Without key: shared rate limit. With key: 1 req/sec guaranteed.
- [Get a key](https://www.semanticscholar.org/product/api#api-key)

### Elsevier / ScienceDirect (Institutional)

- **API key**: [Elsevier Developer Portal](https://dev.elsevier.com/) (sign up with university email)
- **Institutional token**: Email `datasupport@elsevier.com` from your university email
- On-campus/VPN: API key alone may be sufficient

### arXiv (Free, no key needed)

- No credentials required. Preprints in physics, math, CS, biology, economics.

### PubMed / NCBI (Free, key optional)

- Without key: 3 req/sec. With key: 10 req/sec.
- [Get key](https://www.ncbi.nlm.nih.gov/account/settings/)

### CORE (Free key required)

- [Register for free API key](https://core.ac.uk/services/api)
- World's largest open access aggregator: 300M+ metadata records, 40M+ full texts.

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

---

## Testing Checklist

### 1. Verify `.env` is filled in correctly

Required keys (must have values):
- `LLM_BASE_URL` — e.g., `https://dashscope.aliyuncs.com/compatible-mode/v1`
- `LLM_API_KEY` — your actual API key
- `LLM_MODEL` — e.g., `qwen3.6-plus`

Optional keys (fill in only for sources you enable):
- `OPENALEX_EMAIL` — your email (recommended for OpenAlex)
- `S2_API_KEY` — Semantic Scholar API key (optional)
- `ELSEVIER_API_KEY` — Elsevier API key (required if elsevier enabled)
- `ELSEVIER_INST_TOKEN` — Elsevier institutional token (optional)
- `PUBMED_API_KEY` — PubMed API key (optional)
- `CORE_API_KEY` — CORE API key (required if core enabled)

### 2. Verify `input/settings.yaml` has correct source toggles

- At least one source with `role: search_and_pdf` must be `enabled: true`
- Sources with `role: pdf_only` (like Elsevier) are only used as fallback for PDF downloads
- Make sure the source names match exactly: `openalex`, `semantic_scholar`, `elsevier`, `arxiv`, `pubmed`, `core`

### 3. Verify `input/research.md` has a research angle written

- The file must exist and contain actual research content (not template text)
- It should describe your research focus, data, and what you're looking for

### 4. Test LLM API key

Run this one-liner to verify your LLM endpoint and key work:

```bash
python -c "
import asyncio, aiohttp, os
from dotenv import load_dotenv
load_dotenv()
async def test():
    async with aiohttp.ClientSession() as s:
        async with s.post(
            os.getenv('LLM_BASE_URL').rstrip('/') + '/chat/completions',
            headers={'Authorization': f'Bearer {os.getenv(\"LLM_API_KEY\")}', 'Content-Type': 'application/json'},
            json={'model': os.getenv('LLM_MODEL'), 'messages': [{'role': 'user', 'content': 'Say hello'}], 'max_tokens': 10}
        ) as r:
            data = await r.json()
            print(f'Status: {r.status}')
            print(f'Response: {data.get(\"choices\", [{}])[0].get(\"message\", {}).get(\"content\", \"ERROR\")}')
asyncio.run(test())
"
```

Expected output: `Status: 200` and a response like "Hello!"

### 5. Test Elsevier API (if enabled)

```bash
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
key = os.getenv('ELSEVIER_API_KEY')
if key:
    print(f'Elsevier API key is set: {key[:8]}...')
else:
    print('Elsevier API key is NOT set')
"
```

### 6. Run the pipeline

```bash
python -m litscout.main
```

Watch for:
- Clean startup banner showing active sources
- Query generation success
- Search results from enabled sources
- PDF download progress
- Screening results
- Sufficiency check output

### 7. Check output after a successful run

```bash
# Check manifest exists and has entries
cat output/manifest.json | python -m json.tool | head -30

# Check kept papers directory has PDFs
ls -la output/kept_papers/

# Check reports directory has a report
ls -la output/reports/

# Check log file for any errors
tail -50 output/litscout.log
```

### 8. Common errors and what they mean

| Error | Meaning | Fix |
|-------|---------|-----|
| `LLM base_url not set` | `.env` missing or `LLM_BASE_URL` empty | Copy `.env.example` to `.env` and fill in values |
| `input/settings.yaml not found` | User settings file missing | Copy `input/settings.example.yaml` to `input/settings.yaml` |
| `Please write your research angle` | `input/research.md` is empty or still has template text | Write your actual research focus in the file |
| `No search sources available` | No source with `role: search_and_pdf` is enabled | Enable at least one source in `input/settings.yaml` |
| `Source 'X' is enabled but ... not set in .env` | API key missing for enabled source | Add the key to `.env` or disable the source |
| `LLM API error (status=401)` | Wrong API key or wrong endpoint | Verify key and URL in `.env` |
| `LLM API error (status=429)` | Rate limit exceeded | Wait and retry, or add API key for higher limits |
| `Failed to parse ... as JSON` | LLM returned non-JSON response | Check model supports JSON output mode |
| `Unclosed client session` | Session not properly closed | Fixed in latest version — update if you see this |
