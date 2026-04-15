"""litscout.clean — Clean output and temp directories."""

import argparse
import os
import shutil
import sys
from pathlib import Path


def get_paths_to_clean(project_root: Path) -> tuple[list[Path], list[Path]]:
    """Get lists of files/dirs that would be deleted.

    Returns:
        Tuple of (output_items, temp_items) as lists of Paths.
    """
    output_dir = project_root / "output"
    temp_dir = project_root / "temp"

    output_items: list[Path] = []
    temp_items: list[Path] = []

    # Collect output/ contents (excluding .gitkeep)
    if output_dir.exists():
        for item in output_dir.iterdir():
            if item.name == ".gitkeep":
                continue
            output_items.append(item)

    # Collect temp/ contents if it exists
    if temp_dir.exists():
        for item in temp_dir.iterdir():
            temp_items.append(item)

    return output_items, temp_items


def clean_project(project_root: Path, confirm: bool = True) -> None:
    """Clean output and temp directories.

    Args:
        project_root: Path to the project root directory.
        confirm: If True, ask for confirmation before deleting.
    """
    output_items, temp_items = get_paths_to_clean(project_root)

    if not output_items and not temp_items:
        print("Nothing to clean. Output and temp directories are already empty.")
        return

    # Show what would be deleted
    print("The following items will be deleted:\n")

    if output_items:
        print("output/:")
        for item in output_items:
            if item.is_dir():
                print(f"  [dir]  {item.relative_to(project_root)}/")
            else:
                print(f"  [file] {item.relative_to(project_root)}")
        print()

    if temp_items:
        print("temp/:")
        for item in temp_items:
            if item.is_dir():
                print(f"  [dir]  {item.relative_to(project_root)}/")
            else:
                print(f"  [file] {item.relative_to(project_root)}")
        print()

    total = len(output_items) + len(temp_items)
    print(f"Total: {total} item(s)\n")

    if confirm:
        response = input("Are you sure? [y/N] ").strip().lower()
        if response not in ("y", "yes"):
            print("Clean cancelled.")
            return

    # Delete output items
    deleted_count = 0
    for item in output_items:
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            print(f"Deleted: {item.relative_to(project_root)}")
            deleted_count += 1
        except OSError as e:
            print(f"Error deleting {item.relative_to(project_root)}: {e}")

    # Delete temp items
    for item in temp_items:
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            print(f"Deleted: {item.relative_to(project_root)}")
            deleted_count += 1
        except OSError as e:
            print(f"Error deleting {item.relative_to(project_root)}: {e}")

    print(f"\nClean complete. {deleted_count} item(s) deleted.")


def main() -> None:
    """CLI entry point for the clean command."""
    parser = argparse.ArgumentParser(
        description="Clean output and temp directories from litscout project."
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Skip confirmation prompt and delete immediately.",
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=None,
        help="Path to project root (default: current directory).",
    )

    args = parser.parse_args()

    project_root = Path(args.project_root) if args.project_root else Path.cwd()

    if not project_root.exists():
        print(f"Error: Project root '{project_root}' does not exist.")
        sys.exit(1)

    clean_project(project_root, confirm=not args.confirm)


if __name__ == "__main__":
    main()
