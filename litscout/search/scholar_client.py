"""litscout.search.scholar_client — Unified academic search client."""

import asyncio
import logging
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
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
    source: str  # "semantic_scholar" | "openalex" | "arxiv" | "pubmed" | "core"


class ScholarClient:
    """Unified search client for multiple academic APIs."""

    def __init__(
        self,
        active_sources: list[dict[str, Any]] | None = None,
    ):
        self.active_sources = active_sources or []
        self._session: aiohttp.ClientSession | None = None

        # Search method dispatchers
        self._searchers = {
            "openalex": self._search_openalex,
            "semantic_scholar": self._search_semantic_scholar,
            "arxiv": self._search_arxiv,
            "pubmed": self._search_pubmed,
            "core": self._search_core,
        }

        # PDF fetcher dispatchers
        self._pdf_fetchers = {
            "openalex": self._fetch_pdf_openalex,
            "semantic_scholar": self._fetch_pdf_semantic_scholar,
            "elsevier": self._fetch_pdf_elsevier,
            "arxiv": self._fetch_pdf_arxiv,
            "pubmed": self._fetch_pdf_pubmed,
            "core": self._fetch_pdf_core,
        }

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

    async def _download_url(self, url: str, headers: dict[str, str] | None = None) -> bytes | None:
        """Download content from a URL."""
        session = await self._get_session()
        try:
            async with session.get(url, headers=headers or {}, timeout=60) as response:
                if response.status == 200:
                    return await response.read()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.debug("Failed to download from %s: %s", url, e)
        return None

    # ── OpenAlex ───────────────────────────────────────────────────────────────

    async def _search_openalex(
        self, query: str, limit: int, year_min: int, credentials: dict
    ) -> list[PaperMetadata]:
        """Search OpenAlex API."""
        session = await self._get_session()
        base = "https://api.openalex.org/works"
        params = [
            f"search={self._encode_query(query)}",
            f"filter=publication_year:>={year_min},open_access.is_oa:true",
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
                        paper = self._parse_openalex_paper(item)
                        if paper and paper.year >= year_min:
                            papers.append(paper)
                else:
                    error_text = await response.text()
                    logger.warning("OpenAlex API error (status=%d): %s", response.status, error_text)
        except aiohttp.ClientError as e:
            logger.warning("OpenAlex API request failed: %s", e)

        logger.info("OpenAlex: found %d papers for query '%s'", len(papers), query)
        return papers

    def _parse_openalex_paper(self, data: dict[str, Any]) -> PaperMetadata | None:
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

    async def _fetch_pdf_openalex(
        self, paper: PaperMetadata, credentials: dict
    ) -> bytes | None:
        """Fetch PDF from OpenAlex OA URL."""
        if paper.source == "openalex" and paper.pdf_url:
            return await self._download_url(paper.pdf_url)
        return None

    # ── Semantic Scholar ───────────────────────────────────────────────────────

    async def _search_semantic_scholar(
        self, query: str, limit: int, year_min: int, credentials: dict
    ) -> list[PaperMetadata]:
        """Search Semantic Scholar API."""
        session = await self._get_session()
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
                        paper = self._parse_s2_paper(item)
                        if paper and paper.year >= year_min:
                            papers.append(paper)
                else:
                    error_text = await response.text()
                    logger.warning("Semantic Scholar API error (status=%d): %s", response.status, error_text)
        except aiohttp.ClientError as e:
            logger.warning("Semantic Scholar API request failed: %s", e)

        logger.info("Semantic Scholar: found %d papers for query '%s'", len(papers), query)
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

    async def _fetch_pdf_semantic_scholar(
        self, paper: PaperMetadata, credentials: dict
    ) -> bytes | None:
        """Fetch PDF from Semantic Scholar open access PDF URL."""
        if paper.source == "semantic_scholar" and paper.pdf_url:
            return await self._download_url(paper.pdf_url)
        return None

    # ── Elsevier ───────────────────────────────────────────────────────────────

    async def _fetch_pdf_elsevier(
        self, paper: PaperMetadata, credentials: dict
    ) -> bytes | None:
        """Fetch PDF from Elsevier ScienceDirect API."""
        api_key = credentials.get("api_key")
        if not api_key:
            return None

        if not paper.doi:
            return None

        session = await self._get_session()
        doi_encoded = paper.doi.replace("/", "%2F")
        url = f"https://api.elsevier.com/content/article/doi/{doi_encoded}"

        headers = {
            "Accept": "application/pdf",
            "X-ELS-APIKey": api_key,
        }
        inst_token = credentials.get("inst_token")
        if inst_token:
            headers["X-ELS-Insttoken"] = inst_token

        try:
            async with session.get(url, headers=headers, timeout=60) as response:
                if response.status == 200:
                    content = await response.read()
                    logger.info("Elsevier: downloaded PDF for %s", paper.doi)
                    return content
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.debug("Elsevier API request failed: %s", e)

        return None

    # ── arXiv ──────────────────────────────────────────────────────────────────

    async def _search_arxiv(
        self, query: str, limit: int, year_min: int, credentials: dict
    ) -> list[PaperMetadata]:
        """Search arXiv API. Returns Atom XML, parse with xml.etree.ElementTree."""
        session = await self._get_session()
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
                    papers = self._parse_arxiv_xml(content, year_min)
                else:
                    logger.warning("arXiv API error (status=%d)", response.status)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning("arXiv API request failed: %s", e)

        logger.info("arXiv: found %d papers for query '%s'", len(papers), query)
        return papers

    def _parse_arxiv_xml(self, xml_content: str, year_min: int) -> list[PaperMetadata]:
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

                # Extract DOI fromarXiv ID
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

    async def _fetch_pdf_arxiv(
        self, paper: PaperMetadata, credentials: dict
    ) -> bytes | None:
        """arXiv PDFs are always freely available."""
        if paper.source == "arxiv" and paper.pdf_url:
            return await self._download_url(paper.pdf_url)
        return None

    # ── PubMed ─────────────────────────────────────────────────────────────────

    async def _search_pubmed(
        self, query: str, limit: int, year_min: int, credentials: dict
    ) -> list[PaperMetadata]:
        """Two-step: esearch for IDs, then efetch for metadata."""
        session = await self._get_session()
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
                    papers = self._parse_pubmed_xml(content)
                else:
                    logger.warning("PubMed efetch error (status=%d)", response.status)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning("PubMed efetch request failed: %s", e)

        logger.info("PubMed: found %d papers for query '%s'", len(papers), query)
        return papers

    def _parse_pubmed_xml(self, xml_content: str) -> list[PaperMetadata]:
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

    async def _fetch_pdf_pubmed(
        self, paper: PaperMetadata, credentials: dict
    ) -> bytes | None:
        """Try PMC for free PDF. Returns None if not in PMC."""
        if not paper.doi:
            return None

        session = await self._get_session()

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
                            return await self._download_url(pmc_url)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.debug("PMC lookup failed: %s", e)

        return None

    # ── CORE ───────────────────────────────────────────────────────────────────

    async def _search_core(
        self, query: str, limit: int, year_min: int, credentials: dict
    ) -> list[PaperMetadata]:
        """Search CORE API v3."""
        session = await self._get_session()
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
                        paper = self._parse_core_paper(item, year_min)
                        if paper:
                            papers.append(paper)
                else:
                    logger.warning("CORE API error (status=%d)", response.status)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning("CORE API request failed: %s", e)

        logger.info("CORE: found %d papers for query '%s'", len(papers), query)
        return papers

    def _parse_core_paper(self, data: dict[str, Any], year_min: int) -> PaperMetadata | None:
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

    async def _fetch_pdf_core(
        self, paper: PaperMetadata, credentials: dict
    ) -> bytes | None:
        """CORE often has direct download URLs for full text."""
        if paper.source == "core" and paper.pdf_url:
            return await self._download_url(paper.pdf_url)
        return None

    # ── Main search dispatcher ─────────────────────────────────────────────────

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

        # Search each active source
        for source_config in self.active_sources:
            source_name = source_config.get("name", "")
            credentials = source_config.get("credentials", {})

            if source_name not in self._searchers:
                logger.warning("Unknown source: %s", source_name)
                continue

            papers = await self._searchers[source_name](
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
        source = paper.source
        if source not in self._pdf_fetchers:
            logger.warning("No PDF fetcher for source: %s", source)
            return None

        return await self._pdf_fetchers[source](paper, credentials or {})

    def _encode_query(self, query: str) -> str:
        """URL encode a query string."""
        return query.replace(" ", "+")
