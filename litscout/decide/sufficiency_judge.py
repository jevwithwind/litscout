"""litscout.decide.sufficiency_judge — Check if enough papers have been collected."""

import json
import logging
from typing import Any

from litscout.llm_client import LLMClient

logger = logging.getLogger(__name__)


class SufficiencyJudge:
    """Check if the collected papers are sufficient for the research."""

    def __init__(
        self,
        llm_client: LLMClient,
        sufficiency_prompt_file: str = "prompts/sufficiency.md",
    ):
        self.llm_client = llm_client
        self.sufficiency_prompt_file = sufficiency_prompt_file

    def _load_sufficiency_prompt(self) -> str:
        """Load the sufficiency checking prompt."""
        with open(self.sufficiency_prompt_file, "r", encoding="utf-8") as f:
            return f.read()

    def _check_thresholds(
        self, manifest: list[dict[str, Any]], config: dict[str, Any]
    ) -> tuple[bool, str]:
        """Check if threshold-based conditions are met.

        Args:
            manifest: List of paper entries from manifest.
            config: Configuration dict with sufficiency settings.

        Returns:
            Tuple of (thresholds_met, reason).
        """
        sufficiency_config = config.get("sufficiency", {})

        # Count kept papers by relevance
        kept = [p for p in manifest if p.get("kept")]
        high_relevance = [p for p in kept if p.get("relevance") == "high"]
        medium_relevance = [p for p in kept if p.get("relevance") == "medium"]

        # Max iterations check is handled in main.py loop

        # Check target kept papers
        target_kept = sufficiency_config.get("target_kept_papers", 0)
        if target_kept > 0 and len(kept) >= target_kept:
            return True, f"Target kept papers ({target_kept}) reached"

        # Check min high relevance
        min_high = sufficiency_config.get("min_high_relevance", 0)
        if min_high > 0 and len(high_relevance) >= min_high:
            return True, f"Min high relevance ({min_high}) reached"

        # Check min medium relevance
        min_medium = sufficiency_config.get("min_medium_relevance", 0)
        if min_medium > 0 and len(medium_relevance) >= min_medium:
            return True, f"Min medium relevance ({min_medium}) reached"

        return False, f"Thresholds not met: {len(kept)} kept ({len(high_relevance)} high, {len(medium_relevance)} medium)"

    async def _check_with_llm(
        self,
        manifest: list[dict[str, Any]],
        research_angle: str,
        sufficiency_prompt: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Use LLM to check sufficiency.

        Args:
            manifest: List of paper entries from manifest.
            research_angle: The user's research angle.
            sufficiency_prompt: The sufficiency checking prompt.
            config: Configuration dict.

        Returns:
            LLM response dict with is_sufficient, reasoning, gaps, etc.
        """
        # Build context about collected papers
        papers_context = ""
        for paper in manifest[:30]:  # Limit to 30 for token budget
            papers_context += f"- {paper.get('title', 'Unknown')} ({paper.get('year', 'N/A')}) - {paper.get('relevance', 'N/A')}\n"

        # Build threshold context
        sufficiency_config = config.get("sufficiency", {})
        thresholds = f"""Target kept papers: {sufficiency_config.get('target_kept_papers', 0)}
Min high relevance: {sufficiency_config.get('min_high_relevance', 0)}
Min medium relevance: {sufficiency_config.get('min_medium_relevance', 0)}"""

        user_content = f"""# Research Angle
{research_angle}

---

# Collected Papers
{papers_context}

---

# Threshold Targets
{thresholds}

Please assess whether the collected papers are sufficient for the research angle.
"""

        messages = [
            {"role": "system", "content": sufficiency_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            response = await self.llm_client.complete(messages, response_format="json")
            return json.loads(response)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("LLM sufficiency check failed: %s", e)
            return {
                "is_sufficient": False,
                "confidence": 0.0,
                "reasoning": f"LLM check failed: {e}",
                "gaps": [],
                "suggestion": "Continue searching",
            }

    async def check_sufficiency(
        self,
        manifest: list[dict[str, Any]],
        config: dict[str, Any],
        research_angle: str,
    ) -> dict[str, Any]:
        """Check if the collected papers are sufficient.

        Args:
            manifest: List of paper entries from manifest.
            config: Configuration dict.
            research_angle: The user's research angle.

        Returns:
            Dict with should_stop, reason, gaps, and other info.
        """
        sufficiency_config = config.get("sufficiency", {})

        # Check thresholds first
        thresholds_met, reason = self._check_thresholds(manifest, config)

        if not thresholds_met:
            return {
                "should_stop": False,
                "reason": reason,
                "gaps": [],
                "confidence": 0.0,
            }

        # Load prompts
        sufficiency_prompt = self._load_sufficiency_prompt()

        # Use LLM for qualitative assessment
        llm_result = await self._check_with_llm(
            manifest, research_angle, sufficiency_prompt, config
        )

        is_sufficient = llm_result.get("is_sufficient", False)
        confidence = llm_result.get("confidence", 0.0)
        reasoning = llm_result.get("reasoning", "")
        gaps = llm_result.get("gaps", [])

        # Be conservative: if confidence is low, don't stop
        if confidence < 0.7:
            return {
                "should_stop": False,
                "reason": f"Low confidence ({confidence:.2f}): {reasoning}",
                "gaps": gaps,
                "confidence": confidence,
            }

        if is_sufficient:
            return {
                "should_stop": True,
                "reason": f"Sufficient papers collected: {reasoning}",
                "gaps": gaps,
                "confidence": confidence,
            }
        else:
            return {
                "should_stop": False,
                "reason": f"Not sufficient: {reasoning}",
                "gaps": gaps,
                "confidence": confidence,
            }
