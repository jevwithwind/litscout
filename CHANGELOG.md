# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-04-15

### Added
- Published to PyPI — install with `pip install litscout`
- CLI subcommands: `init`, `run`, `report`, `clean`, `status`
- Plugin-based source architecture in `litscout/sources/`
- 6 academic search source plugins:
  - OpenAlex (search + PDF)
  - Semantic Scholar (search + PDF)
  - Elsevier (PDF-only, institutional token)
  - arXiv (search + PDF)
  - PubMed (search + metadata)
  - CORE (search + PDF)
- Bundled template files for project scaffolding (`.env`, `config.yaml`, `settings.yaml`, `research.md`)
- Bundled prompt files (`query_gen.md`, `screening.md`, `sufficiency.md`)
- `litscout init` command to scaffold new projects
- `litscout status` command to show project summary
- `litscout clean` command to remove output/temp files
- `litscout report` command to regenerate Markdown report
- Resource loading via `importlib.resources` for both dev and installed modes
- Optional field support for source credentials (e.g., `ELSEVIER_INST_TOKEN`)
- Windows console encoding fix (ASCII characters instead of box-drawing)

### Changed
- Refactored `scholar_client.py` to thin orchestrator that delegates to source plugins
- Updated `pyproject.toml` with proper PyPI metadata
- Version now managed dynamically via `setuptools-scm` and git tags
- Updated README with installation instructions and CLI reference

### Fixed
- UnicodeEncodeError on Windows for `litscout status` output
- ELSEVIER_INST_TOKEN incorrectly treated as required credential

## [0.1.0] - Pre-release

Initial development version.
