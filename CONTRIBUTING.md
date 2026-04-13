# Contributing to litscout

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

1. Fork and clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```
3. Install in development mode:
   ```bash
   pip install -e ".[dev]"
   ```
4. Copy `.env.example` to `.env` and fill in your API keys

## Project Structure

- `litscout/` — Main package source code
- `prompts/` — LLM prompt templates
- `config.yaml` — Pipeline configuration defaults
- `output/` — Runtime output directory (git-ignored)

## How to Contribute

### Reporting Bugs
- Open an issue with a clear description and steps to reproduce
- Include your Python version and OS

### Suggesting Features
- Open an issue tagged `enhancement`
- Describe the use case and expected behavior

### Submitting Code
1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make your changes with clear commit messages
3. Ensure your code follows the existing style (type hints, docstrings)
4. Submit a pull request with a description of your changes

## Code Style

- Use type hints for all function signatures
- Write docstrings for all public functions and classes
- Keep functions focused and small
- Use `async`/`await` for I/O-bound operations
- Follow PEP 8

## Adding a New Search Source

To add a new academic search API:
1. Add a new method in `litscout/search/scholar_client.py`
2. Add the source name to `config.yaml` under `search.sources`
3. Add any required env vars to `.env.example`
4. Update README.md with setup instructions for the new source

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
