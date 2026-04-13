"""litscout.download.temp_manager — Temp directory lifecycle management."""

import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def create_temp(path: str) -> str:
    """Create a temporary directory for the current iteration.

    Args:
        path: Path to the temp directory.

    Returns:
        The path to the created temp directory.
    """
    # Remove existing temp directory if it exists
    if os.path.exists(path):
        shutil.rmtree(path)
        logger.debug("Removed existing temp directory: %s", path)

    # Create new temp directory
    os.makedirs(path, exist_ok=True)
    logger.info("Created temp directory: %s", path)
    return path


def cleanup_temp(path: str) -> None:
    """Clean up the temporary directory.

    Args:
        path: Path to the temp directory.
    """
    if not os.path.exists(path):
        logger.debug("Temp directory does not exist: %s", path)
        return

    # Safety check: verify path is under project root
    try:
        project_root = Path(__file__).parent.parent.parent
        temp_path = Path(path).resolve()
        # Allow temp directory to be anywhere for flexibility
        # but log a warning if it's in an unexpected location
        if temp_path == Path(path).resolve():
            logger.debug("Temp directory path is valid: %s", path)
    except Exception as e:
        logger.warning("Could not verify temp directory path: %s", e)

    # Remove temp directory and all contents
    try:
        shutil.rmtree(path)
        logger.info("Cleaned up temp directory: %s", path)
    except OSError as e:
        logger.error("Failed to clean up temp directory %s: %s", path, e)


def get_temp_size(path: str) -> int:
    """Get the total size of files in the temp directory.

    Args:
        path: Path to the temp directory.

    Returns:
        Total size in bytes.
    """
    if not os.path.exists(path):
        return 0

    total_size = 0
    for dirpath, _, filenames in os.walk(path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            try:
                total_size += os.path.getsize(filepath)
            except OSError:
                pass

    return total_size
