"""litscout.screen.prompt_builder — Build screening prompts for LLM."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_messages(
    research_angle: str,
    screening_prompt: str,
    batch: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Build the messages for the LLM screening request.

    Args:
        research_angle: The user's research angle text.
        screening_prompt: The system prompt for screening.
        batch: List of paper dicts, each with:
            - "filename": str
            - "total_pages": int
            - "pages": list of {"page_num": int, "text": str}

    Returns:
        List of message dicts for the LLM.
    """
    # Build user content with research angle and papers
    user_content = f"""## Research Angle
{research_angle}

---

## Papers to Evaluate

"""

    for paper in batch:
        user_content += f"""--- PAPER: {paper['filename']} ({paper['total_pages']} pages) ---
"""

        for page in paper["pages"]:
            user_content += f"""
[Page {page['page_num']}]
{page['text']}
"""

    return [
        {"role": "system", "content": screening_prompt},
        {"role": "user", "content": user_content},
    ]


def format_paper_for_screening(paper: dict[str, Any]) -> str:
    """Format a single paper for inclusion in the screening prompt.

    Args:
        paper: Paper dict with filename, total_pages, and pages.

    Returns:
        Formatted string for the paper.
    """
    lines = [f"--- PAPER: {paper['filename']} ({paper['total_pages']} pages) ---"]

    for page in paper["pages"]:
        lines.append(f"\n[Page {page['page_num']}]")
        lines.append(page["text"])

    return "\n".join(lines)


def count_batch_tokens(batch: list[dict[str, Any]]) -> int:
    """Count approximate tokens in a batch of papers.

    Args:
        batch: List of paper dicts.

    Returns:
        Approximate token count.
    """
    # Simple estimation: 4 chars ≈ 1 token
    total_chars = 0
    for paper in batch:
        total_chars += len(paper.get("filename", ""))
        for page in paper.get("pages", []):
            total_chars += len(page.get("text", ""))

    # Add overhead for prompt structure (about 2000 tokens)
    overhead = 2000

    return total_chars // 4 + overhead
