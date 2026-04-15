"""litscout.sources.core — CORE open access search source."""

import logging
from typing import Any

import aiohttp

from litscout.sources.base import PaperMetadata, ScholarSource

logger = logging.getLogger(__name__)


class CORESource(ScholarSource):
    """CORE open access search source.

    Free API key required. World's largest open access aggregator.
    Docs: https://core.ac.uk/documentation/api
    """

    @classmethod
    def name(cls) -> str:
        return "core"

    async def search(
        self,
        query: str,
        limit: int,
        year_min: int,
        credentials: dict[str, str],
    ) -> list[PaperMetadata]:
        """Search CORE API v3."""
        session = credentials.get("_session")
        if session is None:
            logger.warning("CORE: no aiohttp session provided")
            return []

        api_key = credentials.get("api_key")
        if not api_key:
            logger.warning("CORE API key not set")
            return []

        url = "https://api.core.ac.uk/v3/search/works"
        headers = {"Authorization": f"Bearer {api_key}"}
        params = {
            "q": query,
            "limit": limit,
        }

        papers: list[PaperMetadata] = []

        try:
            async with session.get(url, headers=headers, params=params, timeout=60) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get("results", [])
                    for item in results:
                        paper = self._parse_paper(item, year_min)
                        if paper:
                            papers.append(paper)
                else:
                    logger.warning("CORE API error (status=%d)", response.status)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning("CORE API request failed: %s", e)

        logger.info("CORE: found %d papers for query '%s'", len(papers), query)
        return papers

    async def fetch_pdf(
        self,
        paper: PaperMetadata,
        credentials: dict[str, str],
        session: Any = None,
    ) -> bytes | None:
        """CORE often has direct download URLs for full text."""
        if paper.source != "core" or not paper.pdf_url:
            return None
        if session is None:
            return None
        try:
            async with session.get(paper.pdf_url) as response:
                if response.status == 200:
                    return await response.read()
        except aiohttp.ClientError as e:
            logger.debug("CORE PDF download failed: %s", e)
        return None

    def _parse_paper(self, data: dict[str, Any], year_min: int) -> PaperMetadata | None:
        """Parse a CORE paper response."""
        try:
            year = data.get("yearPublished", 0)
            if year < year_min:
                return None

            title = data.get("title", "")
            if isinstance(title, dict):
                title = title.get("en", "")

            abstract = data.get("abstract", "")
            if isinstance(abstract, dict):
                abstract = abstract.get("en", "")

            authors = [
                author.get("name", "")
                for author in data.get("authors", [])
                if author.get("name")
            ]

            download_url = data.get("downloadUrl")
            doi = data.get("doi")

            return PaperMetadata(
                paper_id=data.get("id", ""),
                doi=doi,
                title=title,
                authors=authors,
                year=year,
                abstract=abstract,
                pdf_url=download_url,
                source="core",
            )
        except Exception as e:
            logger.debug("Failed to parse CORE paper: %s", e)
            return None
