"""litscout.search.scholar_client — Unified academic search orchestrator.

This module provides a thin orchestrator that loads enabled sources from
settings and delegates search/fetch calls to the corresponding source plugins.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

import aiohttp

from litscout.sources import get_source, list_sources
from litscout.sources.base import PaperMetadata, ScholarSource

logger = logging.getLogger(__name__)


class ScholarClient:
    """Unified search client for multiple academic sources.

    Loads enabled sources from settings and delegates search/fetch calls
    to the corresponding source plugins.
    """

    def __init__(
        self,
        active_sources: list[dict[str, Any]] | None = None,
    ):
        self.active_sources = active_sources or []
        self._session: aiohttp.ClientSession | None = None
        self._source_instances: dict[str, ScholarSource] = {}

    async def __aenter__(self) -> "ScholarClient":
        self._session = aiohttp.ClientSession()
        # Instantiate source plugins with session
        for source_config in self.active_sources:
            source_name = source_config.get("name", "")
            source = get_source(source_name)
            if source is not None:
                self._source_instances[source_name] = source
            else:
                logger.warning("Unknown source: %s", source_name)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._session:
            await self._session.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def search(
        self, query: str, limit: int, year_range: int = 5
    ) -> list[PaperMetadata]:
        """Search multiple academic sources and deduplicate results.

        Args:
            query: Search query string.
            limit: Max results per source.
            year_range: Only consider papers from the last N years.

        Returns:
            List of unique PaperMetadata objects, deduplicated by DOI.
        """
        year_min = datetime.now().year - year_range

        all_papers: list[PaperMetadata] = []
        seen_dois: set[str | None] = set()

        # Search each active source that supports search
        for source_config in self.active_sources:
            source_name = source_config.get("name", "")
            credentials = source_config.get("credentials", {})

            source = self._source_instances.get(source_name)
            if source is None:
                logger.warning("Source not loaded: %s", source_name)
                continue

            if not source.supports_search():
                continue

            # Inject session into credentials for the source
            credentials["_session"] = await self._get_session()

            papers = await source.search(
                query, limit, year_min, credentials
            )

            # Deduplicate by DOI
            for paper in papers:
                if paper.doi not in seen_dois:
                    seen_dois.add(paper.doi)
                    all_papers.append(paper)

        logger.info(
            "Total unique papers found: %d for query '%s'",
            len(all_papers),
            query,
        )
        return all_papers

    async def fetch_pdf(
        self, paper: PaperMetadata, credentials: dict | None = None
    ) -> bytes | None:
        """Fetch PDF for a paper using the appropriate source fetcher.

        Args:
            paper: PaperMetadata with source information.
            credentials: Optional credentials dict for the source.

        Returns:
            PDF bytes or None if fetch failed.
        """
        source = self._source_instances.get(paper.source)
        if source is None:
            logger.warning("No PDF fetcher for source: %s", paper.source)
            return None

        if not source.supports_pdf():
            return None

        session = await self._get_session()
        creds = credentials or {}
        creds["_session"] = session

        return await source.fetch_pdf(paper, creds, session)
