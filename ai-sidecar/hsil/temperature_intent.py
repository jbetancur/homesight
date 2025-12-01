"""
Temperature Intent Mapper

Maps natural language to temperature deltas.
Prevents LLM from asking "What temperature would you like?"
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class TemperatureIntent:
    """
    Natural language → temperature delta mapper.

    Examples:
    - "make it warmer" → +2
    - "a little warmer" → +1
    - "much colder" → -3
    - "freeze me" → -5
    - "too hot" → -2
    - "too cold" → +2
    - "fix the temperature" → use ML prediction
    """

    def __init__(self):
        # Delta patterns: (pattern, delta)
        self.patterns = [
            # Extreme cold requests
            (r'\b(freeze|freezing|arctic|ice cold)\b', -5),
            (r'\b(much colder|way colder|a lot colder|super cold)\b', -3),

            # Moderate cold requests
            (r'\b(colder|cooler)\b', -2),
            (r'\b(a (little|bit) colder|slightly colder)\b', -1),

            # Too hot (complaints)
            (r'\b(too hot|too warm|way too hot|burning up|sweating)\b', -2),
            (r'\b(it\'s hot|i\'m hot|feeling hot)\b', -2),

            # Extreme warm requests
            (r'\b(bake me|roast|super hot|way hotter|much warmer)\b', +5),
            (r'\b(a lot warmer|way warmer|much hotter)\b', +3),

            # Moderate warm requests
            (r'\b(warmer|hotter)\b', +2),
            (r'\b(a (little|bit) warmer|slightly warmer)\b', +1),

            # Too cold (complaints)
            (r'\b(too cold|freezing|frozen|chilly|shivering)\b', +2),
            (r'\b(it\'s cold|i\'m cold|feeling cold)\b', +2),

            # Neutral/fix requests (return None for ML prediction)
            (r'\b(fix (the )?temp|comfortable|just right)\b', None),
        ]

    def parse(self, message: str) -> Optional[int]:
        """
        Parse user message for temperature delta.

        Args:
            message: User's message

        Returns:
            Temperature delta (-5 to +5) or None for ML prediction
        """
        if not message:
            return None

        message_lower = message.lower().strip()

        # Try patterns in order (first match wins)
        for pattern, delta in self.patterns:
            if re.search(pattern, message_lower, re.IGNORECASE):
                if delta is not None:
                    logger.info(f"Temperature intent matched: '{pattern}' → {delta:+d}°F")
                else:
                    logger.info(f"Temperature intent matched: '{pattern}' → ML prediction")
                return delta

        # Check for explicit temperature values
        temp_match = re.search(r'\b(\d+)\s*(?:degrees?|°|deg)?\s*(?:f|fahrenheit)?\b', message_lower)
        if temp_match:
            target_temp = int(temp_match.group(1))
            # Don't return delta here - let caller handle explicit target
            logger.info(f"Explicit temperature found: {target_temp}°F")
            return None

        logger.debug(f"No temperature intent matched for: {message}")
        return None

    def extract_target_temperature(self, message: str) -> Optional[int]:
        """
        Extract explicit target temperature from message.

        Args:
            message: User's message

        Returns:
            Target temperature or None
        """
        if not message:
            return None

        message_lower = message.lower().strip()

        # Look for explicit temperature values
        temp_match = re.search(r'\b(\d+)\s*(?:degrees?|°|deg)?\s*(?:f|fahrenheit)?\b', message_lower)
        if temp_match:
            temp = int(temp_match.group(1))
            # Sanity check (reasonable indoor temperature range)
            if 60 <= temp <= 85:
                logger.info(f"Extracted target temperature: {temp}°F")
                return temp

        return None

    def is_temperature_related(self, message: str) -> bool:
        """Check if message is temperature-related"""
        if not message:
            return False

        message_lower = message.lower()

        keywords = [
            "temp", "temperature", "hot", "cold", "warm", "cool", "heat",
            "freezing", "chilly", "sweating", "comfortable", "degrees"
        ]

        return any(keyword in message_lower for keyword in keywords)
