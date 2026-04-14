"""litscout.report_writer — Generate final Markdown report from manifest."""

import json
import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def write_report(
    manifest: dict[str, Any],
    research_angle: str,
    run_metadata: dict[str, Any],
    output_path: str,
) -> str:
    """Generate a comprehensive final Markdown report from manifest.

    Args:
        manifest: Full manifest dict with 'papers', 'total_iterations', etc.
        research_angle: The contents of prompts/research.md.
        run_metadata: Dict with run statistics and metadata.
        output_path: Path to save the report.

    Returns:
        The path to the saved report.
    """
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Build report content
    report = _build_report(manifest, research_angle, run_metadata)

    # Save report
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    logger.info("Report saved to %s", output_path)
    return output_path


def _build_report(
    manifest: dict[str, Any],
    research_angle: str,
    run_metadata: dict[str, Any],
) -> str:
    """Build the report content as a Markdown string.

    Args:
        manifest: List of paper entries.
        research_angle: The research angle text.
        run_metadata: Run statistics and metadata.

    Returns:
        Markdown report content.
    """
    # Calculate statistics
    papers = manifest.get("papers", [])
    kept = [p for p in papers if p.get("kept")]
    discarded = [p for p in papers if not p.get("kept")]

    high_relevance = [p for p in kept if p.get("relevance") == "high"]
    medium_relevance = [p for p in kept if p.get("relevance") == "medium"]

    total_iterations = manifest.get("total_iterations", 0)
    started_at = manifest.get("started_at", "Unknown")
    elapsed = run_metadata.get("elapsed_time", "Unknown")

    # Build report
    lines = []

    # Header
    lines.append("# litscout Report")
    lines.append("")
    lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Total iterations**: {total_iterations}")
    lines.append(f"**Papers screened**: {len(papers)}")
    lines.append(f"**Papers kept**: {len(kept)} ({len(high_relevance)} high, {len(medium_relevance)} medium)")
    lines.append(f"**Papers discarded**: {len(discarded)}")
    lines.append(f"**Time elapsed**: {elapsed}")
    lines.append("")

    # Research Angle
    lines.append("## Research Angle")
    lines.append("")
    lines.append(f"> {research_angle.strip()}")
    lines.append("")

    # Summary Table
    lines.append("## Summary Table")
    lines.append("")
    lines.append("| # | Paper | Year | Relevance | Why Relevant |")
    lines.append("|---|-------|------|-----------|--------------|")

    # Sort by relevance: high first, then medium
    sorted_papers = sorted(
        kept,
        key=lambda p: (0 if p.get("relevance") == "high" else 1, p.get("filename", ""))
    )

    for i, paper in enumerate(sorted_papers, 1):
        filename = paper.get("filename", "Unknown")
        year = paper.get("year", "N/A")
        relevance = paper.get("relevance", "N/A").capitalize()
        why_useful = paper.get("why_useful", "")[:50] + "..." if len(paper.get("why_useful", "")) > 50 else paper.get("why_useful", "")

        # Escape pipe characters in table cells
        filename = filename.replace("|", "\\|")
        why_useful = why_useful.replace("|", "\\|")

        lines.append(f"| {i} | {filename} | {year} | {relevance} | {why_useful} |")

    lines.append("")
    lines.append("> Papers are sorted by relevance: High relevance first, then Medium.")
    lines.append("")

    # Detailed Evaluations
    lines.append("## Detailed Evaluations")
    lines.append("")

    for i, paper in enumerate(sorted_papers, 1):
        lines.append(f"### {i}. {paper.get('filename', 'Unknown')}")
        lines.append("")
        lines.append(f"- **Relevance rating:** {paper.get('relevance', 'N/A').capitalize()}")
        lines.append(f"- **Why it's useful:** {paper.get('why_useful', 'N/A')}")
        lines.append(f"- **Key pages to read:** {', '.join(str(p) for p in paper.get('key_pages', []))}")

        key_findings = paper.get("key_findings", [])
        if key_findings:
            lines.append("- **Key findings:**")
            for finding in key_findings:
                lines.append(f"  - {finding}")

        lines.append(f"- **Methodology & data:** {paper.get('methodology', 'N/A')}")
        lines.append("")

    # Coverage Analysis
    lines.append("## Coverage Analysis")
    lines.append("")
    gaps = run_metadata.get("gaps", [])
    if gaps:
        lines.append("The following topics/methods may still need coverage:")
        lines.append("")
        for gap in gaps:
            lines.append(f"- {gap}")
    else:
        lines.append("No significant gaps identified in the collected literature.")
    lines.append("")

    # Search Queries Used
    lines.append("## Search Queries Used")
    lines.append("")

    queries_used = manifest.get("queries_used", {})
    if queries_used:
        for iteration, queries in queries_used.items():
            lines.append(f"### Iteration {iteration}")
            lines.append("")
            for query in queries:
                lines.append(f"- {query}")
            lines.append("")
    else:
        lines.append("No search queries were used.")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append("*Generated by litscout v0.1.0*")

    return "\n".join(lines)


def format_elapsed_time(seconds: float) -> str:
    """Format elapsed time as human-readable string.

    Args:
        seconds: Time in seconds.

    Returns:
        Formatted time string (e.g., "1h 23m 45s").
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")

    return " ".join(parts)


def get_report_path(output_dir: str) -> str:
    """Get the path for the next report file.

    Args:
        output_dir: The output directory path.

    Returns:
        Full path to the report file.
    """
    reports_dir = os.path.join(output_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(reports_dir, f"report_{timestamp}.md")
