"""litscout.llm_client — Async LLM API client with retry logic."""

import asyncio
import logging
import os
import time
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


class LLMClient:
    """Async OpenAI-compatible API client with exponential backoff retry."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        max_tokens: int = 16384,
        temperature: float = 0.3,
        max_concurrent_requests: int = 3,
        timeout: int = 120,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_concurrent_requests = max_concurrent_requests
        self.timeout = timeout
        self.max_retries = max_retries

        self._semaphore = asyncio.Semaphore(max_concurrent_requests)
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "LLMClient":
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

    def _build_url(self) -> str:
        """Build the completions endpoint URL."""
        return f"{self.base_url}/chat/completions"

    def _build_headers(self) -> dict[str, str]:
        """Build request headers."""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _build_payload(
        self, messages: list[dict[str, str]], response_format: str = "text"
    ) -> dict[str, Any]:
        """Build the request payload."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}
        return payload

    async def _make_request(
        self, messages: list[dict[str, str]], response_format: str = "text"
    ) -> str:
        """Make a single API request with error handling."""
        session = await self._get_session()
        url = self._build_url()
        headers = self._build_headers()
        payload = self._build_payload(messages, response_format)

        async with self._semaphore:
            for attempt in range(1, self.max_retries + 1):
                try:
                    async with session.post(
                        url,
                        headers=headers,
                        json=payload,
                        timeout=self.timeout,
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            content = data["choices"][0]["message"]["content"]
                            # Log token usage if available
                            if "usage" in data:
                                usage = data["usage"]
                                logger.debug(
                                    "Token usage: prompt=%d, completion=%d, total=%d",
                                    usage.get("prompt_tokens", 0),
                                    usage.get("completion_tokens", 0),
                                    usage.get("total_tokens", 0),
                                )
                            return content
                        elif response.status in (429, 500, 502, 503):
                            # Rate limit or server error - retry
                            wait_time = 2 ** (attempt - 1)
                            logger.warning(
                                "LLM request failed (status=%d), retrying in %ds...",
                                response.status,
                                wait_time,
                            )
                            await asyncio.sleep(wait_time)
                        else:
                            # Non-retryable error
                            error_text = await response.text()
                            raise RuntimeError(
                                f"LLM API error (status={response.status}): {error_text}"
                            )
                except aiohttp.ClientError as e:
                    if attempt < self.max_retries:
                        wait_time = 2 ** (attempt - 1)
                        logger.warning(
                            "Network error during LLM request, retrying in %ds: %s",
                            wait_time,
                            e,
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        raise RuntimeError(
                            f"LLM API request failed after {self.max_retries} attempts: {e}"
                        ) from e

        raise RuntimeError(
            f"LLM API request failed after {self.max_retries} attempts"
        )

    async def complete(
        self, messages: list[dict[str, str]], response_format: str = "text"
    ) -> str:
        """Send a completion request to the LLM with retry logic.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            response_format: "text" for plain text or "json" for JSON output.

        Returns:
            The LLM's response text.

        Raises:
            RuntimeError: If all retry attempts fail.
        """
        start_time = time.time()
        try:
            result = await self._make_request(messages, response_format)
            elapsed = time.time() - start_time
            logger.debug("LLM request completed in %.2fs", elapsed)
            return result
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"LLM request timed out after {self.timeout}s"
            ) from None
