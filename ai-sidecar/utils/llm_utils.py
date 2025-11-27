"""
Utility functions for working with LLM responses.
"""

import json
import logging
from typing import Optional, Dict, Any, Type
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def extract_json_from_llm_response(
    response: str,
    model: Optional[Type[BaseModel]] = None,
    fallback: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Extract and parse JSON from LLM response text.

    LLMs sometimes wrap JSON in markdown code blocks or add extra text.
    This function robustly extracts the JSON portion and validates it.

    Args:
        response: The raw LLM response string
        model: Optional Pydantic model to validate against
        fallback: Optional fallback dict to return on parse failure

    Returns:
        Parsed JSON dict, or fallback if parsing fails

    Examples:
        >>> response = "Here's the result:\\n{\"status\": \"ok\"}\\nLet me know!"
        >>> extract_json_from_llm_response(response)
        {'status': 'ok'}

        >>> extract_json_from_llm_response("Invalid", fallback={"error": "parse_failed"})
        {'error': 'parse_failed'}
    """
    if not response or not isinstance(response, str):
        logger.warning("Invalid response for JSON extraction")
        return fallback

    try:
        # Strategy 1: Try direct parse (common for well-formatted responses)
        try:
            parsed = json.loads(response)
            if model:
                # Validate with Pydantic if model provided
                model(**parsed)
            return parsed
        except (json.JSONDecodeError, ValueError):
            pass

        # Strategy 2: Extract JSON from markdown code blocks
        # Common pattern: ```json\\n{...}\\n```
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            if end > start:
                json_str = response[start:end].strip()
                parsed = json.loads(json_str)
                if model:
                    model(**parsed)
                return parsed

        # Strategy 3: Find first { to last } (handles wrapped JSON)
        json_start = response.find("{")
        json_end = response.rfind("}") + 1

        if json_start != -1 and json_end > json_start:
            json_str = response[json_start:json_end]
            parsed = json.loads(json_str)
            if model:
                model(**parsed)
            return parsed

        # Strategy 4: Try finding array notation
        array_start = response.find("[")
        array_end = response.rfind("]") + 1

        if array_start != -1 and array_end > array_start:
            json_str = response[array_start:array_end]
            parsed = json.loads(json_str)
            if model:
                model(**parsed)
            return parsed

        logger.warning(f"No JSON found in response: {response[:100]}...")
        return fallback

    except json.JSONDecodeError as e:
        logger.warning(f"JSON decode error: {e}, response: {response[:100]}...")
        return fallback
    except Exception as e:
        logger.error(f"Unexpected error extracting JSON: {e}")
        return fallback
