"""litscout.sources.elsevier — Elsevier ScienceDirect PDF source."""

import asyncio
import logging
from typing import Any

import aiohttp

from litscout.sources.base import PaperMetadata, ScholarSource

logger = logging.getLogger(__name__)


class ElsevierSource(ScholarSource):
    """Elsevier ScienceDirect PDF source.

    Institutional access. Downloads paywalled papers your university subscribes to.
    Requires API key from https://dev.elsevier.com/
    """

    @classmethod
    def name(cls) -> str:
        return "elsevier"

    @classmethod
    def supports_search(cls) -> bool:
        """Elsevier is PDF-only, no search capability."""
        return False

    @classmethod
    def supports_pdf(cls) -> bool:
        return True

    async def search(
        self,
        query: str,
        limit: int,
        year_min: int,
        credentials: dict[str, str],
    ) -> list[PaperMetadata]:
        """Elsevier does not support search via this API."""
        return []

    async def fetch_pdf(
        self,
        paper: PaperMetadata,
        credentials: dict[str, str],
        session: Any = None,
    ) -> bytes | None:
        """Fetch PDF from Elsevier ScienceDirect API."""
        api_key = credentials.get("api_key")
        if not api_key:
            return None

        if not paper.doi:
            return None

        if session is None:
            return None

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
