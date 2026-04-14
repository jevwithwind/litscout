"""litscout.screen.screener — Orchestrate paper screening with LLM."""

import asyncio
import json
import logging
import os
from typing import Any

from litscout.batcher import create_batches
from litscout.llm_client import LLMClient
from litscout.pdf_reader import extract_pages
from litscout.screen.prompt_builder import build_messages, count_batch_tokens

logger = logging.getLogger(__name__)


class Screener:
    """Orchestrate the paper screening pipeline."""

    def __init__(
        self,
        llm_client: LLMClient,
        screening_prompt_file: str = "prompts/screening.md",
        batch_size: int = 10,
        max_tokens_per_batch: int = 200000,
    ):
        self.llm_client = llm_client
        self.screening_prompt_file = screening_prompt_file
        self.batch_size = batch_size
        self.max_tokens_per_batch = max_tokens_per_batch

    def _load_screening_prompt(self) -> str:
        """Load the screening system prompt."""
        with open(self.screening_prompt_file, "r", encoding="utf-8") as f:
            return f.read()

    def _load_research_angle(self, prompt_file: str) -> str:
        """Load the research angle from file."""
        with open(prompt_file, "r", encoding="utf-8") as f:
            return f.read()

    def _extract_paper_text(self, pdf_path: str) -> dict[str, Any]:
        """Extract text from a PDF file.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            Paper dict with filename, total_pages, and pages.
        """
        filename = os.path.basename(pdf_path)
        result = extract_pages(pdf_path)

        if not result["success"]:
            logger.warning(
                "Failed to extract text from %s: %s",
                filename,
                result.get("error", "Unknown error"),
            )
            return {
                "filename": filename,
                "total_pages": 0,
                "pages": [],
                "error": result.get("error"),
            }

        return {
            "filename": filename,
            "total_pages": result["total_pages"],
            "pages": result["pages"],
        }

    async def _screen_batch(
        self,
        batch: list[dict[str, Any]],
        research_angle: str,
        screening_prompt: str,
    ) -> list[dict[str, Any]]:
        """Screen a batch of papers using the LLM.

        Args:
            batch: List of paper dicts.
            research_angle: The user's research angle.
            screening_prompt: The system prompt for screening.

        Returns:
            List of evaluation results.
        """
        messages = build_messages(
            research_angle=research_angle,
            screening_prompt=screening_prompt,
            batch=batch,
        )

        try:
            response = await self.llm_client.complete(
                messages, response_format="json"
            )

            # Parse JSON response
            try:
                evaluations = json.loads(response)

                # Ensure we got a list
                if not isinstance(evaluations, list):
                    logger.warning(
                        "LLM response is not a list, treating as malformed"
                    )
                    return self._create_malformed_evaluations(batch)

                # Validate each evaluation
                validated = []
                for i, eval_result in enumerate(evaluations):
                    if not isinstance(eval_result, dict):
                        logger.warning(
                            "Evaluation %d is not a dict, treating as low relevance",
                            i,
                        )
                        validated.append(self._create_low_relevance(batch[i]))
                    else:
                        validated.append(eval_result)

                logger.info(
                    "Screened %d papers in batch",
                    len(validated),
                )
                return validated

            except json.JSONDecodeError as e:
                logger.warning(
                    "Failed to parse screening response as JSON: %s. "
                    "Raw response: %s",
                    e,
                    response[:200],
                )
                return self._create_malformed_evaluations(batch)

        except Exception as e:
            logger.error("Batch screening failed: %s", e)
            return self._create_malformed_evaluations(batch)

    def _create_malformed_evaluations(
        self, batch: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Create low-relevance evaluations for a batch when LLM fails."""
        return [self._create_low_relevance(paper) for paper in batch]

    def _create_low_relevance(self, paper: dict[str, Any]) -> dict[str, Any]:
        """Create a low-relevance evaluation for a paper."""
        return {
            "filename": paper["filename"],
            "relevance": "low",
            "why_not_relevant": "LLM screening failed for this paper",
        }

    async def screen_papers(
        self,
        pdf_paths: list[dict[str, Any]],
        config: dict[str, Any],
        research_angle_file: str = "input/research.md",
    ) -> list[dict[str, Any]]:
        """Screen a list of papers.

        Args:
            pdf_paths: List of dicts with "local_path" and "metadata".
            config: Configuration dict with screening settings.
            research_angle_file: Path to the research angle file.

        Returns:
            List of evaluation results.
        """
        # Load prompts
        screening_prompt = self._load_screening_prompt()
        research_angle = self._load_research_angle(research_angle_file)

        # Extract text from each PDF
        papers = []
        for pdf_info in pdf_paths:
            local_path = pdf_info.get("local_path")
            if local_path and os.path.exists(local_path):
                paper = self._extract_paper_text(local_path)
                papers.append(paper)
            else:
                logger.warning(
                    "PDF not found: %s",
                    pdf_info.get("local_path", "unknown"),
                )

        if not papers:
            logger.warning("No papers to screen")
            return []

        # Create batches
        batches = create_batches(
            papers,
            max_papers=self.batch_size,
            max_tokens=self.max_tokens_per_batch,
        )

        logger.info(
            "Created %d batches for screening",
            len(batches),
        )

        # Screen each batch
        all_evaluations = []
        for batch in batches:
            evaluations = await self._screen_batch(
                batch, research_angle, screening_prompt
            )
            all_evaluations.extend(evaluations)

        logger.info(
            "Screened %d total papers",
            len(all_evaluations),
        )

        return all_evaluations
