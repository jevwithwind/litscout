"""litscout.sources.arxiv — arXiv preprint search source."""

import logging
import xml.etree.ElementTree as ET
from typing import Any

import aiohttp

from litscout.sources.base import PaperMetadata, ScholarSource

logger = logging.getLogger(__name__)


class ArxivSource(ScholarSource):
    """arXiv preprint search source.

    Free, no API key needed. Preprints in physics, math, CS, biology, economics.
    Docs: https://info.arxiv.org/help/api/index.html
    """

    @classmethod
    def name(cls) -> str:
        return "arxiv"

    async def search(
        self,
        query: str,
        limit: int,
        year_min: int,
        credentials: dict[str, str],
    ) -> list[PaperMetadata]:
        """Search arXiv API."""
        session = credentials.get("_session")
        if session is None:
            logger.warning("arXiv: no aiohttp session provided")
            return []

        url = "http://export.arxiv.org/api/query"
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": limit,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }

        papers: list[PaperMetadata] = []

        try:
            async with session.get(url, params=params, timeout=60) as response:
                if response.status == 200:
                    content = await response.text()
                    papers = self._parse_xml(content, year_min)
                else:
                    logger.warning("arXiv API error (status=%d)", response.status)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning("arXiv API request failed: %s", e)

        logger.info("arXiv: found %d papers for query '%s'", len(papers), query)
        return papers

    async def fetch_pdf(
        self,
        paper: PaperMetadata,
        credentials: dict[str, str],
        session: Any = None,
    ) -> bytes | None:
        """arXiv PDFs are always freely available."""
        if paper.source != "arxiv" or not paper.pdf_url:
            return None
        if session is None:
            return None
        try:
            async with session.get(paper.pdf_url) as response:
                if response.status == 200:
                    return await response.read()
        except aiohttp.ClientError as e:
            logger.debug("arXiv PDF download failed: %s", e)
        return None

    def _parse_xml(self, xml_content: str, year_min: int) -> list[PaperMetadata]:
        """Parse arXiv Atom XML response."""
        papers: list[PaperMetadata] = []

        try:
            root = ET.fromstring(xml_content)
            namespace = {"atom": "http://www.w3.org/2005/Atom"}

            for entry in root.findall("atom:entry", namespace):
                title_elem = entry.find("atom:title", namespace)
                title = title_elem.text.strip() if title_elem is not None else ""

                authors = []
                for author in entry.findall("atom:author", namespace):
                    name_elem = author.find("atom:name", namespace)
                    if name_elem is not None and name_elem.text:
                        authors.append(name_elem.text.strip())

                published_elem = entry.find("atom:published", namespace)
                year = 0
                if published_elem is not None and published_elem.text:
                    try:
                        year = int(published_elem.text[:4])
                    except (ValueError, IndexError):
                        pass

                if year < year_min:
                    continue

                id_elem = entry.find("atom:id", namespace)
                pdf_url = None
                if id_elem is not None and id_elem.text:
                    pdf_url = id_elem.text.replace("/abs/", "/pdf/") + ".pdf"

                abstract_elem = entry.find("atom:summary", namespace)
                abstract = abstract_elem.text.strip() if abstract_elem is not None else ""

                arxiv_id = ""
                if id_elem is not None and id_elem.text:
                    arxiv_id = id_elem.text.split("/")[-1]

                papers.append(PaperMetadata(
                    paper_id=arxiv_id,
                    doi=None,
                    title=title,
                    authors=authors,
                    year=year,
                    abstract=abstract,
                    pdf_url=pdf_url,
                    source="arxiv",
                ))
        except ET.ParseError as e:
            logger.debug("Failed to parse arXiv XML: %s", e)

        return papers
