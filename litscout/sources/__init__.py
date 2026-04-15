"""litscout.sources — Plugin-based source architecture for academic search.

This module provides a registry of academic search sources. Each source
is a plugin that implements the ScholarSource abstract base class.

To add a new source:
1. Create a new file in this directory (e.g., my_source.py)
2. Subclass ScholarSource from litscout.sources.base
3. Implement the required methods (name, search, fetch_pdf)
4. Import and register it below
"""

from litscout.sources.base import PaperMetadata, ScholarSource
from litscout.sources.openalex import OpenAlexSource
from litscout.sources.semantic_scholar import SemanticScholarSource
from litscout.sources.elsevier import ElsevierSource
from litscout.sources.arxiv import ArxivSource
from litscout.sources.pubmed import PubMedSource
from litscout.sources.core import CORESource

# Registry of all available sources
SOURCE_REGISTRY: dict[str, type[ScholarSource]] = {
    "openalex": OpenAlexSource,
    "semantic_scholar": SemanticScholarSource,
    "elsevier": ElsevierSource,
    "arxiv": ArxivSource,
    "pubmed": PubMedSource,
    "core": CORESource,
}


def get_source(name: str) -> ScholarSource | None:
    """Get a source instance by name.

    Args:
        name: Source name (e.g., 'openalex', 'semantic_scholar').

    Returns:
        A new instance of the source class, or None if not found.
    """
    source_cls = SOURCE_REGISTRY.get(name)
    if source_cls is None:
        return None
    return source_cls()


def list_sources() -> list[str]:
    """Return a list of all registered source names."""
    return list(SOURCE_REGISTRY.keys())


def get_search_sources() -> list[type[ScholarSource]]:
    """Return all source classes that support search."""
    return [
        cls for cls in SOURCE_REGISTRY.values()
        if cls.supports_search()
    ]


def get_pdf_sources() -> list[type[ScholarSource]]:
    """Return all source classes that support PDF fetching."""
    return [
        cls for cls in SOURCE_REGISTRY.values()
        if cls.supports_pdf()
    ]
