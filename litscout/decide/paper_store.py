"""litscout.decide.paper_store — Copy keepers to output and update manifest."""

import json
import logging
import os
import shutil
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def store_papers(
    kept: list[dict[str, Any]],
    discarded: list[dict[str, Any]],
    iteration: int,
    config: dict[str, Any],
) -> None:
    """Store kept papers and update manifest.

    Args:
        kept: List of kept paper evaluations (high/medium relevance).
        discarded: List of discarded paper evaluations (low relevance).
        iteration: Current iteration number.
        config: Configuration dict with paths and settings.
    """
    # Get paths from config
    output_dir = config.get("paths", {}).get("output_dir", "output")
    kept_papers_dir = config.get("paths", {}).get("kept_papers_dir", "output/kept_papers")
    manifest_file = config.get("paths", {}).get("manifest_file", "output/manifest.json")

    # Ensure directories exist
    os.makedirs(kept_papers_dir, exist_ok=True)

    # Load existing manifest or create new
    manifest = _load_manifest(manifest_file)

    # Copy kept papers to output directory
    for evaluation in kept:
        # Find the original PDF path (from temp directory)
        # This assumes the filename matches
        filename = evaluation.get("filename", "")
        temp_path = os.path.join(config.get("paths", {}).get("temp_dir", "temp"), filename)

        if os.path.exists(temp_path):
            dest_path = os.path.join(kept_papers_dir, filename)
            shutil.copy2(temp_path, dest_path)
            logger.info("Copied %s to kept papers", filename)
        else:
            logger.warning("PDF not found for %s, skipping copy", filename)

    # Build manifest entries
    manifest_entries = []

    # Add kept papers
    for evaluation in kept:
        entry = _build_paper_entry(evaluation, iteration, kept=True)
        manifest_entries.append(entry)

    # Add discarded papers
    for evaluation in discarded:
        entry = _build_paper_entry(evaluation, iteration, kept=False)
        manifest_entries.append(entry)

    # Update manifest
    manifest["papers"].extend(manifest_entries)
    manifest["last_updated"] = datetime.now().isoformat()
    manifest["total_iterations"] = max(
        manifest.get("total_iterations", 0),
        iteration,
    )

    # Save manifest
    _save_manifest(manifest, manifest_file)

    logger.info(
        "Stored %d kept papers, %d discarded papers",
        len(kept),
        len(discarded),
    )


def _load_manifest(manifest_file: str) -> dict[str, Any]:
    """Load existing manifest or create new one."""
    if os.path.exists(manifest_file):
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Failed to load manifest: %s, creating new", e)

    # Create new manifest
    return {
        "version": "0.1.0",
        "started_at": datetime.now().isoformat(),
        "last_updated": datetime.now().isoformat(),
        "total_iterations": 0,
        "queries_used": {},
        "papers": [],
    }


def _save_manifest(manifest: dict[str, Any], manifest_file: str) -> None:
    """Save manifest to file."""
    os.makedirs(os.path.dirname(manifest_file), exist_ok=True)
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def _build_paper_entry(
    evaluation: dict[str, Any], iteration: int, kept: bool
) -> dict[str, Any]:
    """Build a manifest entry for a paper.

    Args:
        evaluation: Evaluation dict from LLM.
        iteration: Current iteration number.
        kept: Whether the paper was kept.

    Returns:
        Manifest entry dict.
    """
    entry: dict[str, Any] = {
        "filename": evaluation.get("filename", ""),
        "iteration": iteration,
        "relevance": evaluation.get("relevance", ""),
        "kept": kept,
    }

    # Add metadata from evaluation
    if kept:
        entry.update({
            "why_useful": evaluation.get("why_useful", ""),
            "key_pages": evaluation.get("key_pages", []),
            "key_findings": evaluation.get("key_findings", []),
            "methodology": evaluation.get("methodology", ""),
        })
    else:
        entry["why_not_relevant"] = evaluation.get("why_not_relevant", "")

    return entry


def get_manifest_stats(manifest_file: str) -> dict[str, Any]:
    """Get statistics from manifest.

    Args:
        manifest_file: Path to manifest file.

    Returns:
        Dict with statistics.
    """
    manifest = _load_manifest(manifest_file)

    papers = manifest.get("papers", [])
    kept = [p for p in papers if p.get("kept")]
    discarded = [p for p in papers if not p.get("kept")]

    high_relevance = [p for p in kept if p.get("relevance") == "high"]
    medium_relevance = [p for p in kept if p.get("relevance") == "medium"]

    return {
        "total_papers": len(papers),
        "kept": len(kept),
        "discarded": len(discarded),
        "high_relevance": len(high_relevance),
        "medium_relevance": len(medium_relevance),
        "iterations": manifest.get("total_iterations", 0),
    }
