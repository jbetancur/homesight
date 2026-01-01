"""
Prompt loader for external YAML prompt files.

Allows prompt editing without rebuilding containers.
Prompts are loaded on first access and can be reloaded at runtime.
"""

import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional

import yaml

logger = logging.getLogger(__name__)

# Determine prompts directory
# In Docker: /app/prompts (mounted volume)
# Local: ./prompts relative to this file's parent
if os.path.exists('/.dockerenv'):
    PROMPTS_DIR = Path('/app/prompts')
else:
    PROMPTS_DIR = Path(__file__).parent.parent / 'prompts'

# Cache for loaded prompts
_prompt_cache: Dict[str, Dict[str, Any]] = {}


def _load_prompt_file(name: str) -> Dict[str, Any]:
    """Load a prompt YAML file by name."""
    path = PROMPTS_DIR / f"{name}.yaml"

    if not path.exists():
        logger.warning(f"Prompt file not found: {path}")
        return {}

    try:
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
            logger.debug(f"Loaded prompt file: {name}")
            return data or {}
    except Exception as e:
        logger.error(f"Failed to load prompt file {path}: {e}")
        return {}


def get_prompt(file_name: str, key: str, **kwargs) -> str:
    """
    Get a prompt string from a YAML file.

    Args:
        file_name: Name of the YAML file (without .yaml extension)
        key: Key within the YAML file
        **kwargs: Format arguments to interpolate into the prompt

    Returns:
        Formatted prompt string, or empty string if not found

    Example:
        >>> get_prompt("orchestrator", "system_prompt")
        "You are HomeSight, a friendly AI assistant..."

        >>> get_prompt("climate_insights", "analysis_prompt", context="...", rooms_too_dry=3)
        "You are a home climate analyst..."
    """
    # Load from cache or file
    if file_name not in _prompt_cache:
        _prompt_cache[file_name] = _load_prompt_file(file_name)

    data = _prompt_cache.get(file_name, {})
    prompt = data.get(key, "")

    if not prompt:
        logger.warning(f"Prompt key '{key}' not found in {file_name}.yaml")
        return ""

    # Format with kwargs if provided
    if kwargs:
        try:
            prompt = prompt.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing format key in prompt {file_name}.{key}: {e}")

    return prompt


def get_prompt_section(file_name: str, key: str) -> str:
    """
    Get a raw prompt section without formatting.

    Use this when you need the template string itself,
    not a formatted version.
    """
    if file_name not in _prompt_cache:
        _prompt_cache[file_name] = _load_prompt_file(file_name)

    return _prompt_cache.get(file_name, {}).get(key, "")


def reload_prompts(file_name: Optional[str] = None):
    """
    Reload prompt files from disk.

    Call this to pick up changes without restarting.

    Args:
        file_name: Specific file to reload, or None for all
    """
    global _prompt_cache

    if file_name:
        if file_name in _prompt_cache:
            del _prompt_cache[file_name]
        _prompt_cache[file_name] = _load_prompt_file(file_name)
        logger.info(f"Reloaded prompt file: {file_name}")
    else:
        _prompt_cache.clear()
        logger.info("Cleared all prompt cache")


def list_available_prompts() -> Dict[str, list]:
    """List all available prompt files and their keys."""
    result = {}

    if not PROMPTS_DIR.exists():
        logger.warning(f"Prompts directory not found: {PROMPTS_DIR}")
        return result

    for yaml_file in PROMPTS_DIR.glob("*.yaml"):
        name = yaml_file.stem
        data = _load_prompt_file(name)
        result[name] = list(data.keys())

    return result
