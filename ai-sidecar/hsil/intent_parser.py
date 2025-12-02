"""
Intent Parser

Lightweight NLP module that maps user language into structured intents.
Prevents hallucinations by matching against known patterns before LLM fallback.
"""

import re
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Intent:
    """Structured intent representation"""
    intent: str
    confidence: float
    target_room: Optional[str] = None
    target_device: Optional[str] = None
    target_value: Optional[Any] = None
    parameters: Optional[Dict[str, Any]] = None


class IntentParser:
    """
    Parse user messages into structured intents.

    Uses pattern matching and keyword detection to identify user intent
    before falling back to LLM processing.
    """

    def __init__(self):
        # Intent patterns: (pattern, intent_name, confidence)
        self.patterns = [
            # Valve control
            (r'\b(turn off|shut off|close|stop).*\b(water|valve|main valve)\b', 'close_main_valve', 0.95),
            (r'\b(turn on|open).*\b(water|valve|main valve)\b', 'open_main_valve', 0.95),

            # HVAC control
            (r'\b(set|adjust|change).*\b(temp|temperature)\b.*\b(\d+)', 'set_temperature', 0.9),
            (r'\b(make it|i\'m|im)\s+(warmer|hotter|colder|cooler)', 'adjust_temperature', 0.85),
            (r'\b(increase|raise|turn up).*\b(temp|temperature|heat)', 'increase_temperature', 0.9),
            (r'\b(decrease|lower|turn down).*\b(temp|temperature|heat)', 'decrease_temperature', 0.9),

            # Device control
            (r'\b(turn off|shut off|disable).*\b(light|switch|outlet)\b', 'turn_off_device', 0.9),
            (r'\b(turn on|enable).*\b(light|switch|outlet)\b', 'turn_on_device', 0.9),

            # Security
            (r'\b(arm|activate|enable).*\b(alarm|security)\b', 'arm_security', 0.95),
            (r'\b(disarm|deactivate|disable).*\b(alarm|security)\b', 'disarm_security', 0.95),

            # Status queries
            (r'\b(what\'s|what is|whats|show|check).*\b(temp|temperature)\b', 'query_temperature', 0.9),
            (r'\b(what\'s|what is|whats|show|check).*\b(humidity|humid)\b', 'query_humidity', 0.9),
            (r'\b(is there|any|check for).*\b(leak|water leak|flooding)\b', 'query_leak', 0.95),
            (r'\b(is there|any|detect).*\b(motion|movement)\b', 'query_motion', 0.9),
            (r'\b(status|state|how\'s|hows).*\b(home|house|system)\b', 'query_home_health', 0.85),
            (r'\b(status|state|how\'s|hows).*\b(room|bedroom|kitchen|bathroom|living room)\b', 'query_room_health', 0.85),

            # Environmental queries
            (r'\b(what\'s|what is|whats).*\b(weather|outside|outdoor)\b', 'query_weather', 0.9),
            (r'\b(air quality|aqi|pollution)\b', 'query_air_quality', 0.9),

            # Anomaly/alert queries
            (r'\b(any|show|check).*\b(alert|alarm|warning|problem|issue)\b', 'query_alerts', 0.9),
            (r'\b(what\'s wrong|whats wrong|anything wrong)\b', 'query_problems', 0.85),

            # Troubleshooting intents (trigger RAG queries)
            (r'\b(how do i|how to|how can i).*\b(replace|change|swap).*\b(battery|batteries)\b', 'troubleshoot_battery', 0.95),
            (r'\b(how do i|how to|how can i).*\b(reset|reboot|restart)\b', 'troubleshoot_reset', 0.9),
            (r'\b(how do i|how to|how can i).*\b(pair|connect|add|include)\b', 'troubleshoot_pairing', 0.9),
            (r'\b(how do i|how to|how can i).*\b(fix|repair|troubleshoot|solve)\b', 'troubleshoot_general', 0.85),
            (r'\b(not working|stopped working|won\'t work|doesn\'t work|broken|offline|unresponsive)\b', 'troubleshoot_not_working', 0.85),
            (r'\b(blinking|flashing).*\b(light|led)\b', 'troubleshoot_indicator', 0.9),
            (r'\b(what does|what\'s).*\b(error|code|beep|flash|blink).*\b(mean)\b', 'troubleshoot_error_code', 0.9),
            (r'\b(manual|documentation|instructions|guide|specs|specifications)\b', 'request_documentation', 0.85),
            (r'\b(model number|model|part number|serial)\b', 'query_device_info', 0.85),
            (r'\b(battery type|what battery|which battery)\b', 'query_battery_type', 0.9),
            (r'\b(warranty|support|contact|help)\b', 'request_support', 0.8),
        ]

        # Room name patterns
        self.room_patterns = [
            r'\b(bedroom|bed room|master bedroom)\b',
            r'\b(kitchen)\b',
            r'\b(bathroom|bath room|restroom)\b',
            r'\b(living room|livingroom|lounge)\b',
            r'\b(dining room|diningroom)\b',
            r'\b(garage)\b',
            r'\b(basement|cellar)\b',
            r'\b(attic)\b',
            r'\b(hallway|corridor)\b',
            r'\b(office|study)\b',
        ]

        # Temperature value extraction
        self.temp_pattern = r'\b(\d+)\s*(?:degrees?|°|deg)?\s*(?:f|fahrenheit)?\b'

        # Profanity/urgency markers (increase confidence)
        self.urgency_markers = [
            r'\b(fuck|shit|damn|hell|emergency|urgent|asap|immediately|now|quick)\b',
        ]

    def parse(self, message: str) -> Optional[Intent]:
        """
        Parse user message into structured intent.

        Args:
            message: User's message

        Returns:
            Intent object if matched, None otherwise
        """
        if not message:
            return None

        message_lower = message.lower().strip()

        # Check for urgency markers (boost confidence)
        urgency_boost = 0.0
        for pattern in self.urgency_markers:
            if re.search(pattern, message_lower, re.IGNORECASE):
                urgency_boost = 0.1
                break

        # Try to match intent patterns
        for pattern, intent_name, base_confidence in self.patterns:
            match = re.search(pattern, message_lower, re.IGNORECASE)
            if match:
                confidence = min(1.0, base_confidence + urgency_boost)

                # Extract room if present
                target_room = self._extract_room(message_lower)

                # Extract temperature value if temperature-related intent
                target_value = None
                if 'temperature' in intent_name:
                    target_value = self._extract_temperature(message_lower)

                # Extract device name if device-related intent
                target_device = None
                if 'device' in intent_name:
                    target_device = self._extract_device(message_lower)

                logger.info(f"Intent matched: {intent_name} (confidence={confidence:.2f}, room={target_room}, value={target_value})")

                return Intent(
                    intent=intent_name,
                    confidence=confidence,
                    target_room=target_room,
                    target_device=target_device,
                    target_value=target_value
                )

        logger.debug(f"No intent matched for: {message}")
        return None

    def _extract_room(self, message: str) -> Optional[str]:
        """Extract room name from message"""
        for pattern in self.room_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                room = match.group(1)
                # Normalize room name
                room = room.replace(' ', '_').lower()
                return room
        return None

    def _extract_temperature(self, message: str) -> Optional[float]:
        """Extract temperature value from message"""
        match = re.search(self.temp_pattern, message, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except (ValueError, IndexError):
                pass
        return None

    def _extract_device(self, message: str) -> Optional[str]:
        """Extract device name from message"""
        # Simple device name extraction (can be enhanced)
        device_keywords = ['light', 'switch', 'outlet', 'plug', 'lamp', 'fan']
        for keyword in device_keywords:
            if keyword in message:
                return keyword
        return None

    def get_all_intents(self) -> List[str]:
        """Return list of all recognized intents"""
        return list(set(intent for _, intent, _ in self.patterns))

    def is_troubleshooting_intent(self, intent: Optional['Intent']) -> bool:
        """Check if the intent requires RAG document lookup"""
        if not intent:
            return False
        
        troubleshooting_intents = {
            'troubleshoot_battery',
            'troubleshoot_reset',
            'troubleshoot_pairing',
            'troubleshoot_general',
            'troubleshoot_not_working',
            'troubleshoot_indicator',
            'troubleshoot_error_code',
            'request_documentation',
            'query_device_info',
            'query_battery_type',
            'request_support',
        }
        
        return intent.intent in troubleshooting_intents
