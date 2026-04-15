"""litscout.resources — Helper for loading bundled package resources.

Uses importlib.resources to locate files bundled with the package.
Falls back to local files during development.
"""

import sys
from pathlib import Path

try:
    from importlib.resources import files
except ImportError:
    # Python 3.8 compatibility
    from importlib_resources import files


def get_prompt_path(prompt_name: str) -> Path:
    """Get the path to a bundled prompt file.

    Looks in the current working directory first (for development),
    then falls back to the bundled package data.

    Args:
        prompt_name: Name of the prompt file (e.g., 'query_gen.md').

    Returns:
        Path to the prompt file.
    """
    # First check cwd/prompts/ (development mode)
    cwd_prompt = Path("prompts") / prompt_name
    if cwd_prompt.exists():
        return cwd_prompt

    # Fall back to bundled prompts
    return get_package_path("prompts", prompt_name)


def get_template_path(template_name: str) -> Path:
    """Get the path to a bundled template file.

    Args:
        template_name: Name of the template file (e.g., '.env.example').

    Returns:
        Path to the template file.
    """
    return get_package_path("templates", template_name)


def get_package_path(subdir: str, filename: str) -> Path:
    """Get the path to a file bundled with the package.

    Args:
        subdir: Subdirectory within the package (e.g., 'prompts', 'templates').
        filename: Name of the file.

    Returns:
        Path to the file.
    """
    if sys.version_info >= (3, 12):
        # Python 3.12+: files() returns Traversable
        pkg_files = files("litscout").joinpath(subdir, filename)
        return Path(str(pkg_files))
    else:
        # Python 3.9-3.11: use as_file context manager
        from contextlib import contextmanager
        ref = f"litscout.{subdir}.{filename.replace('.', '_')}"
        # For older Python, use the package directly
        pkg_files = files("litscout").joinpath(subdir, filename)
        return Path(str(pkg_files))


def read_prompt(prompt_name: str) -> str:
    """Read a bundled prompt file.

    Args:
        prompt_name: Name of the prompt file.

    Returns:
        Content of the prompt file.
    """
    path = get_prompt_path(prompt_name)
    return path.read_text(encoding="utf-8")


def read_template(template_name: str) -> str:
    """Read a bundled template file.

    Args:
        template_name: Name of the template file.

    Returns:
        Content of the template file.
    """
    path = get_template_path(template_name)
    return path.read_text(encoding="utf-8")
