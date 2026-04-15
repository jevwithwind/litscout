"""litscout.sources.pubmed — PubMed/NCBI biomedical search source."""

import logging
import xml.etree.ElementTree as ET
from typing import Any

import aiohttp

from litscout.sources.base import PaperMetadata, ScholarSource

logger = logging.getLogger(__name__)


class PubMedSource(ScholarSource):
    """PubMed/NCBI biomedical search source.

    Free, optional API key for higher rate limits (10 req/sec vs 3 req/sec).
    Biomedical and life sciences literature (36M+ citations).
    Docs: https://www.ncbi.nlm.nih.gov/books/NBK25497/
    """

    @classmethod
    def name(cls) -> str:
        return "pubmed"

    async def search(
        self,
        query: str,
        limit: int,
        year_min: int,
        credentials: dict[str, str],
    ) -> list[PaperMetadata]:
        """Two-step: esearch for IDs, then efetch for metadata."""
        session = credentials.get("_session")
        if session is None:
            logger.warning("PubMed: no aiohttp session provided")
            return []

        api_key = credentials.get("api_key")

        # Step 1: Search for IDs
        esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        esearch_params = {
            "db": "pubmed",
            "term": query,
            "retmax": limit,
            "retmode": "json",
            "mindate": str(year_min),
            "datetype": "pdat",
        }
        if api_key:
            esearch_params["api_key"] = api_key

        paper_ids: list[str] = []
        try:
            async with session.get(esearch_url, params=esearch_params, timeout=60) as response:
                if response.status == 200:
                    data = await response.json()
                    paper_ids = data.get("esearchresult", {}).get("idlist", [])
                else:
                    logger.warning("PubMed esearch error (status=%d)", response.status)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning("PubMed esearch request failed: %s", e)

        if not paper_ids:
            return []

        # Step 2: Fetch details
        efetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        efetch_params = {
            "db": "pubmed",
            "id": ",".join(paper_ids),
            "retmode": "xml",
        }
        if api_key:
            efetch_params["api_key"] = api_key

        papers: list[PaperMetadata] = []

        try:
            async with session.get(efetch_url, params=efetch_params, timeout=60) as response:
                if response.status == 200:
                    content = await response.text()
                    papers = self._parse_xml(content)
                else:
                    logger.warning("PubMed efetch error (status=%d)", response.status)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning("PubMed efetch request failed: %s", e)

        logger.info("PubMed: found %d papers for query '%s'", len(papers), query)
        return papers

    async def fetch_pdf(
        self,
        paper: PaperMetadata,
        credentials: dict[str, str],
        session: Any = None,
    ) -> bytes | None:
        """Try PMC for free PDF. Returns None if not in PMC."""
        if not paper.doi or session is None:
            return None

        # Check if paper is in PubMed Central
        idconv_url = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
        idconv_params = {
            "ids": paper.doi,
            "format": "json",
        }

        try:
            async with session.get(idconv_url, params=idconv_params, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    records = data.get("records", [])
                    if records:
                        record = records[0]
                        pmcid = record.get("pmcid")
                        if pmcid:
                            # Construct PMC PDF URL
                            pmc_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"
                            async with session.get(pmc_url) as pdf_response:
                                if pdf_response.status == 200:
                                    return await pdf_response.read()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.debug("PMC lookup failed: %s", e)

        return None

    def _parse_xml(self, xml_content: str) -> list[PaperMetadata]:
        """Parse PubMed XML response."""
        papers: list[PaperMetadata] = []

        try:
            root = ET.fromstring(xml_content)
            namespace = {"pm": "http://www.ncbi.nlm.nih.gov"}

            for article in root.findall(".//PubmedArticle"):
                medline_citation = article.find(".//MedlineCitation")
                if medline_citation is None:
                    continue

                # Title
                title_elem = medline_citation.find(".//Article/ArticleTitle")
                title = title_elem.text.strip() if title_elem is not None else ""

                # Authors
                authors = []
                for author in medline_citation.findall(".//Author"):
                    last_name = author.find("LastName")
                    fore_name = author.find("ForeName")
                    if last_name is not None and last_name.text:
                        author_name = last_name.text
                        if fore_name is not None and fore_name.text:
                            author_name = f"{fore_name.text} {author_name}"
                        authors.append(author_name)

                # Year
                year = 0
                pub_date = medline_citation.find(".//Article/ArticleDate")
                if pub_date is not None:
                    year_elem = pub_date.find("Year")
                    if year_elem is not None and year_elem.text:
                        try:
                            year = int(year_elem.text)
                        except ValueError:
                            pass

                # DOI
                doi = None
                article_id_list = article.find(".//ArticleIdList")
                if article_id_list is not None:
                    for article_id in article_id_list.findall("ArticleId"):
                        if article_id.get("IdType") == "doi":
                            doi = article_id.text
                            break

                # Abstract
                abstract_elem = medline_citation.find(".//Abstract/AbstractText")
                abstract = abstract_elem.text.strip() if abstract_elem is not None else ""

                papers.append(PaperMetadata(
                    paper_id="",
                    doi=doi,
                    title=title,
                    authors=authors,
                    year=year,
                    abstract=abstract,
                    pdf_url=None,
                    source="pubmed",
                ))
        except ET.ParseError as e:
            logger.debug("Failed to parse PubMed XML: %s", e)

        return papers
