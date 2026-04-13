"""litscout.search.scholar_client — Unified academic search client."""

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


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
    source: str  # "semantic_scholar" | "openalex"


class ScholarClient:
    """Unified search client for Semantic Scholar and OpenAlex APIs."""

    def __init__(
        self,
        s2_api_key: str | None = None,
        openalex_email: str | None = None,
        sources: list[str] | None = None,
    ):
        self.s2_api_key = s2_api_key
        self.openalex_email = openalex_email
        self.sources = sources or ["semantic_scholar", "openalex"]

        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "ScholarClient":
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._session:
            await self._session.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    def _build_s2_headers(self) -> dict[str, str]:
        """Build Semantic Scholar API headers."""
        headers = {"Accept": "application/json"}
        if self.s2_api_key:
            headers["x-api-key"] = self.s2_api_key
        return headers

    def _build_openalex_url(self, query: str, year_min: int, limit: int) -> str:
        """Build OpenAlex API URL."""
        base = "https://api.openalex.org/works"
        params = [
            f"search={self._encode_query(query)}",
            f"filter=publication_year:>={year_min},open_access.is_oa:true",
            f"per_page={limit}",
        ]
        if self.openalex_email:
            params.append(f"mailto={self._encode_query(self.openalex_email)}")
        return f"{base}?{'&'.join(params)}"

    def _encode_query(self, query: str) -> str:
        """URL encode a query string."""
        return query.replace(" ", "+")

    async def _search_semantic_scholar(
        self, query: str, limit: int, year_min: int
    ) -> list[PaperMetadata]:
        """Search Semantic Scholar API."""
        session = await self._get_session()
        url = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"

        params = [
            f"query={self._encode_query(query)}",
            "fields=title,authors,year,abstract,openAccessPdf,externalIds",
            f"limit={limit}",
        ]

        headers = self._build_s2_headers()
        url_with_params = f"{url}?{'&'.join(params)}"

        papers: list[PaperMetadata] = []

        try:
            async with session.get(url_with_params, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    for item in data.get("data", []):
                        paper = self._parse_s2_paper(item)
                        if paper and paper.year >= year_min:
                            papers.append(paper)
                else:
                    error_text = await response.text()
                    logger.warning(
                        "Semantic Scholar API error (status=%d): %s",
                        response.status,
                        error_text,
                    )
        except aiohttp.ClientError as e:
            logger.warning("Semantic Scholar API request failed: %s", e)

        logger.info(
            "Semantic Scholar: found %d papers for query '%s'",
            len(papers),
            query,
        )
        return papers

    def _parse_s2_paper(self, data: dict[str, Any]) -> PaperMetadata | None:
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

    async def _search_openalex(
        self, query: str, limit: int, year_min: int
    ) -> list[PaperMetadata]:
        """Search OpenAlex API."""
        session = await self._get_session()
        url = self._build_openalex_url(query, year_min, limit)

        papers: list[PaperMetadata] = []

        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get("results", [])

                    for item in results:
                        paper = self._parse_openalex_paper(item)
                        if paper and paper.year >= year_min:
                            papers.append(paper)
                else:
                    error_text = await response.text()
                    logger.warning(
                        "OpenAlex API error (status=%d): %s",
                        response.status,
                        error_text,
                    )
        except aiohttp.ClientError as e:
            logger.warning("OpenAlex API request failed: %s", e)

        logger.info(
            "OpenAlex: found %d papers for query '%s'",
            len(papers),
            query,
        )
        return papers

    def _parse_openalex_paper(self, data: dict[str, Any]) -> PaperMetadata | None:
        """Parse an OpenAlex paper response."""
        try:
            # Extract DOI from openalex_id
            openalex_id = data.get("id", "")
            doi = None
            if openalex_id.startswith("https://openalex.org/"):
                doi = openalex_id.replace("https://openalex.org/", "https://doi.org/")

            # Get primary DOI from external_ids
            external_ids = data.get("external_ids", {})
            if not doi:
                for ext_id in external_ids.get("DOI", []):
                    doi = ext_id.get("id")
                    if doi:
                        break

            # Get PDF URL from open_access
            open_access = data.get("open_access", {})
            pdf_url = open_access.get("oa_url")

            # Get authors
            authors = [
                author.get("display_name", "")
                for author in data.get("authorships", [])
                if author.get("display_name")
            ]

            # Get year from publication_date
            publication_date = data.get("publication_date", "")
            year = 0
            if publication_date:
                try:
                    year = int(publication_date[:4])
                except (ValueError, IndexError):
                    pass

            return PaperMetadata(
                paper_id=openalex_id,
                doi=doi,
                title=data.get("display_name", ""),
                authors=authors,
                year=year,
                abstract=data.get("abstract"),
                pdf_url=pdf_url,
                source="openalex",
            )
        except Exception as e:
            logger.debug("Failed to parse OpenAlex paper: %s", e)
            return None

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

        # Search each source
        for source in self.sources:
            if source == "semantic_scholar":
                papers = await self._search_semantic_scholar(query, limit, year_min)
            elif source == "openalex":
                papers = await self._search_openalex(query, limit, year_min)
            else:
                logger.warning("Unknown source: %s", source)
                continue

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
