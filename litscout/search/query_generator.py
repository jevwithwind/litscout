"""litscout.search.query_generator — LLM-powered query generation."""

import json
import logging
import os
from typing import Any

from litscout.llm_client import LLMClient

logger = logging.getLogger(__name__)


class QueryGenerator:
    """Generate academic search queries based on research angle."""

    def __init__(
        self,
        llm_client: LLMClient,
        research_angle_file: str = "prompts/research.md",
        query_gen_prompt_file: str = "prompts/query_gen.md",
    ):
        self.llm_client = llm_client
        self.research_angle_file = research_angle_file
        self.query_gen_prompt_file = query_gen_prompt_file

    def _load_file(self, path: str) -> str:
        """Load a text file."""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def _build_messages(
        self,
        research_angle: str,
        manifest_papers: list[dict[str, Any]],
        previous_queries: list[str],
        gap_analysis: str | None,
        num_queries: int,
    ) -> list[dict[str, str]]:
        """Build the messages for the LLM query generation request.

        Args:
            research_angle: The user's research angle text.
            manifest_papers: List of papers already found.
            previous_queries: List of queries already used.
            gap_analysis: Gap analysis from previous iteration (if any).
            num_queries: Number of queries to generate.

        Returns:
            List of message dicts for the LLM.
        """
        system_prompt = self._load_file(self.query_gen_prompt_file)

        # Build context about already-found papers
        papers_context = ""
        if manifest_papers:
            papers_context = "\n\n### Papers Already Found\n"
            for paper in manifest_papers[:20]:  # Limit to 20 for token budget
                papers_context += f"- {paper.get('title', 'Unknown')}\n"
                if paper.get("relevance"):
                    papers_context += f"  Relevance: {paper['relevance']}\n"

        # Build context about previous queries
        queries_context = ""
        if previous_queries:
            queries_context = "\n\n### Queries Already Used\n"
            for query in previous_queries[-10:]:  # Limit to 10 for token budget
                queries_context += f"- {query}\n"

        # Build gap analysis context
        gap_context = ""
        if gap_analysis:
            gap_context = f"\n\n### Previous Gap Analysis\n{gap_analysis}"

        user_content = f"""# Research Angle
{research_angle}

{papers_context}
{queries_context}
{gap_context}

Please generate {num_queries} new search queries that will find papers not yet discovered.
Focus on filling gaps in the current collection.

Respond with ONLY a JSON object in this exact format (no markdown fences, no preamble):

{{
  "queries": [
    "keyword combination one",
    "keyword combination two",
    "keyword combination three"
  ],
  "gap_analysis": "Brief explanation of what topics/methods are still missing from the collection and how these queries aim to fill those gaps."
}}
"""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

    async def generate(
        self,
        research_angle: str,
        manifest_papers: list[dict[str, Any]],
        previous_queries: list[str],
        gap_analysis: str | None = None,
        num_queries: int = 5,
    ) -> tuple[list[str], str]:
        """Generate search queries based on research angle.

        Args:
            research_angle: The user's research angle text.
            manifest_papers: List of papers already found.
            previous_queries: List of queries already used.
            gap_analysis: Gap analysis from previous iteration (if any).
            num_queries: Number of queries to generate.

        Returns:
            Tuple of (list of query strings, gap analysis text).
        """
        messages = self._build_messages(
            research_angle=research_angle,
            manifest_papers=manifest_papers,
            previous_queries=previous_queries,
            gap_analysis=gap_analysis,
            num_queries=num_queries,
        )

        try:
            response = await self.llm_client.complete(
                messages, response_format="json"
            )

            # Parse JSON response
            try:
                result = json.loads(response)
                queries = result.get("queries", [])
                gap_analysis_result = result.get("gap_analysis", "")

                logger.info(
                    "Generated %d new search queries",
                    len(queries),
                )

                return queries, gap_analysis_result

            except json.JSONDecodeError as e:
                logger.warning(
                    "Failed to parse query generation response as JSON: %s. "
                    "Raw response: %s",
                    e,
                    response[:200],
                )
                # Return fallback queries based on research angle keywords
                return self._generate_fallback_queries(research_angle), ""

        except Exception as e:
            logger.error("Query generation failed: %s", e)
            return self._generate_fallback_queries(research_angle), ""

    def _generate_fallback_queries(self, research_angle: str) -> list[str]:
        """Generate fallback queries from research angle keywords."""
        # Extract potential keywords from research angle
        keywords = []
        for line in research_angle.split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith(">"):
                # Simple keyword extraction: take words that are at least 4 chars
                words = [w.strip().lower() for w in line.split() if len(w) >= 4]
                keywords.extend(words)

        # Create simple query combinations
        queries = []
        if len(keywords) >= 2:
            queries.append(f"{keywords[0]} {keywords[1]}")
        if len(keywords) >= 3:
            queries.append(f"{keywords[0]} {keywords[2]}")
        if len(keywords) >= 4:
            queries.append(f"{keywords[1]} {keywords[3]}")

        # Add some generic fallbacks
        if len(queries) < 3:
            queries.append("literature review")
        if len(queries) < 3:
            queries.append("survey paper")

        return queries[:5]
