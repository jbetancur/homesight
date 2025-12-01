"""
Conversational Agent (Production-safe)

- Safe for local LLMs (prompt truncation, formatting, no special-token conflicts)
- Robust JSON parsing (regex-based, trailing comma cleanup)
- Action validation for safety
- Lean, LLM-friendly event + weather formatting
- Avoids huge prompt expansion
"""

import logging
import json
import re
from typing import Optional, Dict, Any, List

from .types import (
    ConversationRequest,
    ConversationResponse,
    ActionCommand,
    EventContext,
    MemoryEntry
)
from .intent_parser import IntentParser
from .device_ontology import DeviceOntology
from .home_health_engine import HomeHealthEngine
from .temperature_preference_model import TemperaturePreferenceModel
from .temperature_intent import TemperatureIntent

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
    Conversational interface to HSIL using cloud or local LLMs.
    Production-safe version.
    """

    def __init__(
        self,
        llm_provider,
        memory_service,
        feedback_learning,
        policy_engine,
        weather_service=None,
        backend_url: str = "http://localhost:8080"
    ):
        self.llm = llm_provider
        self.memory = memory_service
        self.feedback_learning = feedback_learning
        self.policy = policy_engine
        self.weather = weather_service

        # Production safety features
        self.intent_parser = IntentParser()
        self.ontology = DeviceOntology(backend_url=backend_url)

        # Home intelligence features
        self.health_engine = HomeHealthEngine(backend_url=backend_url)
        self.temp_model = TemperaturePreferenceModel()
        self.temp_intent = TemperatureIntent()

        # Conversation memory (last 10 turns)
        self.conversation_memory: List[Dict[str, str]] = []

        self.max_system_prompt_chars = 6000
        self.max_user_message_chars = 2000

        logger.info("ConversationalAgentService initialized (context-aware + preference-learning + home-aware)")

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    async def initialize(self):
        """Initialize device ontology (call after construction)"""
        success = await self.ontology.load()
        if success:
            logger.info(f"Device ontology loaded: {len(self.ontology.devices)} devices")
        else:
            logger.warning("Failed to load device ontology")

    async def chat(
        self,
        message: str,
        event_context: Optional[EventContext] = None,
        home_state: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None
    ) -> ConversationResponse:

        # Handle temperature intents BEFORE LLM (prevent "What temperature?" questions)
        if self.temp_intent.is_temperature_related(message):
            temp_response = await self._handle_temperature_request(message, home_state)
            if temp_response:
                # Add to conversation memory
                self.conversation_memory.append({"role": "user", "content": message})
                self.conversation_memory.append({"role": "assistant", "content": temp_response.reply})
                if len(self.conversation_memory) > 20:
                    self.conversation_memory = self.conversation_memory[-20:]
                return temp_response

        # Try intent parser for other intents
        intent = self.intent_parser.parse(message)
        if intent and intent.confidence > 0.85:
            logger.info(f"High-confidence intent: {intent.intent} ({intent.confidence:.2f})")
            # Intent handling could be added here for direct responses

        # Check if this is a room/zone query - handle directly for better responses
        room_query = self._detect_room_query(message)
        logger.info(f"Room query detection: message='{message}', detected_zone={room_query}, ontology_loaded={self.ontology._loaded}")
        if room_query:
            room_response = await self._handle_room_query(room_query, home_state)
            if room_response:
                self.conversation_memory.append({"role": "user", "content": message})
                self.conversation_memory.append({"role": "assistant", "content": room_response.reply})
                if len(self.conversation_memory) > 20:
                    self.conversation_memory = self.conversation_memory[-20:]
                return room_response

        context = await self._build_context(message, event_context, home_state)

        system_prompt = await self._build_system_prompt(context)
        llm_response = await self._call_llm(system_prompt, message)

        parsed = await self._parse_llm_response(llm_response, context)

        # Add to conversation memory
        self.conversation_memory.append({"role": "user", "content": message})
        self.conversation_memory.append({"role": "assistant", "content": parsed.reply})
        if len(self.conversation_memory) > 20:
            self.conversation_memory = self.conversation_memory[-20:]

        return parsed

    def _detect_room_query(self, message: str) -> Optional[str]:
        """Detect if user is asking about a specific room/zone."""
        message_lower = message.lower()
        
        # Common patterns for room queries
        room_patterns = [
            "tell me about", "what's in", "whats in", "what is in",
            "how is", "how's", "status of", "check on", "check the",
            "about my", "about the"
        ]
        
        # Check if message matches a room query pattern
        is_room_query = any(pattern in message_lower for pattern in room_patterns)
        
        if is_room_query and self.ontology._loaded:
            # Find which room they're asking about
            for zone_id in self.ontology.zone_ids:
                zone = self.ontology.zones.get(zone_id)
                if zone:
                    zone_name_lower = zone.name.lower()
                    zone_id_lower = zone_id.lower().replace("-", " ").replace("_", " ")
                    if zone_name_lower in message_lower or zone_id_lower in message_lower:
                        return zone_id
        
        return None

    async def _handle_room_query(
        self,
        zone_id: str,
        home_state: Optional[Dict[str, Any]]
    ) -> Optional[ConversationResponse]:
        """Handle a query about a specific room with comprehensive response."""
        zone = self.ontology.zones.get(zone_id)
        if not zone:
            return None
        
        devices = self.ontology.devices_by_zone.get(zone_id, [])
        attrs = zone.attributes
        
        # Build comprehensive response
        parts = []
        
        # 1. Intro with device overview
        if devices:
            device_list = [f"{d.name} ({d.type})" for d in devices]
            if len(devices) == 1:
                parts.append(f"Your {zone.name.lower()} has a {device_list[0]} sensor.")
            else:
                parts.append(f"Your {zone.name.lower()} has {len(devices)} devices: {', '.join(device_list)}.")
        else:
            parts.append(f"Your {zone.name.lower()} doesn't have any sensors installed yet.")
        
        # 2. Device status from home_state (if available)
        if home_state and devices:
            device_states = home_state.get("devices", []) if isinstance(home_state, dict) else []
            for device in devices:
                for ds in device_states:
                    if isinstance(ds, dict) and ds.get("id") == device.device_id:
                        state = ds.get("state", "normal")
                        if state == "normal":
                            parts.append(f"The {device.name} is reporting normal status (no alerts).")
                        else:
                            parts.append(f"⚠️ The {device.name} status: {state}")
                        break
        
        # 3. Room features
        features = []
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
        
        if features:
            parts.append(f"Room features: {', '.join(features)}.")
        
        # 4. Follow-up offer
        if devices:
            parts.append("\nWould you like me to check the sensor's battery level, view recent history, or look for any past incidents in this room?")
        else:
            parts.append("\nWould you like to add sensors to this room for monitoring?")
        
        reply = " ".join(parts)
        
        return ConversationResponse(reply=reply, action=None)

    # ---------------------------------------------------------------------
    # Temperature Intent Handling
    # ---------------------------------------------------------------------

    async def _handle_temperature_request(
        self,
        message: str,
        home_state: Optional[Dict[str, Any]]
    ) -> Optional[ConversationResponse]:
        """
        Handle temperature requests WITHOUT asking follow-up questions.

        Resolves deltas automatically using ML or intent parsing.
        """
        # Get current temperature from home state
        current_temp = None
        if home_state:
            # Handle both dict and HomeState object
            devices_list = []
            if isinstance(home_state, dict):
                devices_list = home_state.get("devices", [])
            elif hasattr(home_state, 'devices'):
                devices_list = home_state.devices

            for device in devices_list:
                # Handle both dict and DeviceState object
                if isinstance(device, dict):
                    state = device.get("state", {})
                else:
                    state = device.state if hasattr(device, 'state') else {}

                if isinstance(state, dict) and "temperature" in state:
                    current_temp = state["temperature"]
                    break

        if current_temp is None:
            return ConversationResponse(
                reply="I don't have temperature sensor data right now.",
                action=None
            )

        # Check for explicit target temperature
        target_temp = self.temp_intent.extract_target_temperature(message)

        if target_temp:
            # Explicit target ("set to 72")
            self.temp_model.learn_from_command(message, current_temp, target_temp=target_temp)

            action = ActionCommand(
                topic="homesight/hvac/command",
                command="set_temperature",
                value=target_temp
            )

            return ConversationResponse(
                reply=f"Setting temperature to {target_temp}°F.",
                action=action
            )

        # Check for delta intent ("make it warmer")
        delta = self.temp_intent.parse(message)

        if delta is not None:
            # Intent parsed delta
            new_temp = current_temp + delta
            self.temp_model.learn_from_command(message, current_temp, delta=delta)

            action = ActionCommand(
                topic="homesight/hvac/command",
                command="set_temperature",
                value=new_temp
            )

            return ConversationResponse(
                reply=f"Adjusting temperature by {delta:+d}°F to {new_temp:.0f}°F.",
                action=action
            )

        # Use ML prediction
        outdoor_temp = None
        if self.weather and self.weather.cached_context:
            outdoor_temp = self.weather.cached_context.weather.temperature

        predicted_delta = self.temp_model.predict_adjustment(message, current_temp, outdoor_temp)

        if predicted_delta:
            new_temp = current_temp + predicted_delta
            self.temp_model.learn_from_command(message, current_temp, delta=predicted_delta)

            action = ActionCommand(
                topic="homesight/hvac/command",
                command="set_temperature",
                value=new_temp
            )

            return ConversationResponse(
                reply=f"Adjusting temperature by {predicted_delta:+d}°F to {new_temp:.0f}°F based on your preferences.",
                action=action
            )

        # Fallback: no clear intent
        return None

    # ---------------------------------------------------------------------
    # Context Builder
    # ---------------------------------------------------------------------

    async def _build_context(
        self,
        message: str,
        event_context: Optional[EventContext],
        home_state: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:

        context = {
            "user_message": message,
            "timestamp": __import__("datetime").datetime.now().isoformat()
        }

        # Event context (flattened for LLMs)
        if event_context:
            context["event"] = {
                "device_id": event_context.device_id,
                "type": event_context.event_type,
                "value": event_context.event_value,
                "location": event_context.location,
                "trend_1h": event_context.trend_1h,
                "anomaly_score": event_context.anomaly_score,
            }

        # Home state (keep only essential fields)
        if home_state:
            # truncate large fields for local LLM
            clipped_state = json.loads(json.dumps(home_state))  # deep copy
            context["home_state"] = clipped_state

        # Weather from cache (NEVER fetch during chat)
        if self.weather and self.weather.cached_context:
            try:
                context["environment"] = self.weather.format_for_llm()
            except Exception as e:
                logger.warning(f"Weather formatting failed: {e}")

        # Device ontology summary
        if self.ontology._loaded:
            summary = self.ontology.get_device_summary()
            context["device_summary"] = summary
            logger.info(f"Device summary zones: {list(summary.get('zone_details', {}).keys())}")
        else:
            logger.warning("Device ontology not loaded, skipping device_summary")

        # Home health assessment (authoritative status)
        home_health = await self.health_engine.evaluate(home_state=home_state)
        context["home_health"] = {
            "status": home_health.status.value,
            "score": home_health.health_score,
            "has_leak": home_health.has_leak,
            "has_smoke": home_health.has_smoke,
            "has_co": home_health.has_co,
            "active_alarms": home_health.active_alarms,
            "details": [d.message for d in home_health.details[:5]]  # Top 5 issues
        }

        # Temperature preference range
        temp_range = self.temp_model.get_preferred_range()
        context["temp_preferences"] = {
            "min": temp_range[0],
            "max": temp_range[1]
        }

        # Conversation memory (last 6 turns for context)
        if self.conversation_memory:
            context["conversation_history"] = self.conversation_memory[-6:]

        # Memory search
        try:
            if self.memory:
                mems = await self.memory.search_keyword(message, limit=3)
                context["memories"] = [
                    {"content": m.content, "type": m.type.value} for m in mems
                ]
        except Exception as e:
            logger.warning(f"Memory retrieval failed: {e}")

        # User feedback preferences
        try:
            if self.feedback_learning:
                prefs = await self.feedback_learning.get_all_preferences(min_confidence=0.6)
                if prefs:
                    context["user_preferences"] = prefs
        except Exception as e:
            logger.warning(f"Failed prefs: {e}")

        # RAG context
        if hasattr(self, "rag_engine") and self.rag_engine:
            try:
                rag = self.rag_engine.query(message, n_results=3)
                docs = [
                    f"[{r['metadata'].get('source','Unknown')}]: {r['text'][:150]}"
                    for r in rag
                    if r.get("relevance_score", 0) > 0.25
                ]
                if docs:
                    context["rag_context"] = docs
            except Exception as e:
                logger.warning(f"RAG failure: {e}")

        # Session history
        if hasattr(self, "session_history") and self.session_history:
            context["session_history"] = self.session_history[-4:]

        return context

    # ---------------------------------------------------------------------
    # Prompt Builder
    # ---------------------------------------------------------------------

    async def _build_system_prompt(self, context: Dict[str, Any]) -> str:
        """
        Create a concise system prompt for local/cloud LLMs.
        """

        p = [
            "You are HomeSight, a contextual, preference-learning home assistant.",
            "",
            "CRITICAL RULES (NEVER VIOLATE):",
            "1. NEVER invent sensor data - only use provided context",
            "2. NEVER contradict yourself or home_health status",
            "3. NEVER ask follow-up questions for temperature (already handled)",
            "4. ONLY use devices listed in device_summary",
            "5. ONLY use safe commands: " + ", ".join(SAFE_ACTIONS),
            "6. If home_health says 'critical' or 'has_leak=true', YOU MUST acknowledge it",
            "7. If home_health says 'good', DON'T invent problems",
            "",
            "RESPONSE STYLE:",
            "- When asked about a room/zone, provide a COMPLETE overview:",
            "  1. Room features/attributes (floor type, plumbing, HVAC, etc.)",
            "  2. ALL devices/sensors in that room with their current status",
            "  3. Any active incidents or alerts in that room",
            "  4. Offer to provide more details (battery levels, history, trends)",
            "- Be conversational and helpful, not just factual",
            "- End responses about rooms with a helpful follow-up offer",
            "",
            "EXAMPLE (for room query):",
            "User: tell me about my basement",
            "Response: Your basement has a ZSE42 leak sensor which is currently reporting normal (no water detected).",
            "The room features include: concrete floor, plumbing, water heater, washer/dryer, and sump pump.",
            "Would you like me to check the sensor's battery level, view its recent history, or check for any past incidents?",
            "",
            "Capabilities:",
            "- Remember conversation history",
            "- Learn temperature preferences",
            "- Provide authoritative home status (from home_health)",
            "",
        ]

        # Home Health (AUTHORITATIVE - prevent contradictions)
        if "home_health" in context:
            hh = context["home_health"]
            p.append(f"HOME STATUS (authoritative, DO NOT contradict):")
            p.append(f"  Status: {hh['status'].upper()} (score: {hh['score']}/100)")

            if hh["has_leak"]:
                p.append(f"  ⚠️ WATER LEAK DETECTED")
            if hh["has_smoke"]:
                p.append(f"  ⚠️ SMOKE DETECTED")
            if hh["has_co"]:
                p.append(f"  ⚠️ CO DETECTED")

            if hh["active_alarms"] > 0:
                p.append(f"  Active Alarms: {hh['active_alarms']}")

            if hh.get("details"):
                p.append(f"  Issues:")
                for detail in hh["details"]:
                    p.append(f"    - {detail}")
            elif hh["status"] == "good":
                p.append(f"  ✓ All systems normal")

            p.append("")

        # Conversation history
        if "conversation_history" in context:
            p.append("Recent Conversation:")
            for msg in context["conversation_history"]:
                role = msg["role"]
                content = msg["content"][:100]
                p.append(f"  [{role}] {content}")
            p.append("")

        p.append("Current Context:")

        # Device ontology summary with zone details
        if "device_summary" in context:
            summary = context["device_summary"]
            p.append(f"Devices: {summary.get('total_devices', 0)} total")
            p.append(f"Rooms: {', '.join(summary.get('rooms', []))}")
            if summary.get('rooms_with_temperature'):
                p.append(f"Temp sensors in: {', '.join(summary['rooms_with_temperature'])}")
            if summary.get('rooms_with_leak_detection'):
                p.append(f"Leak sensors in: {', '.join(summary['rooms_with_leak_detection'])}")
            
            # Include zone details with attributes and devices
            zone_details = summary.get('zone_details', {})
            if zone_details:
                p.append("")
                p.append("ZONE DETAILS (ALWAYS include devices when asked about a room):")
                for zone_id, info in zone_details.items():
                    p.append(f"  📍 {info.get('name', zone_id)} ({info.get('type', 'unknown')}):")
                    
                    # Devices with types
                    devices = info.get('devices', [])
                    if devices:
                        p.append(f"     Sensors/Devices: {', '.join(devices)}")
                    else:
                        p.append(f"     Sensors/Devices: None installed")
                    
                    # Room features
                    attrs = info.get('attributes', [])
                    if attrs:
                        p.append(f"     Features: {', '.join(attrs)}")

        if "home_state" in context:
            p.append(f"Home State: {json.dumps(context['home_state'], indent=2)[:500]}")

        if "event" in context:
            ev = context["event"]
            p.append(
                f"Event: device={ev['device_id']} type={ev['type']} "
                f"value={ev['value']} location={ev['location']} "
                f"anomaly={ev['anomaly_score']}"
            )

        if "environment" in context:
            p.append(f"Weather: {context['environment']}")

        if "user_preferences" in context:
            p.append("User Preferences:")
            for k, v in context["user_preferences"].items():
                p.append(f"- {k}: {v}")

        if "memories" in context:
            p.append("Relevant Past Interactions:")
            for mem in context["memories"]:
                p.append(f"- [{mem['type']}] {mem['content']}")

        if "rag_context" in context:
            p.append("Documentation:")
            for d in context["rag_context"]:
                p.append(f"- {d}")

        if "session_history" in context:
            p.append("Recent Conversation:")
            for msg in context["session_history"]:
                p.append(f"- [{msg['role']}] {msg['content'][:120]}")

        # ML health summaries (if provided by River ML)
        if "ml_room_health" in context:
            p.append(f"Room Health (ML): {context['ml_room_health']}")

        if "ml_home_health" in context:
            p.append(f"Home Health (ML): {context['ml_home_health']}")

        # Output format (no extra backticks)
        p.append("""
Respond ONLY with valid JSON:

{
  "reply": "Your full, helpful response here. Include all relevant details and a follow-up question or offer when appropriate.",
  "action": {
    "topic": "homesight/device/command",
    "command": "cmd",
    "value": 123
  }
}

If no action is needed, set:
"action": null

IMPORTANT: The "reply" field should be conversational and complete - include device status, room features, AND a helpful follow-up offer.
""")

        prompt = "\n".join(p)
        return prompt

    # ---------------------------------------------------------------------
    # LLM Call
    # ---------------------------------------------------------------------

    async def _call_llm(self, system_prompt: str, user_message: str) -> str:

        if self.llm.chat_mode == "local":
            system_prompt = system_prompt[-self.max_system_prompt_chars:]
            user_message = user_message[-self.max_user_message_chars:]

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        resp_text, _ = await self.llm.chat_async(
            messages=messages,
            temperature=0.7,
            max_tokens=400
        )

        return resp_text

    # ---------------------------------------------------------------------
    # JSON Response Parsing (robust)
    # ---------------------------------------------------------------------

    async def _parse_llm_response(
        self, llm_response: str, context: Dict[str, Any]
    ) -> ConversationResponse:

        action = None
        reply = llm_response

        try:
            # Find any JSON object in the output
            match = re.search(r"\{(?:[^{}]|(?:\{[^}]*\}))*\}", llm_response, re.DOTALL)

            if match:
                raw = match.group(0)

                # Remove trailing commas
                cleaned = re.sub(r",\s*}", "}", raw)
                cleaned = re.sub(r",\s*]", "]", cleaned)

                parsed = json.loads(cleaned)
                reply = parsed.get("reply", reply)

                # Validate action
                if parsed.get("action"):
                    a = parsed["action"]
                    cmd = a.get("command")

                    if cmd in SAFE_ACTIONS:
                        action = ActionCommand(
                            topic=a["topic"],
                            command=cmd,
                            value=a["value"]
                        )
                    else:
                        logger.warning(f"Blocked unsafe action: {cmd}")

        except Exception as e:
            logger.warning(f"JSON parse failed: {e}")

        # Use policy engine fallback
        if not action and self.policy:
            try:
                decision = await self.policy.evaluate_user_intent(
                    intent=context.get("user_message", ""),
                    context=context.get("home_state", {})
                )
                if decision.action:
                    action = decision.action
                    if decision.reasoning:
                        reply += f"\n({decision.reasoning})"
            except Exception as e:
                logger.warning(f"Policy engine error: {e}")

        return ConversationResponse(reply=reply, action=action)

    # ---------------------------------------------------------------------

    async def provide_feedback(
        self,
        interaction_id: str,
        feedback_type: str,
        rating: Optional[int] = None,
        correction: Optional[str] = None
    ):
        """Store user feedback for long-term learning."""
        if not self.feedback_learning:
            return

        from .learning import UserFeedback, FeedbackType

        fb = UserFeedback(
            interaction_id=interaction_id,
            feedback_type=FeedbackType(feedback_type),
            rating=rating,
            correction=correction
        )

        await self.feedback_learning.record_feedback(fb)
        logger.info(f"Feedback recorded: {fb}")
