"""litscout.main — Main orchestrator and CLI entry point."""

import argparse
import asyncio
import json
import logging
import os
import shutil
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from litscout.config import load_config
from litscout.decide.paper_store import get_manifest_stats
from litscout.decide.relevance_filter import filter_results, get_relevance_count
from litscout.decide.sufficiency_judge import SufficiencyJudge
from litscout.download.pdf_fetcher import PDFFetcher
from litscout.download.temp_manager import cleanup_temp, create_temp
from litscout.llm_client import LLMClient
from litscout.resources import read_template
from litscout.report_writer import write_report
from litscout.screen.screener import Screener
from litscout.search.deduplicator import Deduplicator
from litscout.search.query_generator import QueryGenerator
from litscout.search.scholar_client import PaperMetadata, ScholarClient

# Global shutdown flag
shutdown_requested = False


# ── CLI Subcommands ──────────────────────────────────────────────────────────

def cmd_init(args: argparse.Namespace) -> None:
    """Scaffold a new litscout project directory."""
    project_root = Path(args.project_root) if args.project_root else Path.cwd()

    print(f"Initializing litscout project in: {project_root}")
    print()

    # Create directories
    dirs = ["input", "output", "output/kept_papers", "output/reports", "temp", "prompts"]
    for d in dirs:
        (project_root / d).mkdir(parents=True, exist_ok=True)
        print(f"  Created: {d}/")

    print()

    # Copy template files (only if they don't already exist)
    templates = [
        (".env.example", ".env"),
        ("config.yaml", "config.yaml"),
        ("settings.example.yaml", "input/settings.yaml"),
        ("research.example.md", "input/research.md"),
    ]

    for template_name, dest_name in templates:
        dest = project_root / dest_name
        if dest.exists():
            print(f"  Skipped (exists): {dest_name}")
            continue
        try:
            content = read_template(template_name)
            dest.write_text(content, encoding="utf-8")
            print(f"  Created: {dest_name}")
        except Exception as e:
            print(f"  Warning: Could not create {dest_name}: {e}")

    # Create .gitkeep in output/
    gitkeep = project_root / "output" / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.touch()

    print()
    print("Project initialized! Next steps:")
    print("  1. Edit .env with your API keys (at minimum: LLM_BASE_URL, LLM_API_KEY, LLM_MODEL)")
    print("  2. Edit input/settings.yaml to enable your sources")
    print("  3. Edit input/research.md with your research angle")
    print("  4. Run: litscout run")


def cmd_run(args: argparse.Namespace) -> None:
    """Run the litscout pipeline."""
    config_path = args.config
    if not os.path.exists(config_path):
        print(f"Error: Config file not found: {config_path}")
        print("Did you run `litscout init` first?")
        sys.exit(1)

    asyncio.run(main(config_path))


def cmd_report(args: argparse.Namespace) -> None:
    """Regenerate the markdown report from existing manifest.json."""
    config_path = args.config
    if not os.path.exists(config_path):
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)

    try:
        config = load_config(config_path)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

    manifest_file = config.get("paths", {}).get("manifest_file", "output/manifest.json")
    if not os.path.exists(manifest_file):
        print(f"Error: Manifest not found: {manifest_file}")
        print("Run `litscout run` first to collect papers.")
        sys.exit(1)

    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)

    # Load research angle
    research_angle_file = config.get("paths", {}).get("research_file", "input/research.md")
    if os.path.exists(research_angle_file):
        with open(research_angle_file, "r", encoding="utf-8") as f:
            research_angle = f.read()
    else:
        print(f"Error: Research angle file not found: {research_angle_file}")
        sys.exit(1)

    reports_dir = config.get("paths", {}).get("reports_dir", "output/reports")
    report_path = os.path.join(
        reports_dir,
        f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
    )

    stats = get_manifest_stats(manifest_file)

    run_metadata = {
        "elapsed_time": "N/A (regenerated)",
        "total_iterations": manifest_data.get("total_iterations", 0),
        "total_screened": stats["total_papers"],
        "total_kept": stats["kept"],
        "total_discarded": stats["discarded"],
        "queries_used": [],
        "gaps": [],
    }

    write_report(
        manifest=manifest_data,
        research_angle=research_angle,
        run_metadata=run_metadata,
        output_path=report_path,
    )

    print(f"Report regenerated: {report_path}")


def cmd_clean(args: argparse.Namespace) -> None:
    """Clean output and temp directories."""
    from litscout.clean import clean_project

    project_root = Path(args.project_root) if args.project_root else Path.cwd()
    confirm = not args.confirm
    clean_project(project_root, confirm=confirm)


def cmd_status(args: argparse.Namespace) -> None:
    """Show quick summary of current project state."""
    config_path = args.config

    if not os.path.exists(config_path):
        print(f"Error: Config file not found: {config_path}")
        print("Did you run `litscout init` first?")
        sys.exit(1)

    try:
        config = load_config(config_path)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

    manifest_file = config.get("paths", {}).get("manifest_file", "output/manifest.json")

    print("=" * 40)
    print(" litscout Status")
    print("=" * 40)

    # Active sources
    active_sources = config.get("active_sources", [])
    if active_sources:
        source_strs = []
        for source in active_sources:
            name = source.get("name", "")
            role = source.get("role", "")
            role_str = "search+pdf" if role == "search_and_pdf" else "pdf-only"
            source_strs.append(f"{name} ({role_str})")
        print(f" Active sources : {', '.join(source_strs)}")
    else:
        print(" Active sources : None configured")

    # Target papers
    target_papers = config.get("sufficiency", {}).get("target_kept_papers", 20)
    print(f" Target papers  : {target_papers}")

    # Manifest stats
    if os.path.exists(manifest_file):
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

        stats = get_manifest_stats(manifest_file)
        total_iterations = manifest_data.get("total_iterations", 0)
        last_updated = manifest_data.get("last_updated", "Unknown")

        print(f" Iterations run : {total_iterations}")
        print(f" Papers kept    : {stats['kept']} ({stats['high_relevance']} high, {stats['medium_relevance']} medium)")
        print(f" Papers discarded: {stats['discarded']}")
        print(f" Last updated   : {last_updated}")
    else:
        print(" Iterations run : 0 (no runs yet)")
        print(" Papers kept    : 0")
        print(" Papers discarded: 0")
        print(" Last updated   : N/A")

    print("=" * 40)


# ── Pipeline Logic ───────────────────────────────────────────────────────────

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
    print("=" * 50)
    print(" litscout v0.2.0")
    print(" Automated Literature Search & Screening")
    print("=" * 50)

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


def get_relevance_summary(kept: int, discarded: int) -> str:
    """Get relevance summary string."""
    if kept == 0:
        return "0 high, 0 medium"
    return f"{kept} kept"


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

    try:
        # Open sessions
        await llm_client.__aenter__()
        await scholar_client.__aenter__()
        await pdf_fetcher.__aenter__()

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
    finally:
        # Close sessions
        await llm_client.__aexit__(None, None, None)
        await scholar_client.__aexit__(None, None, None)
        await pdf_fetcher.__aexit__(None, None, None)

    # Final report
    elapsed = time.time() - start_time
    elapsed_str = f"{int(elapsed // 3600)}h {int((elapsed % 3600) // 60)}m {int(elapsed % 60)}s"

    # Load full manifest dict (not just the papers list)
    if os.path.exists(manifest_file):
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
    else:
        manifest_data = {
            "version": "0.2.0",
            "papers": [],
            "total_iterations": 0,
            "queries_used": {},
        }

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
        manifest=manifest_data,
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
    """CLI entry point with subcommands."""
    parser = argparse.ArgumentParser(
        prog="litscout",
        description="litscout — Automated literature search, screening, and prioritization pipeline",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init subcommand
    init_parser = subparsers.add_parser(
        "init",
        help="Scaffold a new litscout project directory",
    )
    init_parser.add_argument(
        "project_root",
        nargs="?",
        default=None,
        help="Path to project root (default: current directory)",
    )

    # run subcommand
    run_parser = subparsers.add_parser(
        "run",
        help="Run the literature search pipeline",
    )
    run_parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )

    # report subcommand
    report_parser = subparsers.add_parser(
        "report",
        help="Regenerate the markdown report from existing manifest.json",
    )
    report_parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )

    # clean subcommand
    clean_parser = subparsers.add_parser(
        "clean",
        help="Clean output and temp directories",
    )
    clean_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Skip confirmation prompt and delete immediately",
    )
    clean_parser.add_argument(
        "--project-root",
        type=str,
        default=None,
        help="Path to project root (default: current directory)",
    )

    # status subcommand
    status_parser = subparsers.add_parser(
        "status",
        help="Show quick summary of current project state",
    )
    status_parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # Dispatch to subcommand
    commands = {
        "init": cmd_init,
        "run": cmd_run,
        "report": cmd_report,
        "clean": cmd_clean,
        "status": cmd_status,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    cli()
