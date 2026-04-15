"""litscout.sources.semantic_scholar — Semantic Scholar academic search source."""

import logging
from typing import Any

import aiohttp

from litscout.sources.base import PaperMetadata, ScholarSource

logger = logging.getLogger(__name__)


class SemanticScholarSource(ScholarSource):
    """Semantic Scholar academic search source.

    Free, optional API key for guaranteed 1 req/sec rate limit.
    Covers 200M+ papers with AI-powered relevance ranking.
    Docs: https://api.semanticscholar.org/
    """

    @classmethod
    def name(cls) -> str:
        return "semantic_scholar"

    async def search(
        self,
        query: str,
        limit: int,
        year_min: int,
        credentials: dict[str, str],
    ) -> list[PaperMetadata]:
        """Search Semantic Scholar API."""
        session = credentials.get("_session")
        if session is None:
            logger.warning("Semantic Scholar: no aiohttp session provided")
            return []

        url = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"

        params = [
            f"query={self._encode_query(query)}",
            "fields=title,authors,year,abstract,openAccessPdf,externalIds",
            f"limit={limit}",
        ]

        headers = {"Accept": "application/json"}
        api_key = credentials.get("api_key")
        if api_key:
            headers["x-api-key"] = api_key

        url_with_params = f"{url}?{'&'.join(params)}"
        papers: list[PaperMetadata] = []

        try:
            async with session.get(url_with_params, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    for item in data.get("data", []):
                        paper = self._parse_paper(item)
                        if paper and paper.year >= year_min:
                            papers.append(paper)
                else:
                    error_text = await response.text()
                    logger.warning("Semantic Scholar API error (status=%d): %s", response.status, error_text)
        except aiohttp.ClientError as e:
            logger.warning("Semantic Scholar API request failed: %s", e)

        logger.info("Semantic Scholar: found %d papers for query '%s'", len(papers), query)
        return papers

    async def fetch_pdf(
        self,
        paper: PaperMetadata,
        credentials: dict[str, str],
        session: Any = None,
    ) -> bytes | None:
        """Fetch PDF from Semantic Scholar open access PDF URL."""
        if paper.source != "semantic_scholar" or not paper.pdf_url:
            return None
        if session is None:
            return None
        try:
            async with session.get(paper.pdf_url) as response:
                if response.status == 200:
                    return await response.read()
        except aiohttp.ClientError as e:
            logger.debug("Semantic Scholar PDF download failed: %s", e)
        return None

    def _parse_paper(self, data: dict[str, Any]) -> PaperMetadata | None:
        """Parse a Semantic Scholar paper response."""
        try:
            external_ids = data.get("externalIds", {})
            doi = external_ids.get("DOI") or external_ids.get("DBLP")

            pdf_info = data.get("openAccessPdf")
            pdf_url = None
            if pdf_info and isinstance(pdf_info, dict):
                pdf_url = pdf_info.get("url")

            authors = [
                author.get("name", "")
                for author in data.get("authors", [])
                if author.get("name")
            ]

            return PaperMetadata(
                paper_id=data.get("paperId", ""),
                doi=doi,
                title=data.get("title", ""),
                authors=authors,
                year=data.get("year", 0),
                abstract=data.get("abstract"),
                pdf_url=pdf_url,
                source="semantic_scholar",
            )
        except Exception as e:
            logger.debug("Failed to parse Semantic Scholar paper: %s", e)
            return None

    def _encode_query(self, query: str) -> str:
        """URL encode a query string."""
        return query.replace(" ", "+")
