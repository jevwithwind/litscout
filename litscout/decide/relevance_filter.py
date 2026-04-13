"""litscout.decide.relevance_filter — Parse LLM responses and split keep/discard."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def filter_results(
    evaluations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse LLM screening results and split into keep/discard.

    Args:
        evaluations: List of evaluation dicts from LLM.

    Returns:
        Tuple of (kept, discarded) where:
            - kept = high + medium relevance papers
            - discarded = low relevance papers
    """
    kept: list[dict[str, Any]] = []
    discarded: list[dict[str, Any]] = []

    for evaluation in evaluations:
        if not isinstance(evaluation, dict):
            logger.warning(
                "Invalid evaluation: expected dict, got %s",
                type(evaluation).__name__,
            )
            discarded.append(evaluation)
            continue

        relevance = evaluation.get("relevance", "").lower()

        if relevance in ("high", "medium"):
            kept.append(evaluation)
        elif relevance == "low":
            discarded.append(evaluation)
        else:
            logger.warning(
                "Unknown relevance rating '%s' for paper '%s', treating as low",
                relevance,
                evaluation.get("filename", "unknown"),
            )
            discarded.append(evaluation)

    logger.info(
        "Filter results: kept %d, discarded %d",
        len(kept),
        len(discarded),
    )

    return kept, discarded


def validate_evaluation(evaluation: dict[str, Any]) -> bool:
    """Validate an evaluation result structure.

    Args:
        evaluation: Evaluation dict to validate.

    Returns:
        True if valid, False otherwise.
    """
    if not isinstance(evaluation, dict):
        return False

    relevance = evaluation.get("relevance", "").lower()
    if relevance not in ("high", "medium", "low"):
        return False

    if not evaluation.get("filename"):
        return False

    if relevance in ("high", "medium"):
        required_fields = ["why_useful", "key_pages", "key_findings", "methodology"]
        for field in required_fields:
            if not evaluation.get(field):
                logger.warning(
                    "Missing required field '%s' for high/medium relevance paper",
                    field,
                )
                return False

    return True


def get_relevance_count(evaluations: list[dict[str, Any]]) -> dict[str, int]:
    """Count papers by relevance level.

    Args:
        evaluations: List of evaluation dicts.

    Returns:
        Dict with counts for high, medium, low, and total.
    """
    counts = {"high": 0, "medium": 0, "low": 0, "total": 0}

    for evaluation in evaluations:
        if not isinstance(evaluation, dict):
            continue

        relevance = evaluation.get("relevance", "").lower()
        if relevance in counts:
            counts[relevance] += 1
        counts["total"] += 1

    return counts
