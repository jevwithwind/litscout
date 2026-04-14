"""litscout.main — Main orchestrator and CLI entry point."""

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime
from typing import Any

from litscout.config import load_config
from litscout.decide.paper_store import get_manifest_stats
from litscout.decide.relevance_filter import filter_results, get_relevance_count
from litscout.decide.sufficiency_judge import SufficiencyJudge
from litscout.download.pdf_fetcher import PDFFetcher
from litscout.download.temp_manager import cleanup_temp, create_temp
from litscout.llm_client import LLMClient
from litscout.report_writer import write_report
from litscout.screen.screener import Screener
from litscout.search.deduplicator import Deduplicator
from litscout.search.query_generator import QueryGenerator
from litscout.search.scholar_client import PaperMetadata, ScholarClient

# Global shutdown flag
shutdown_requested = False


def setup_logging(log_file: str) -> None:
    """Set up logging to console and file.

    Args:
        log_file: Path to the log file.
    """
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Console handler (INFO level)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # File handler (DEBUG level)
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Configure root logger
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[console_handler, file_handler],
    )


def print_header(config: dict[str, Any]) -> None:
    """Print the litscout header."""
    print("══════════════════════════════════════════════════")
    print(" litscout v0.1.0")
    print(" Automated Literature Search & Screening")
    print("══════════════════════════════════════════════════")

    # Get research angle file
    research_file = config.get("paths", {}).get("research_file", "input/research.md")
    print(f" Research angle : {research_file}")

    # Get target papers and max iterations
    target_papers = config.get("sufficiency", {}).get("target_kept_papers", 20)
    max_iterations = config.get("sufficiency", {}).get("max_iterations", 0)
    max_iter_str = "unlimited" if max_iterations == 0 else str(max_iterations)
    print(f" Target papers  : {target_papers}")
    print(f" Max iterations : {max_iter_str}")

    # Get active sources
    active_sources = config.get("active_sources", [])
    source_strs = []
    for source in active_sources:
        name = source.get("name", "")
        role = source.get("role", "")
        role_str = "search+pdf" if role == "search_and_pdf" else "pdf-only"
        source_strs.append(f"{name} ({role_str})")

    if source_strs:
        print(f" Active sources : {', '.join(source_strs)}")

    # Check for skipped sources (enabled but missing credentials)
    skipped_sources = []
    sources_config = config.get("sources", {})
    for source_name, source_config in sources_config.items():
        if source_config.get("enabled", False):
            # Check if credentials are missing
            if source_name == "semantic_scholar" and not os.getenv("S2_API_KEY"):
                skipped_sources.append(f"{source_name} (S2_API_KEY not set)")
            elif source_name == "elsevier" and not os.getenv("ELSEVIER_API_KEY"):
                skipped_sources.append(f"{source_name} (ELSEVIER_API_KEY not set)")
            elif source_name == "pubmed" and not os.getenv("PUBMED_API_KEY"):
                skipped_sources.append(f"{source_name} (PUBMED_API_KEY not set)")
            elif source_name == "core" and not os.getenv("CORE_API_KEY"):
                skipped_sources.append(f"{source_name} (CORE_API_KEY not set)")

    if skipped_sources:
        print(f" Skipped sources: {', '.join(skipped_sources)}")

    print()


def print_iteration_header(iteration: int) -> None:
    """Print iteration header."""
    print(f"─── Iteration {iteration} ─────────────────────────")
    print()


def print_iteration_summary(
    iteration: int,
    queries_count: int,
    candidates_count: int,
    downloaded_count: int,
    total_screened: int,
    kept_count: int,
    discarded_count: int,
    total_kept: int,
    target_kept: int,
) -> None:
    """Print iteration summary."""
    print(f"✓ Generated {queries_count} search queries")
    print(f"✓ Found {candidates_count} new candidates")
    print(f"✓ Downloaded {downloaded_count} PDFs")
    print(f"✓ Screened {total_screened} papers")
    print(f"✓ Kept {kept_count} ({get_relevance_summary(kept_count, discarded_count)}) | Discarded {discarded_count}")
    print(f"✓ Total kept: {total_kept}/{target_kept} target")
    print()


def get_relevance_summary(kept: int, discarded: int) -> str:
    """Get relevance summary string."""
    if kept == 0:
        return "0 high, 0 medium"
    return f"{kept} kept"


async def run_iteration(
    iteration: int,
    config: dict[str, Any],
    llm_client: LLMClient,
    scholar_client: ScholarClient,
    query_generator: QueryGenerator,
    pdf_fetcher: PDFFetcher,
    screener: Screener,
    sufficiency_judge: SufficiencyJudge,
    deduplicator: Deduplicator,
    manifest: list[dict[str, Any]],
    previous_queries: list[str],
    gaps: list[str],
    research_angle: str,
    temp_dir: str,
    output_dir: str,
) -> tuple[bool, list[str], list[str]]:
    """Run a single iteration of the pipeline.

    Args:
        iteration: Current iteration number.
        config: Configuration dict.
        llm_client: LLM client for query generation and screening.
        scholar_client: Academic search client.
        query_generator: Query generator.
        pdf_fetcher: PDF fetcher.
        screener: Paper screener.
        sufficiency_judge: Sufficiency checker.
        deduplicator: Deduplicator.
        manifest: Current manifest.
        previous_queries: Previously used queries.
        gaps: Gap analysis from previous iteration.
        research_angle: User's research angle.
        temp_dir: Temp directory path.
        output_dir: Output directory path.

    Returns:
        Tuple of (should_continue, new_queries, new_gaps).
    """
    search_config = config.get("search", {})
    sufficiency_config = config.get("sufficiency", {})
    download_config = config.get("download", {})
    screening_config = config.get("screening", {})

    queries_per_iteration = search_config.get("queries_per_iteration", 5)
    results_per_query = search_config.get("results_per_query", 20)
    year_range = search_config.get("year_range", 5)
    target_kept = sufficiency_config.get("target_kept_papers", 0)

    # 1. Generate queries
    print_iteration_header(iteration)
    queries, gap_analysis = await query_generator.generate(
        research_angle=research_angle,
        manifest_papers=manifest,
        previous_queries=previous_queries,
        gap_analysis=gaps[0] if gaps else None,
        num_queries=queries_per_iteration,
    )
    print(f"✓ Generated {len(queries)} search queries")

    # 2. Search
    candidates: list[PaperMetadata] = []
    for query in queries:
        results = await scholar_client.search(
            query=query,
            limit=results_per_query,
            year_range=year_range,
        )
        new_results = [r for r in results if deduplicator.is_new(r)]
        candidates.extend(new_results)
        for r in results:
            deduplicator.mark_seen(r)

    print(f"✓ Found {len(candidates)} new candidates")

    if not candidates:
        print("⚠ No new candidates found. Consider broadening research angle.")
        return True, queries, [gap_analysis] if gap_analysis else []

    # 3. Download
    create_temp(temp_dir)
    downloads = await pdf_fetcher.fetch_pdfs(
        candidates,
        temp_dir,
    )
    successful = [d for d in downloads if d["success"]]
    print(f"✓ Downloaded {len(successful)}/{len(candidates)} PDFs")

    if not successful:
        cleanup_temp(temp_dir)
        return True, queries, [gap_analysis] if gap_analysis else []

    # 4. Screen
    pdf_paths = [
        {"local_path": d["local_path"], "metadata": d["metadata"]}
        for d in successful
    ]
    evaluations = await screener.screen_papers(
        pdf_paths=pdf_paths,
        config=config,
        research_angle_file=config.get("paths", {}).get("prompt_file", "prompts/research.md"),
    )
    print(f"✓ Screened {len(evaluations)} papers")

    # 5. Filter and store
    kept, discarded = filter_results(evaluations)
    store_papers(
        kept=kept,
        discarded=discarded,
        iteration=iteration,
        config=config,
    )
    cleanup_temp(temp_dir)
    print(f"✓ Kept {len(kept)}, discarded {len(discarded)}")

    # 6. Sufficiency check
    manifest = load_manifest(config)
    total_kept = sum(1 for p in manifest if p.get("kept"))
    print(f"✓ Total kept: {total_kept}/{target_kept} target")

    result = await sufficiency_judge.check_sufficiency(
        manifest=manifest,
        config=config,
        research_angle=research_angle,
    )

    if result["should_stop"]:
        if sufficiency_config.get("auto_stop", False):
            print(f"✓ Auto-stopping: {result['reason']}")
            return False, queries, result.get("gaps", [])
        else:
            print(f"✓ Sufficiency reached: {result['reason']}")
            user_input = input("Continue searching? [y/N]: ").strip().lower()
            if user_input != "y":
                return False, queries, result.get("gaps", [])
            return True, queries, result.get("gaps", [])

    return True, queries, result.get("gaps", [])


def store_papers(
    kept: list[dict[str, Any]],
    discarded: list[dict[str, Any]],
    iteration: int,
    config: dict[str, Any],
) -> None:
    """Store papers and update manifest."""
    from litscout.decide.paper_store import store_papers as _store_papers
    _store_papers(kept, discarded, iteration, config)


def load_manifest(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Load manifest from file."""
    manifest_file = config.get("paths", {}).get("manifest_file", "output/manifest.json")
    if os.path.exists(manifest_file):
        with open(manifest_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("papers", [])
    return []


async def main(config_path: str = "config.yaml") -> None:
    """Main entry point for the litscout pipeline.

    Args:
        config_path: Path to the config.yaml file.
    """
    global shutdown_requested

    # Load configuration
    try:
        config = load_config(config_path)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

    # Set up logging
    log_file = config.get("paths", {}).get("output_dir", "output") + "/litscout.log"
    setup_logging(log_file)

    # Print header
    print_header(config)

    # Get research angle
    research_angle_file = config.get("paths", {}).get("research_file", "input/research.md")
    if os.path.exists(research_angle_file):
        with open(research_angle_file, "r", encoding="utf-8") as f:
            research_angle = f.read()
    else:
        print(f"Error: Research angle file not found: {research_angle_file}")
        sys.exit(1)

    print(f"Research: {research_angle_file}")
    print()

    # Create directories
    output_dir = config.get("paths", {}).get("output_dir", "output")
    kept_papers_dir = config.get("paths", {}).get("kept_papers_dir", "output/kept_papers")
    reports_dir = config.get("paths", {}).get("reports_dir", "output/reports")
    temp_dir = config.get("paths", {}).get("temp_dir", "temp")

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(kept_papers_dir, exist_ok=True)
    os.makedirs(reports_dir, exist_ok=True)

    # Load existing manifest if available
    manifest_file = config.get("paths", {}).get("manifest_file", "output/manifest.json")
    if os.path.exists(manifest_file):
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
        existing_papers = len(manifest_data.get("papers", []))
        existing_iterations = manifest_data.get("total_iterations", 0)
        print(f"Resuming from iteration {existing_iterations + 1} ({existing_papers} papers already collected)")
        print()

        # Load previous queries
        previous_queries = []
        for iteration, queries in manifest_data.get("queries_used", {}).items():
            previous_queries.extend(queries)
    else:
        previous_queries = []

    # Initialize components
    llm_client = LLMClient(
        base_url=config["api"]["base_url"],
        api_key=config["api"]["api_key"],
        model=config["api"]["model"],
        max_tokens=config["api"].get("max_tokens", 16384),
        temperature=config["api"].get("temperature", 0.3),
        max_concurrent_requests=config["api"].get("max_concurrent_requests", 3),
    )

    scholar_client = ScholarClient(
        active_sources=config.get("active_sources", []),
    )

    query_generator = QueryGenerator(
        llm_client=llm_client,
        research_angle_file=research_angle_file,
        query_gen_prompt_file=config.get("paths", {}).get("query_gen_prompt", "prompts/query_gen.md"),
    )

    # Get elsevier config from active sources
    elsevier_config = next((s for s in config.get("active_sources", []) if s.get("name") == "elsevier"), {})
    elsevier_enabled = elsevier_config.get("role") == "pdf_only"
    elsevier_api_key = elsevier_config.get("credentials", {}).get("api_key", "")
    elsevier_inst_token = elsevier_config.get("credentials", {}).get("inst_token", "")

    pdf_fetcher = PDFFetcher(
        elsevier_api_key=elsevier_api_key,
        elsevier_inst_token=elsevier_inst_token,
        elsevier_enabled=elsevier_enabled,
        concurrency=config["download"].get("concurrency", 5),
        timeout=config["download"].get("timeout", 60),
        max_pdf_size_mb=config["download"].get("max_pdf_size_mb", 50),
    )

    screener = Screener(
        llm_client=llm_client,
        screening_prompt_file=config.get("paths", {}).get("screening_prompt", "prompts/screening.md"),
        batch_size=config["screening"].get("batch_size", 10),
        max_tokens_per_batch=config["screening"].get("max_tokens_per_batch", 200000),
    )

    sufficiency_judge = SufficiencyJudge(
        llm_client=llm_client,
        sufficiency_prompt_file=config.get("paths", {}).get("sufficiency_prompt", "prompts/sufficiency.md"),
    )

    deduplicator = Deduplicator(
        state_file=os.path.join(output_dir, "deduplicator.json"),
    )

    # Load existing seen papers into deduplicator
    if os.path.exists(manifest_file):
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
        deduplicator.load_from_manifest(manifest_data.get("papers", []))

    # Register signal handler for graceful shutdown
    def signal_handler(signum: int, frame: Any) -> None:
        global shutdown_requested
        print("\n\nShutdown requested... finishing current iteration...")
        shutdown_requested = True

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Main loop
    start_time = time.time()
    iteration = 1
    consecutive_empty = 0
    all_queries = previous_queries.copy()
    gaps: list[str] = []

    # Load existing manifest for iteration count
    if os.path.exists(manifest_file):
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
        iteration = manifest_data.get("total_iterations", 0) + 1

    while not shutdown_requested:
        # Check max iterations
        max_iterations = config.get("sufficiency", {}).get("max_iterations", 0)
        if max_iterations > 0 and iteration > max_iterations:
            print(f"Max iterations ({max_iterations}) reached")
            break

        print_iteration_header(iteration)

        # 1. Generate queries
        queries, gap_analysis = await query_generator.generate(
            research_angle=research_angle,
            manifest_papers=load_manifest(config),
            previous_queries=all_queries,
            gap_analysis=gaps[0] if gaps else None,
            num_queries=config["search"].get("queries_per_iteration", 5),
        )
        print(f"✓ Generated {len(queries)} search queries")

        # 2. Search
        candidates: list[PaperMetadata] = []
        for query in queries:
            results = await scholar_client.search(
                query=query,
                limit=config["search"].get("results_per_query", 20),
                year_range=config["search"].get("year_range", 5),
            )
            new_results = [r for r in results if deduplicator.is_new(r)]
            candidates.extend(new_results)
            for r in results:
                deduplicator.mark_seen(r)

        print(f"✓ Found {len(candidates)} new candidates")

        if not candidates:
            consecutive_empty += 1
            print("⚠ No new candidates found. Consider broadening research angle.")
            if consecutive_empty >= 3:
                print("⚠ No new papers found for 3 iterations. Stopping.")
                break
            all_queries.extend(queries)
            gaps = [gap_analysis] if gap_analysis else []
            iteration += 1
            continue

        consecutive_empty = 0

        # 3. Download
        create_temp(temp_dir)
        downloads = await pdf_fetcher.fetch_pdfs(
            candidates,
            temp_dir,
        )
        successful = [d for d in downloads if d["success"]]
        print(f"✓ Downloaded {len(successful)}/{len(candidates)} PDFs")

        if not successful:
            cleanup_temp(temp_dir)
            all_queries.extend(queries)
            gaps = [gap_analysis] if gap_analysis else []
            iteration += 1
            continue

        # 4. Screen
        pdf_paths = [
            {"local_path": d["local_path"], "metadata": d["metadata"]}
            for d in successful
        ]
        evaluations = await screener.screen_papers(
            pdf_paths=pdf_paths,
            config=config,
            research_angle_file=research_angle_file,
        )
        print(f"✓ Screened {len(evaluations)} papers")

        # 5. Filter and store
        kept, discarded = filter_results(evaluations)
        store_papers(
            kept=kept,
            discarded=discarded,
            iteration=iteration,
            config=config,
        )
        cleanup_temp(temp_dir)
        print(f"✓ Kept {len(kept)}, discarded {len(discarded)}")

        # 6. Sufficiency check
        manifest = load_manifest(config)
        total_kept = sum(1 for p in manifest if p.get("kept"))
        target_kept = config.get("sufficiency", {}).get("target_kept_papers", 0)
        print(f"✓ Total kept: {total_kept}/{target_kept} target")

        result = await sufficiency_judge.check_sufficiency(
            manifest=manifest,
            config=config,
            research_angle=research_angle,
        )

        if result["should_stop"]:
            if config.get("sufficiency", {}).get("auto_stop", False):
                print(f"✓ Auto-stopping: {result['reason']}")
                break
            else:
                print(f"✓ Sufficiency reached: {result['reason']}")
                user_input = input("Continue searching? [y/N]: ").strip().lower()
                if user_input != "y":
                    break

        all_queries.extend(queries)
        gaps = result.get("gaps", [])
        iteration += 1

    # Final report
    elapsed = time.time() - start_time
    elapsed_str = f"{int(elapsed // 3600)}h {int((elapsed % 3600) // 60)}m {int(elapsed % 60)}s"

    manifest = load_manifest(config)
    stats = get_manifest_stats(manifest_file)

    report_path = os.path.join(
        reports_dir,
        f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
    )

    run_metadata = {
        "elapsed_time": elapsed_str,
        "total_iterations": iteration - 1,
        "total_screened": stats["total_papers"],
        "total_kept": stats["kept"],
        "total_discarded": stats["discarded"],
        "queries_used": all_queries,
        "gaps": gaps,
    }

    write_report(
        manifest=manifest,
        research_angle=research_angle,
        run_metadata=run_metadata,
        output_path=report_path,
    )

    print()
    print("════════════════════════════════════════")
    print(" Done!")
    print(f" Report saved to: {report_path}")
    print(f" Total iterations: {iteration - 1}")
    print(f" Papers kept: {stats['kept']} ({stats['high_relevance']} high, {stats['medium_relevance']} medium)")
    print(f" Papers discarded: {stats['discarded']}")
    print(f" Time elapsed: {elapsed_str}")
    print("════════════════════════════════════════")


def cli() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="litscout — Automated literature search and screening pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  litscout                          # Run with default config
  litscout --config myconfig.yaml   # Use custom config file
  litscout --continue               # Ignore sufficiency, keep running
        """,
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "--continue",
        action="store_true",
        dest="continue_searching",
        help="Ignore sufficiency, keep running until stopped",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Run one more iteration then stop",
    )
    parser.add_argument(
        "--target-papers",
        type=int,
        help="Override target kept papers",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        help="Override max iterations",
    )

    args = parser.parse_args()

    # Run the async main function
    asyncio.run(main(args.config))


if __name__ == "__main__":
    cli()
