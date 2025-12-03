"""
Conversational Agent - Simplified

Philosophy: Gather data, pass to LLM, let it reason.
No hardcoded intent detection or response generation.
The LLM does the work.
"""

import logging
import json
import re
from typing import Optional, Dict, Any, List

from .types import (
    ConversationResponse,
    ActionCommand,
    EventContext,
)
from .device_ontology import DeviceOntology
from .home_health_engine import HomeHealthEngine

logger = logging.getLogger(__name__)


SAFE_ACTIONS = {
    "set_temperature",
    "turn_on", "turn_off",
    "arm", "disarm",
    "open_valve", "close_valve",
    "set_humidity",
    "acknowledge",
}


class ConversationalAgentService:
    """
    Simplified conversational agent.
    
    Gathers all relevant data and passes it to the LLM.
    The LLM reasons about what to say - no hardcoded handlers.
    """

    def __init__(
        self,
        llm_provider,
        memory_service=None,
        feedback_learning=None,
        policy_engine=None,
        weather_service=None,
        rag_engine=None,
        backend_url: str = "http://localhost:8080"
    ):
        self.llm = llm_provider
        self.memory = memory_service
        self.feedback_learning = feedback_learning
        self.policy = policy_engine
        self.weather = weather_service
        self.rag_engine = rag_engine
        self.backend_url = backend_url

        # Core services
        self.ontology = DeviceOntology(backend_url=backend_url)
        self.health_engine = HomeHealthEngine(backend_url=backend_url)

        # Session memory
        self._session_memories: Dict[str, List[Dict[str, str]]] = {}
        self._current_session: Optional[str] = None

        # Config from LLM provider
        cfg = getattr(llm_provider, 'config', None)
        self.max_system_prompt_chars = getattr(cfg, 'chat_max_system_prompt_chars', 10000) if cfg else 10000
        self.max_user_message_chars = getattr(cfg, 'chat_max_user_message_chars', 2000) if cfg else 2000
        self.max_memory_turns = getattr(cfg, 'chat_max_memory_turns', 20) if cfg else 20
        self.llm_context_turns = getattr(cfg, 'chat_context_turns', 10) if cfg else 10
        self.chat_temperature = getattr(cfg, 'chat_temperature', 0.3) if cfg else 0.3
        self.chat_max_tokens = getattr(cfg, 'chat_max_tokens', 500) if cfg else 500

        logger.info(f"ConversationalAgentService initialized (simplified)")

    async def initialize(self):
        """Load device ontology."""
        success = await self.ontology.load()
        if success:
            logger.info(f"Device ontology loaded: {len(self.ontology.devices)} devices")

    # -------------------------------------------------------------------------
    # Main Chat Entry Point
    # -------------------------------------------------------------------------

    async def chat(
        self,
        message: str,
        event_context: Optional[EventContext] = None,
        home_state: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None
    ) -> ConversationResponse:
        """
        Main chat method.
        
        1. Gather all relevant data
        2. Build prompt with that data
        3. Let LLM reason and respond
        """
        self._current_session = session_id or "default"
        
        # Gather ALL data the LLM needs
        context = await self._gather_context(message, event_context, home_state)
        
        # Build system prompt with all context
        system_prompt = self._build_system_prompt(context)
        
        # Call LLM
        llm_response = await self._call_llm(system_prompt, message)
        
        # Parse response
        result = self._parse_response(llm_response)
        
        # Update memory
        self._add_to_memory("user", message)
        self._add_to_memory("assistant", result.reply)
        
        return result

    # -------------------------------------------------------------------------
    # Context Gathering - Get ALL data upfront
    # -------------------------------------------------------------------------

    async def _gather_context(
        self,
        message: str,
        event_context: Optional[EventContext],
        home_state: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Gather all relevant data for the LLM."""
        import httpx
        from datetime import datetime
        
        context = {
            "timestamp": datetime.now().isoformat(),
            "user_message": message,
        }
        
        # 1. Device Ontology - what sensors exist and where
        if self.ontology._loaded:
            context["devices"] = []
            for device in self.ontology.devices.values():
                # Extract manufacturer/model from metadata if available
                meta = device.metadata or {}
                context["devices"].append({
                    "id": device.device_id,
                    "name": device.name,
                    "type": device.type,  # e.g., "sensor", "leak_sensor", "thermostat"
                    "zone": device.zone_id,
                    "manufacturer": meta.get("manufacturer", "Unknown"),
                    "model": meta.get("model", device.name),
                })
            
            context["zones"] = []
            for zone_id, zone in self.ontology.zones.items():
                zone_devices = self.ontology.devices_by_zone.get(zone_id, [])
                context["zones"].append({
                    "id": zone_id,
                    "name": zone.name,
                    "type": zone.type,
                    "devices": [d.name for d in zone_devices],
                    "device_types": [d.type for d in zone_devices],
                    "features": self._get_zone_features(zone),
                })
        
        # 2. Home Health - current status
        try:
            health = await self.health_engine.evaluate(home_state=home_state)
            context["health"] = {
                "status": health.status.value,
                "score": health.health_score,
                "has_leak": health.has_leak,
                "has_smoke": health.has_smoke,
                "has_co": health.has_co,
                "active_alarms": health.active_alarms,
                "issues": [d.message for d in health.details[:5]],
            }
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
        
        # 3. ML Erratic Data - learned patterns
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get("http://localhost:8001/hsil/erratic")
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("erratic_devices"):
                        context["ml_erratic"] = data["erratic_devices"]
        except Exception as e:
            logger.debug(f"ML erratic fetch failed: {e}")
        
        # 4. Recent Incidents - historical problems
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{self.backend_url}/api/incidents")
                if resp.status_code == 200:
                    incidents = resp.json()
                    # Summarize - don't dump all 100+ incidents
                    if incidents:
                        context["incidents"] = {
                            "total_count": len(incidents),
                            "recent": incidents[:5],  # Last 5
                            "by_device": self._count_by_field(incidents, "device_id"),
                            "by_type": self._count_by_field(incidents, "title"),
                        }
        except Exception as e:
            logger.debug(f"Incidents fetch failed: {e}")
        
        # 5. Weather
        if self.weather and self.weather.cached_context:
            try:
                context["weather"] = self.weather.format_for_llm()
            except Exception as e:
                logger.debug(f"Weather format failed: {e}")
        
        # 6. Event Context (if triggered by an event)
        if event_context:
            context["event"] = {
                "device_id": event_context.device_id,
                "type": event_context.event_type,
                "value": event_context.event_value,
                "location": event_context.location,
            }
        
        # 7. Home State (live device readings)
        if home_state:
            context["home_state"] = home_state
        
        # 8. Conversation History
        memory = self._get_session_memory()
        if memory:
            context["conversation"] = memory[-self.llm_context_turns:]
        
        return context

    def _get_zone_features(self, zone) -> List[str]:
        """Extract zone features as a list."""
        features = []
        attrs = zone.attributes
        if attrs.floor_type:
            features.append(f"{attrs.floor_type} floor")
        if attrs.has_plumbing:
            features.append("plumbing")
        if attrs.has_water_heater:
            features.append("water heater")
        if attrs.has_washer:
            features.append("washer/dryer")
        if attrs.has_sump_pump:
            features.append("sump pump")
        if attrs.has_hvac_return:
            features.append("HVAC return")
        if attrs.has_hvac_vent:
            features.append("HVAC vent")
        if attrs.has_windows:
            features.append("windows")
        return features

    def _count_by_field(self, items: List[Dict], field: str) -> Dict[str, int]:
        """Count items by a field value."""
        counts = {}
        for item in items:
            val = item.get(field, "unknown")
            counts[val] = counts.get(val, 0) + 1
        return counts

    # -------------------------------------------------------------------------
    # System Prompt - Tell LLM what data it has and how to use it
    # -------------------------------------------------------------------------

    def _build_system_prompt(self, context: Dict[str, Any]) -> str:
        """Build system prompt with all context data."""
        
        parts = [
            "You are HomeSight, a smart home assistant.",
            "",
            "## RULES",
            "1. ONLY report data you have. If no sensor exists for something, say so.",
            "2. Each device has a TYPE that defines what it can measure:",
            "   - 'leak_sensor' or 'water_leak' or 'sensor': detects water leaks ONLY (NOT temperature/humidity)",
            "   - 'temperature_sensor': measures temperature and sometimes humidity",
            "   - 'thermostat': controls HVAC, shows temperature",
            "   - 'motion_sensor': detects motion only",
            "3. NEVER claim a sensor can measure something its type doesn't support.",
            "4. If ml_erratic shows a device with erratic_score > 0.6, ALWAYS mention this is concerning.",
            "5. 'features' are room (zone) attributes - NOT sensors. You CANNOT report their status.",
            "6. Be conversational and helpful. Suggest what you CAN help with.",
            "",
            "## YOUR DATA",
            "",
        ]
        
        # Devices
        if "devices" in context:
            parts.append("### Devices (these are your sensors)")
            for d in context["devices"]:
                parts.append(f"- {d['name']} (type: {d['type']}, model: {d.get('model', 'unknown')}) in {d['zone']}")
            parts.append("")
        
        # Zones
        if "zones" in context:
            parts.append("### Zones")
            for z in context["zones"]:
                devices_str = ", ".join(z["devices"]) if z["devices"] else "no sensors"
                types_str = ", ".join(set(z["device_types"])) if z["device_types"] else "none"
                features_str = ", ".join(z["features"]) if z["features"] else "none"
                parts.append(f"- {z['name']}: sensors=[{devices_str}] (types: {types_str}), features=[{features_str}]")
            parts.append("")
        
        # Health
        if "health" in context:
            h = context["health"]
            parts.append(f"### Home Health: {h['status'].upper()} (score: {h['score']}/100)")
            if h["has_leak"]:
                parts.append("⚠️ WATER LEAK DETECTED")
            if h["has_smoke"]:
                parts.append("⚠️ SMOKE DETECTED")
            if h["issues"]:
                for issue in h["issues"]:
                    parts.append(f"- {issue}")
            parts.append("")
        
        # ML Erratic - CRITICAL for health questions
        if "ml_erratic" in context:
            parts.append("### ⚠️ ML-Detected Erratic Behavior (IMPORTANT)")
            parts.append("These sensors show unusual rapid-fire patterns. Mention this when discussing health!")
            for e in context["ml_erratic"]:
                parts.append(f"- {e['device_id']}: erratic_score={e['erratic_score']:.0%}, rate={e.get('recent_events_per_minute', 0)}/min, trend={e.get('trend', 'unknown')}")
            parts.append("(High scores suggest sensor malfunction or false positives)")
            parts.append("")
        
        # Incidents
        if "incidents" in context:
            inc = context["incidents"]
            parts.append(f"### Incident History ({inc['total_count']} total)")
            if inc["by_type"]:
                types_str = ", ".join([f"{k}: {v}" for k, v in list(inc["by_type"].items())[:5]])
                parts.append(f"By type: {types_str}")
            parts.append("")
        
        # Weather
        if "weather" in context:
            parts.append(f"### Weather: {context['weather']}")
            parts.append("")
        
        # Home State (live readings)
        if "home_state" in context:
            parts.append("### Current Device Readings")
            state_str = json.dumps(context["home_state"], indent=2)
            if len(state_str) > 500:
                state_str = state_str[:500] + "..."
            parts.append(state_str)
            parts.append("")
        
        # Conversation
        if "conversation" in context:
            parts.append("### Recent Conversation")
            for msg in context["conversation"][-5:]:
                content = msg["content"][:150] if len(msg["content"]) > 150 else msg["content"]
                parts.append(f"[{msg['role']}]: {content}")
            parts.append("")
        
        # Response format
        parts.append("""
## RESPONSE FORMAT
Respond with JSON only:
{
  "reply": "Your conversational response here",
  "action": null
}

For actions:
{
  "reply": "Your response",
  "action": {"topic": "homesight/device/command", "command": "turn_on", "value": true}
}
""")
        
        prompt = "\n".join(parts)
        
        # Truncate if needed
        if len(prompt) > self.max_system_prompt_chars:
            prompt = prompt[:self.max_system_prompt_chars]
        
        return prompt

    # -------------------------------------------------------------------------
    # LLM Call
    # -------------------------------------------------------------------------

    async def _call_llm(self, system_prompt: str, user_message: str) -> str:
        """Call the LLM."""
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        
        # Add conversation history
        memory = self._get_session_memory()
        for msg in memory[-self.llm_context_turns:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        
        messages.append({"role": "user", "content": user_message})
        
        resp_text, _ = await self.llm.chat_async(
            messages=messages,
            temperature=self.chat_temperature,
            max_tokens=self.chat_max_tokens
        )
        
        return resp_text

    # -------------------------------------------------------------------------
    # Response Parsing
    # -------------------------------------------------------------------------

    def _parse_response(self, llm_response: str) -> ConversationResponse:
        """Parse LLM response, extracting reply and optional action."""
        action = None
        reply = llm_response
        
        try:
            # Find JSON in response
            match = re.search(r"\{(?:[^{}]|(?:\{[^}]*\}))*\}", llm_response, re.DOTALL)
            if match:
                raw = match.group(0)
                # Clean trailing commas
                cleaned = re.sub(r",\s*}", "}", raw)
                cleaned = re.sub(r",\s*]", "]", cleaned)
                
                parsed = json.loads(cleaned)
                reply = parsed.get("reply", reply)
                
                # Validate action
                if parsed.get("action"):
                    a = parsed["action"]
                    if a.get("command") in SAFE_ACTIONS:
                        action = ActionCommand(
                            topic=a["topic"],
                            command=a["command"],
                            value=a.get("value")
                        )
        except Exception as e:
            logger.warning(f"JSON parse failed: {e}")
        
        return ConversationResponse(reply=reply, action=action)

    # -------------------------------------------------------------------------
    # Memory Management
    # -------------------------------------------------------------------------

    def _get_session_memory(self) -> List[Dict[str, str]]:
        """Get memory for current session."""
        sid = self._current_session or "default"
        if sid not in self._session_memories:
            self._session_memories[sid] = []
        return self._session_memories[sid]

    def _add_to_memory(self, role: str, content: str):
        """Add message to session memory."""
        memory = self._get_session_memory()
        memory.append({"role": role, "content": content})
        if len(memory) > self.max_memory_turns:
            sid = self._current_session or "default"
            self._session_memories[sid] = memory[-self.max_memory_turns:]

    # -------------------------------------------------------------------------
    # Feedback (kept for API compatibility)
    # -------------------------------------------------------------------------

    async def provide_feedback(
        self,
        interaction_id: str,
        feedback_type: str,
        rating: Optional[int] = None,
        correction: Optional[str] = None
    ):
        """Store user feedback."""
        if self.feedback_learning:
            from .learning import UserFeedback, FeedbackType
            fb = UserFeedback(
                interaction_id=interaction_id,
                feedback_type=FeedbackType(feedback_type),
                rating=rating,
                correction=correction
            )
            await self.feedback_learning.record_feedback(fb)
