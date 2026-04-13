"""litscout.batcher — Token-aware batching of papers for LLM processing."""

import logging
from typing import Any

import tiktoken

logger = logging.getLogger(__name__)

# Use cl100k_base encoding as approximation for token counting
# This is the encoding used by GPT-4 and most modern OpenAI models
_ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens in a string using cl100k_base encoding.

    Args:
        text: The text to count tokens for.

    Returns:
        Approximate token count.
    """
    return len(_ENCODING.encode(text))


def create_batches(
    papers: list[dict[str, Any]],
    max_papers: int,
    max_tokens: int,
) -> list[list[dict[str, Any]]]:
    """Group papers into batches respecting token budget.

    Args:
        papers: List of paper dicts, each with:
            - "filename": str
            - "total_pages": int
            - "pages": list of {"page_num": int, "text": str}
        max_papers: Maximum number of papers per batch.
        max_tokens: Maximum total tokens per batch (safety ceiling).

    Returns:
        List of batches, where each batch is a list of paper dicts.

    Note:
        If a single paper exceeds the token budget, its pages are truncated
        to fit within the budget. A warning is logged.
    """
    if not papers:
        return []

    batches: list[list[dict[str, Any]]] = []
    current_batch: list[dict[str, Any]] = []
    current_batch_tokens = 0

    for paper in papers:
        paper_tokens = _count_paper_tokens(paper)

        # If adding this paper would exceed token budget
        if current_batch_tokens + paper_tokens > max_tokens:
            # If batch is not empty, finalize it
            if current_batch:
                batches.append(current_batch)
                current_batch = []
                current_batch_tokens = 0

            # If paper itself is too large, truncate it
            if paper_tokens > max_tokens:
                logger.warning(
                    "Paper '%s' has %d tokens, exceeding batch budget of %d. "
                    "Truncating to fit.",
                    paper["filename"],
                    paper_tokens,
                    max_tokens,
                )
                paper = _truncate_paper(paper, max_tokens)
                paper_tokens = _count_paper_tokens(paper)

        # If adding this paper would exceed paper limit
        if len(current_batch) >= max_papers:
            batches.append(current_batch)
            current_batch = []
            current_batch_tokens = 0

        current_batch.append(paper)
        current_batch_tokens += paper_tokens

    # Don't forget the last batch
    if current_batch:
        batches.append(current_batch)

    logger.info(
        "Created %d batches from %d papers (max %d papers/batch, %d tokens/batch)",
        len(batches),
        len(papers),
        max_papers,
        max_tokens,
    )
    return batches


def _count_paper_tokens(paper: dict[str, Any]) -> int:
    """Count tokens in a single paper.

    Args:
        paper: Paper dict with "pages" list.

    Returns:
        Total token count for the paper.
    """
    total = 0
    for page in paper.get("pages", []):
        total += count_tokens(page.get("text", ""))
    return total


def _truncate_paper(paper: dict[str, Any], max_tokens: int) -> dict[str, Any]:
    """Truncate a paper's pages to fit within token budget.

    Args:
        paper: Paper dict to truncate.
        max_tokens: Maximum tokens allowed.

    Returns:
        Truncated paper dict.
    """
    truncated = paper.copy()
    truncated["pages"] = []
    current_tokens = 0

    for page in paper.get("pages", []):
        page_tokens = count_tokens(page.get("text", ""))
        if current_tokens + page_tokens <= max_tokens:
            truncated["pages"].append(page)
            current_tokens += page_tokens
        else:
            # Truncate page text to fit
            remaining_tokens = max_tokens - current_tokens
            if remaining_tokens > 0:
                # Approximate truncation by character count
                # This is imprecise but works as a fallback
                page_text = page.get("text", "")
                # Rough estimate: 4 chars ≈ 1 token
                chars_to_keep = remaining_tokens * 4
                truncated_text = page_text[:chars_to_keep]
                truncated["pages"].append({
                    "page_num": page.get("page_num", 0),
                    "text": truncated_text + "\n[...truncated...]",
                })
            break

    return truncated
