"""litscout.sources.openalex — OpenAlex academic search source."""

import logging
from datetime import datetime
from typing import Any

import aiohttp

from litscout.sources.base import PaperMetadata, ScholarSource

logger = logging.getLogger(__name__)


class OpenAlexSource(ScholarSource):
    """OpenAlex academic search source.

    Free, no API key needed. Covers 250M+ scholarly works across all disciplines.
    Docs: https://docs.openalex.org/
    """

    @classmethod
    def name(cls) -> str:
        return "openalex"

    async def search(
        self,
        query: str,
        limit: int,
        year_min: int,
        credentials: dict[str, str],
    ) -> list[PaperMetadata]:
        """Search OpenAlex API for papers."""
        session = credentials.get("_session")
        if session is None:
            logger.warning("OpenAlex: no aiohttp session provided")
            return []

        base = "https://api.openalex.org/works"
        year_max = datetime.now().year
        params = [
            f"search={self._encode_query(query)}",
            f"filter=publication_year:{year_min}-{year_max},open_access.is_oa:true",
            f"per_page={limit}",
        ]
        email = credentials.get("email")
        if email:
            params.append(f"mailto={self._encode_query(email)}")

        url = f"{base}?{'&'.join(params)}"
        papers: list[PaperMetadata] = []

        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    for item in data.get("results", []):
                        paper = self._parse_paper(item)
                        if paper and paper.year >= year_min:
                            papers.append(paper)
                else:
                    error_text = await response.text()
                    logger.warning("OpenAlex API error (status=%d): %s", response.status, error_text)
        except aiohttp.ClientError as e:
            logger.warning("OpenAlex API request failed: %s", e)

        logger.info("OpenAlex: found %d papers for query '%s'", len(papers), query)
        return papers

    async def fetch_pdf(
        self,
        paper: PaperMetadata,
        credentials: dict[str, str],
        session: Any = None,
    ) -> bytes | None:
        """Fetch PDF from OpenAlex OA URL."""
        if paper.source != "openalex" or not paper.pdf_url:
            return None
        if session is None:
            return None
        try:
            async with session.get(paper.pdf_url) as response:
                if response.status == 200:
                    return await response.read()
        except aiohttp.ClientError as e:
            logger.debug("OpenAlex PDF download failed: %s", e)
        return None

    def _parse_paper(self, data: dict[str, Any]) -> PaperMetadata | None:
        """Parse an OpenAlex paper response."""
        try:
            openalex_id = data.get("id", "")
            doi = None
            if openalex_id.startswith("https://openalex.org/"):
                doi = openalex_id.replace("https://openalex.org/", "https://doi.org/")

            external_ids = data.get("external_ids", {})
            if not doi:
                for ext_id in external_ids.get("DOI", []):
                    doi = ext_id.get("id")
                    if doi:
                        break

            open_access = data.get("open_access", {})
            pdf_url = open_access.get("oa_url")

            authors = [
                author.get("display_name", "")
                for author in data.get("authorships", [])
                if author.get("display_name")
            ]

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

    def _encode_query(self, query: str) -> str:
        """URL encode a query string."""
        return query.replace(" ", "+")
