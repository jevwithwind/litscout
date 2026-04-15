"""litscout.download.pdf_fetcher — Async PDF downloads with Elsevier fallback."""

import asyncio
import logging
import os
import re
from typing import Any

import aiohttp

from litscout.search.scholar_client import PaperMetadata

logger = logging.getLogger(__name__)


class PDFFetcher:
    """Fetch PDFs from academic sources with fallback mechanisms."""

    def __init__(
        self,
        elsevier_api_key: str | None = None,
        elsevier_inst_token: str | None = None,
        elsevier_enabled: bool = True,
        concurrency: int = 5,
        timeout: int = 60,
        max_pdf_size_mb: int = 50,
    ):
        self.elsevier_api_key = elsevier_api_key
        self.elsevier_inst_token = elsevier_inst_token
        self.elsevier_enabled = elsevier_enabled
        self.concurrency = concurrency
        self.timeout = timeout
        self.max_pdf_size_mb = max_pdf_size_mb

        self._session: aiohttp.ClientSession | None = None
        self._semaphore: asyncio.Semaphore | None = None

    async def __aenter__(self) -> "PDFFetcher":
        self._session = aiohttp.ClientSession()
        self._semaphore = asyncio.Semaphore(self.concurrency)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._session:
            await self._session.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    def _get_elsevier_headers(self) -> dict[str, str]:
        """Build Elsevier API headers."""
        headers = {
            "Accept": "application/pdf",
            "X-ELS-APIKey": self.elsevier_api_key or "",
        }
        if self.elsevier_inst_token:
            headers["X-ELS-Insttoken"] = self.elsevier_inst_token
        return headers

    async def _fetch_pdf_from_url(
        self, url: str, paper: PaperMetadata, temp_dir: str
    ) -> tuple[str | None, bool]:
        """Fetch PDF from a URL.

        Args:
            url: The PDF URL to fetch.
            paper: Paper metadata for logging.
            temp_dir: Temporary directory to save the PDF.

        Returns:
            Tuple of (local_path or None, success).
        """
        session = await self._get_session()

        try:
            async with self._semaphore:
                async with session.get(url, timeout=self.timeout) as response:
                    # Check content length
                    content_length = response.headers.get("Content-Length")
                    if content_length:
                        size_mb = int(content_length) / (1024 * 1024)
                        if size_mb > self.max_pdf_size_mb:
                            logger.warning(
                                "Skipping %s: PDF size %.2f MB exceeds limit of %d MB",
                                paper.title or "Untitled",
                                size_mb,
                                self.max_pdf_size_mb,
                            )
                            return None, False

                    # Check content type
                    content_type = response.headers.get("Content-Type", "")
                    if "pdf" not in content_type.lower() and "application/octet-stream" not in content_type.lower():
                        logger.debug(
                            "URL %s is not a PDF (Content-Type: %s)",
                            url,
                            content_type,
                        )
                        return None, False

                    # Read content
                    content = await response.read()

                    # Generate filename from DOI or title
                    if paper.doi:
                        filename = re.sub(r"[^\w]", "_", paper.doi) + ".pdf"
                    else:
                        filename = re.sub(r"[^\w]", "_", (paper.title or "Untitled")[:50]) + ".pdf"

                    local_path = os.path.join(temp_dir, filename)

                    # Save PDF
                    with open(local_path, "wb") as f:
                        f.write(content)

                    logger.info(
                        "Downloaded PDF for '%s' from %s",
                        (paper.title or "Untitled")[:50],
                        url[:50],
                    )
                    return local_path, True

        except asyncio.TimeoutError:
            logger.warning("Timeout downloading PDF for %s", paper.title or "Untitled")
            return None, False
        except aiohttp.ClientError as e:
            logger.warning("Failed to download PDF for %s: %s", paper.title or "Untitled", e)
            return None, False
        except IOError as e:
            logger.error("Failed to save PDF for %s: %s", paper.title or "Untitled", e)
            return None, False

    async def _fetch_from_elsevier(
        self, paper: PaperMetadata, temp_dir: str
    ) -> tuple[str | None, bool]:
        """Fetch PDF from Elsevier ScienceDirect API.

        Args:
            paper: Paper metadata with DOI.
            temp_dir: Temporary directory to save the PDF.

        Returns:
            Tuple of (local_path or None, success).
        """
        if not self.elsevier_enabled or not self.elsevier_api_key:
            return None, False

        if not paper.doi:
            return None, False

        session = await self._get_session()
        doi_encoded = paper.doi.replace("/", "%2F")
        url = f"https://api.elsevier.com/content/article/doi/{doi_encoded}"

        try:
            async with self._semaphore:
                async with session.get(
                    url,
                    headers=self._get_elsevier_headers(),
                    timeout=self.timeout,
                ) as response:
                    if response.status == 200:
                        content = await response.read()

                        # Generate filename
                        filename = re.sub(r"[^\w]", "_", paper.doi) + ".pdf"
                        local_path = os.path.join(temp_dir, filename)

                        with open(local_path, "wb") as f:
                            f.write(content)

                        logger.info(
                            "Downloaded PDF for '%s' from Elsevier",
                            (paper.title or "Untitled")[:50],
                        )
                        return local_path, True
                    elif response.status == 404:
                        logger.debug(
                            "Elsevier: Paper not found (404) for %s",
                            paper.doi,
                        )
                        return None, False
                    else:
                        logger.debug(
                            "Elsevier: API returned status %d for %s",
                            response.status,
                            paper.doi,
                        )
                        return None, False

        except asyncio.TimeoutError:
            logger.warning("Timeout fetching Elsevier PDF for %s", paper.title or "Untitled")
            return None, False
        except aiohttp.ClientError as e:
            logger.debug("Elsevier API request failed for %s: %s", paper.title or "Untitled", e)
            return None, False

    async def fetch_pdf(
        self, paper: PaperMetadata, temp_dir: str
    ) -> dict[str, Any]:
        """Fetch a single paper's PDF.

        Args:
            paper: PaperMetadata with PDF URL and DOI.
            temp_dir: Temporary directory to save the PDF.

        Returns:
            Dict with metadata, local_path, and success flag.
        """
        result: dict[str, Any] = {
            "metadata": paper,
            "local_path": None,
            "success": False,
        }

        # Priority 1: Open-access PDF URL from metadata
        if paper.pdf_url:
            local_path, success = await self._fetch_pdf_from_url(
                paper.pdf_url, paper, temp_dir
            )
            if success and local_path:
                result["local_path"] = local_path
                result["success"] = True
                return result

        # Priority 2: Elsevier ScienceDirect API fallback
        if paper.doi:
            local_path, success = await self._fetch_from_elsevier(paper, temp_dir)
            if success and local_path:
                result["local_path"] = local_path
                result["success"] = True
                return result

        logger.warning(
            "Could not download PDF for '%s' (no open-access URL, Elsevier fallback unavailable)",
            (paper.title or "Untitled")[:50],
        )
        return result

    async def fetch_pdfs(
        self, papers: list[PaperMetadata], temp_dir: str
    ) -> list[dict[str, Any]]:
        """Fetch multiple papers' PDFs concurrently.

        Args:
            papers: List of PaperMetadata objects.
            temp_dir: Temporary directory to save the PDFs.

        Returns:
            List of result dicts with metadata, local_path, and success flag.
        """
        if not papers:
            return []

        # Ensure temp directory exists
        os.makedirs(temp_dir, exist_ok=True)

        # Create tasks for all papers
        tasks = [self.fetch_pdf(paper, temp_dir) for paper in papers]

        # Run with semaphore for concurrency control
        results = await asyncio.gather(*tasks)

        # Log summary
        successful = sum(1 for r in results if r["success"])
        logger.info(
            "Downloaded %d/%d PDFs",
            successful,
            len(papers),
        )

        return results
