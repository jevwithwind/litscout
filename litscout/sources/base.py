"""litscout.sources.base — Abstract base class for academic search sources."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class PaperMetadata:
    """Metadata for a paper from an academic search API."""
    paper_id: str  # Source-specific ID
    doi: str | None
    title: str
    authors: list[str]
    year: int
    abstract: str | None
    pdf_url: str | None
    source: str  # e.g., "openalex", "semantic_scholar", "arxiv", etc.


class ScholarSource(ABC):
    """Abstract base class for academic search sources.

    Each source plugin implements search and/or PDF fetching capabilities.
    Subclass this to add new academic sources to litscout.
    """

    @classmethod
    @abstractmethod
    def name(cls) -> str:
        """Return the source identifier string (e.g., 'openalex')."""
        ...

    @classmethod
    def supports_search(cls) -> bool:
        """Return True if this source can search for papers."""
        return True

    @classmethod
    def supports_pdf(cls) -> bool:
        """Return True if this source can fetch PDFs."""
        return True

    @abstractmethod
    async def search(
        self,
        query: str,
        limit: int,
        year_min: int,
        credentials: dict[str, str],
    ) -> list[PaperMetadata]:
        """Search for papers matching the query.

        Args:
            query: Search query string.
            limit: Maximum number of results to return.
            year_min: Only return papers from this year or later.
            credentials: Source-specific credentials from .env.

        Returns:
            List of PaperMetadata objects.
        """
        ...

    async def fetch_pdf(
        self,
        paper: PaperMetadata,
        credentials: dict[str, str],
        session: Any = None,
    ) -> bytes | None:
        """Fetch PDF content for a paper.

        Args:
            paper: PaperMetadata with source information.
            credentials: Source-specific credentials.
            session: Optional aiohttp ClientSession for making requests.

        Returns:
            PDF bytes or None if fetch failed.
        """
        return None
