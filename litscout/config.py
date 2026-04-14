"""litscout.config — Load and validate configuration."""

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def load_config(config_path: str = "config.yaml") -> dict[str, Any]:
    """Load and validate configuration from config.yaml and input/settings.yaml.

    Args:
        config_path: Path to the config.yaml file.

    Returns:
        Config dict with all settings resolved.

    Raises:
        FileNotFoundError: If config.yaml or input/settings.yaml is not found.
        RuntimeError: If required settings are missing or invalid.
    """
    # Load .env file
    load_dotenv()

    # Load technical config
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Load user settings
    settings_path = config["paths"]["settings_file"]
    if not os.path.exists(settings_path):
        raise FileNotFoundError(
            f"input/settings.yaml not found. Run from the project root directory "
            "or create the input/ folder."
        )

    with open(settings_path, "r", encoding="utf-8") as f:
        settings = yaml.safe_load(f)

    # Merge user settings into config
    config["sufficiency"]["target_kept_papers"] = settings.get("target_papers", 20)
    config["sufficiency"]["max_iterations"] = settings.get("max_iterations", 0)
    config["sufficiency"]["auto_stop"] = settings.get("auto_stop", False)

    # Resolve sources
    config["active_sources"] = _resolve_sources(settings.get("sources", {}))

    # Resolve environment variable references
    config = _resolve_env_vars(config)

    # Validate required settings
    _validate_config(config)

    return config


def _resolve_sources(sources: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve source configurations from settings.

    Args:
        sources: Dict of source configurations from input/settings.yaml.

    Returns:
        List of active source configs with resolved credentials.
    """
    active_sources = []

    # Source-specific env var mappings
    env_mappings = {
        "semantic_scholar": {"api_key_env": "S2_API_KEY"},
        "elsevier": {
            "api_key_env": "ELSEVIER_API_KEY",
            "inst_token_env": "ELSEVIER_INST_TOKEN",
        },
        "arxiv": {},
        "pubmed": {"api_key_env": "PUBMED_API_KEY"},
        "core": {"api_key_env": "CORE_API_KEY"},
        "openalex": {},
    }

    for source_name, source_config in sources.items():
        if not source_config.get("enabled", False):
            continue

        # Get env var mappings for this source
        mappings = env_mappings.get(source_name, {})

        # Resolve credentials
        credentials = {}
        for field, env_var in mappings.items():
            value = os.getenv(env_var, "")
            if value:
                credentials[field] = value
            elif field.endswith("_env") or field.endswith("_token"):
                # Required field is missing
                logger.warning(
                    "Source '%s' is enabled but %s is not set in .env — skipping",
                    source_name,
                    env_var,
                )
                break
        else:
            # All required credentials are present (or no credentials needed)
            source_entry = {
                "name": source_name,
                "role": source_config.get("role", "search_and_pdf"),
                "credentials": credentials,
            }
            active_sources.append(source_entry)
            logger.debug("Source '%s' is active with role '%s'", source_name, source_config.get("role"))

    # Check if at least one search-capable source is active
    search_sources = [s for s in active_sources if s["role"] == "search_and_pdf"]
    if not search_sources:
        logger.warning("No search sources available. Enable at least one source with role 'search_and_pdf' in input/settings.yaml")

    return active_sources


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

    # Check research angle file
    research_file = config.get("paths", {}).get("research_file", "input/research.md")
    if not os.path.exists(research_file):
        raise RuntimeError(
            f"Please write your research angle in {research_file} before running litscout."
        )

    # Check if research angle is still the template
    with open(research_file, "r", encoding="utf-8") as f:
        content = f.read().strip()
    if "Describe your research question" in content or "(Describe your" in content:
        raise RuntimeError(
            f"Please write your research angle in {research_file} before running litscout. "
            "The file still contains template text."
        )

    # Check for active search sources
    active_sources = config.get("active_sources", [])
    search_sources = [s for s in active_sources if s.get("role") == "search_and_pdf"]
    if not search_sources:
        logger.warning("No search sources available. Enable at least one source with role 'search_and_pdf' in input/settings.yaml")

    # Log warnings for missing optional API keys
    s2 = config.get("search", {}).get("semantic_scholar", {})
    if not s2.get("api_key"):
        logger.info("Semantic Scholar API key not set, using unauthenticated mode")

    elsevier = config.get("search", {}).get("elsevier", {})
    if not elsevier.get("api_key"):
        logger.info("Elsevier API key not set, disabling Elsevier fallback")
