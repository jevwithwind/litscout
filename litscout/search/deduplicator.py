"""litscout.search.deduplicator — Track seen papers to avoid duplicates."""

import json
import logging
import os
import re
from typing import Any

from litscout.search.scholar_client import PaperMetadata

logger = logging.getLogger(__name__)


class Deduplicator:
    """Track seen paper identifiers to avoid duplicates across iterations."""

    def __init__(self, state_file: str = "output/deduplicator.json"):
        self.state_file = state_file
        self.seen_dois: set[str] = set()
        self.seen_paper_ids: dict[str, set[str]] = {}  # source -> set of IDs
        self._load_state()

    def _load_state(self) -> None:
        """Load state from file if it exists."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.seen_dois = set(data.get("seen_dois", []))
                    # Convert lists back to sets for each source
                    raw_paper_ids = data.get("seen_paper_ids", {})
                    self.seen_paper_ids = {
                        source: set(ids) for source, ids in raw_paper_ids.items()
                    }
                    logger.info(
                        "Loaded deduplicator state: %d seen DOIs, %d sources",
                        len(self.seen_dois),
                        len(self.seen_paper_ids),
                    )
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Failed to load deduplicator state: %s", e)
                self._reset_state()
        else:
            self._reset_state()

    def _reset_state(self) -> None:
        """Reset state to empty."""
        self.seen_dois = set()
        self.seen_paper_ids = {}

    def _save_state(self) -> None:
        """Save state to file."""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            data = {
                "seen_dois": list(self.seen_dois),
                "seen_paper_ids": {
                    source: list(ids) for source, ids in self.seen_paper_ids.items()
                },
            }
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            logger.warning("Failed to save deduplicator state: %s", e)

    def _normalize_title(self, title: str) -> str:
        """Normalize a title for comparison."""
        # Remove punctuation, convert to lowercase
        title = re.sub(r"[^\w\s]", "", title.lower())
        # Remove extra whitespace
        title = " ".join(title.split())
        return title

    def _title_similarity(self, title1: str, title2: str) -> float:
        """Calculate similarity between two titles (0.0 to 1.0)."""
        norm1 = self._normalize_title(title1)
        norm2 = self._normalize_title(title2)

        if not norm1 or not norm2:
            return 0.0

        # Simple Jaccard similarity on words
        words1 = set(norm1.split())
        words2 = set(norm2.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union)

    def is_new(self, paper: PaperMetadata) -> bool:
        """Check if a paper is new (not seen before).

        Args:
            paper: The paper to check.

        Returns:
            True if the paper is new, False if it's a duplicate.
        """
        # Check by DOI first (most reliable)
        if paper.doi and paper.doi in self.seen_dois:
            logger.debug("Paper %s is duplicate (DOI seen)", paper.doi)
            return False

        # Check by source-specific ID
        if paper.source in self.seen_paper_ids:
            if paper.paper_id in self.seen_paper_ids[paper.source]:
                logger.debug(
                    "Paper %s is duplicate (%s ID seen)",
                    paper.paper_id,
                    paper.source,
                )
                return False

        # Fallback: check title similarity (for papers without DOIs)
        for seen_paper in self._get_all_seen_papers():
            if seen_paper.doi is None and paper.doi is None:
                similarity = self._title_similarity(seen_paper.title, paper.title)
                if similarity > 0.9:
                    logger.debug(
                        "Paper '%s' is duplicate (title similarity: %.2f)",
                        paper.title,
                        similarity,
                    )
                    return False

        return True

    def _get_all_seen_papers(self) -> list[PaperMetadata]:
        """Get all seen papers for title comparison."""
        # This is a simplified version - in practice, we'd need to store
        # full paper metadata. For now, we'll just return an empty list
        # and rely on DOI/ID matching.
        return []

    def mark_seen(self, paper: PaperMetadata) -> None:
        """Mark a paper as seen.

        Args:
            paper: The paper to mark as seen.
        """
        if paper.doi:
            self.seen_dois.add(paper.doi)

        if paper.source not in self.seen_paper_ids:
            self.seen_paper_ids[paper.source] = set()
        self.seen_paper_ids[paper.source].add(paper.paper_id)

        self._save_state()
        logger.debug(
            "Marked paper %s as seen (source: %s)",
            paper.paper_id,
            paper.source,
        )

    def load_from_manifest(self, manifest: list[dict[str, Any]]) -> None:
        """Load seen papers from manifest.

        Args:
            manifest: List of paper entries from manifest.json.
        """
        for entry in manifest:
            doi = entry.get("doi")
            if doi:
                self.seen_dois.add(doi)

            source = entry.get("source")
            paper_id = entry.get("paper_id")
            if source and paper_id:
                if source not in self.seen_paper_ids:
                    self.seen_paper_ids[source] = set()
                self.seen_paper_ids[source].add(paper_id)

        logger.info(
            "Loaded %d seen papers from manifest",
            len(self.seen_dois) + sum(len(ids) for ids in self.seen_paper_ids.values()),
        )

    def clear(self) -> None:
        """Clear all seen papers (for fresh start)."""
        self._reset_state()
        self._save_state()
