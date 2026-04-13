"""litscout.config — Load and validate configuration."""

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def load_config(config_path: str = "config.yaml") -> dict[str, Any]:
    """Load and validate configuration from config.yaml and .env.

    Args:
        config_path: Path to the config.yaml file.

    Returns:
        Config dict with all settings resolved.

    Raises:
        FileNotFoundError: If config.yaml is not found.
        RuntimeError: If required env vars are missing.
    """
    # Load .env file
    load_dotenv()

    # Load config.yaml
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Resolve environment variable references
    config = _resolve_env_vars(config)

    # Validate required settings
    _validate_config(config)

    return config


def _resolve_env_vars(config: dict[str, Any]) -> dict[str, Any]:
    """Resolve environment variable references in config.

    Args:
        config: Config dict with env var references.

    Returns:
        Config dict with env vars resolved to actual values.
    """
    resolved = _deep_copy(config)

    # Resolve API settings
    api = resolved.get("api", {})
    if "base_url_env" in api:
        api["base_url"] = os.getenv(api["base_url_env"], "")
    if "api_key_env" in api:
        api["api_key"] = os.getenv(api["api_key_env"], "")
    if "model_env" in api:
        api["model"] = os.getenv(api["model_env"], "")

    # Resolve search settings
    search = resolved.get("search", {})
    s2 = search.get("semantic_scholar", {})
    if "api_key_env" in s2:
        s2["api_key"] = os.getenv(s2["api_key_env"], "")

    openalex = search.get("openalex", {})
    if "email_env" in openalex:
        openalex["email"] = os.getenv(openalex["email_env"], "")

    elsevier = search.get("elsevier", {})
    if "api_key_env" in elsevier:
        elsevier["api_key"] = os.getenv(elsevier["api_key_env"], "")
    if "inst_token_env" in elsevier:
        elsevier["inst_token"] = os.getenv(elsevier["inst_token_env"], "")

    return resolved


def _deep_copy(obj: Any) -> Any:
    """Create a deep copy of a dict/list structure."""
    if isinstance(obj, dict):
        return {k: _deep_copy(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_deep_copy(item) for item in obj]
    else:
        return obj


def _validate_config(config: dict[str, Any]) -> None:
    """Validate required configuration settings.

    Args:
        config: Config dict to validate.

    Raises:
        RuntimeError: If required settings are missing.
    """
    api = config.get("api", {})

    # Check LLM settings
    required_llm_vars = ["base_url", "api_key", "model"]
    for var in required_llm_vars:
        if not api.get(var):
            raise RuntimeError(
                f"LLM {var} not set. Please set {api.get(f'{var}_env', 'unknown')} in .env"
            )

    # Check search sources
    search = config.get("search", {})
    sources = search.get("sources", [])

    if not sources:
        logger.warning("No search sources configured")

    # Log warnings for missing optional API keys
    s2 = search.get("semantic_scholar", {})
    if not s2.get("api_key"):
        logger.info("Semantic Scholar API key not set, using unauthenticated mode")

    elsevier = search.get("elsevier", {})
    if not elsevier.get("api_key"):
        logger.info("Elsevier API key not set, disabling Elsevier fallback")
