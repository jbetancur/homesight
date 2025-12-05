"""
Conversational Agent - LLM-as-Orchestrator Pattern

Architecture: LLM → [Tools] → LLM → Response
- LLM selects which tools to invoke
- Tools execute deterministically
- LLM synthesizes results into natural language
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
from .tools import ToolRegistry

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
    LLM-as-Orchestrator Conversational Agent.

    The LLM decides which tools to invoke, then synthesizes results.
    No hardcoded intent detection - pure orchestration.
    """

    def __init__(
        self,
        llm_provider,
        learning_engine=None,
        memory_service=None,
        feedback_learning=None,
        policy_engine=None,
        weather_service=None,
        rag_engine=None,
        backend_url: str = "http://localhost:8080"
    ):
        self.llm = llm_provider
        self.learning_engine = learning_engine
        self.memory = memory_service
        self.feedback_learning = feedback_learning
        self.policy = policy_engine
        self.weather = weather_service
        self.rag_engine = rag_engine
        self.backend_url = backend_url

        # Core services
        self.ontology = DeviceOntology(backend_url=backend_url)
        self.health_engine = HomeHealthEngine(backend_url=backend_url)

        # Tool Registry - enables LLM function calling
        self.tools = ToolRegistry(
            learning_engine=learning_engine,
            memory=memory_service,
            db_path=None
        )

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

        logger.info(f"ConversationalAgentService initialized (orchestrator pattern)")

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
        Main chat method - Orchestrator Pattern.

        Flow:
        1. LLM plans which tools to invoke
        2. Execute tools deterministically
        3. LLM synthesizes results into response
        """
        self._current_session = session_id or "default"

        # Gather lightweight context (only essentials)
        context = await self._gather_context(message, event_context, home_state)

        # LLM orchestration: plan → execute → synthesize
        llm_response = await self._orchestrate_with_tools(message, context)

        # Parse response
        result = self._parse_response(llm_response)

        # Update memory
        self._add_to_memory("user", message)
        self._add_to_memory("assistant", result.reply)

        return result

    async def _orchestrate_with_tools(
        self,
        message: str,
        context: Dict[str, Any]
    ) -> str:
        """
        LLM orchestration with function calling.

        The LLM decides which tools to call, we execute them,
        then the LLM synthesizes the results.
        """
        logger.info(f"🔧 Orchestrating with {len(self.tools.tools)} tools available")

        # Build system prompt with tool awareness
        system_prompt = self._build_orchestrator_prompt(context)

        # Get tool schemas for function calling
        tool_schemas = self.tools.get_tool_schemas()

        # First LLM call: planning (with tool selection)
        messages = self._build_messages(system_prompt, message)

        try:
            # Call LLM with tools - it may request tool invocations
            llm_response = await self._call_llm_with_tools(messages, tool_schemas)

            # Check if LLM wants to call tools
            tool_calls = self._extract_tool_calls(llm_response)

            if tool_calls:
                tool_names = [t['name'] for t in tool_calls]
                logger.info(f"🔧 LLM requested tools: {tool_names}")

                # Execute each tool
                tool_results = await self._execute_tools(tool_calls)

                # Add tool results to context
                messages.append({"role": "assistant", "content": llm_response})
                messages.append({
                    "role": "user",
                    "content": f"Tool results: {json.dumps(tool_results, indent=2)}"
                })

                # Second LLM call: synthesis with tool results
                final_response = await self._call_llm_simple(messages)
                return final_response

            # No tools needed - direct response
            logger.info("💬 LLM responded directly (no tools needed)")
            return llm_response

        except Exception as e:
            logger.error(f"Orchestration error: {e}")
            # Fallback to simple call
            return await self._call_llm_simple(messages)

    async def _execute_tools(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute tool calls and return results"""
        results = []

        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            arguments = tool_call.get("arguments", {})

            result = await self.tools.execute_tool(tool_name, arguments)
            results.append({
                "tool": tool_name,
                "arguments": arguments,
                **result
            })

        return results

    def _extract_tool_calls(self, llm_response: str) -> List[Dict[str, Any]]:
        """
        Extract tool calls from LLM response.

        Supports multiple formats:
        - JSON function calling (if LLM supports it)
        - Embedded JSON blocks in response
        """
        tool_calls = []

        # Try to find JSON tool call blocks in response
        # Format: ```json\n{"tool": "check_anomaly", "args": {...}}```
        json_blocks = re.findall(r'```json\s*(\{.*?\})\s*```', llm_response, re.DOTALL)

        for block in json_blocks:
            try:
                parsed = json.loads(block)
                if "tool" in parsed:
                    tool_calls.append({
                        "name": parsed["tool"],
                        "arguments": parsed.get("args", parsed.get("arguments", {}))
                    })
            except json.JSONDecodeError:
                continue

        return tool_calls

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
    # LLM Orchestrator Prompt
    # -------------------------------------------------------------------------

    def _build_orchestrator_prompt(self, context: Dict[str, Any]) -> str:
        """
        Build system prompt for LLM orchestrator.

        Lightweight - only essential context. LLM will use tools for detailed data.
        """
        parts = [
            "You are HomeSight, a friendly AI assistant helping homeowners monitor their smart home.",
            "",
            "## Your Communication Style",
            "- Use plain, conversational language (avoid technical jargon like 'anomaly', 'erratic', 'baseline')",
            "- Speak like you're talking to a friend, not an engineer",
            "- Instead of 'anomaly detected', say 'something unusual happened'",
            "- Instead of 'erratic behavior', say 'acting strange' or 'behaving oddly'",
            "- Instead of 'baseline metrics', say 'normal patterns' or 'typical behavior'",
            "- Be proactive: if you see issues or patterns, mention them even if not directly asked",
            "",
            "## Your Role",
            "You have access to tools to check device history, detect unusual patterns, and answer questions.",
            "Use tools intelligently to gather data, then explain findings in simple terms.",
            "",
            "## Core Context",
        ]

        # Minimal device list
        if "devices" in context:
            parts.append(f"### Devices: {len(context['devices'])} sensors installed")
            parts.append("")

        # Health summary
        if "health" in context:
            h = context["health"]
            parts.append(f"### Home Status: {h['status'].upper()} (score: {h['score']}/100)")
            parts.append("")

        # Weather
        if "weather" in context:
            parts.append(f"### Weather: {context['weather']}")
            parts.append("")

        parts.append("""
## Tool Usage Strategy

1. **Understand intent**: What is the homeowner really asking? (e.g., "anything wrong?" means check for unusual activity)
2. **Be smart about tools**: Use incident history for "when did X happen", erratic checks for "acting weird", baselines for "normal vs unusual"
3. **Execute**: I'll run the tools and give you results
4. **Translate to human**: Take technical results and explain them conversationally

## Examples of Natural Understanding

User: "Has my basement sensor been acting up lately?"
→ Think: They want to know if anything unusual happened
→ Use: check_erratic_behavior(device_id="basement-sensor") + get_device_incidents(device_id="basement-sensor")
→ Respond: "I checked your basement sensor - it's been working normally. Last detected water on [date], but nothing since then."

User: "When did I last have a leak?"
→ Think: They want recent incident history
→ Use: get_recent_incidents(limit=10) and filter for leak-related
→ Respond: "The last time a leak was detected was [date] in the [location]. Everything's been dry since then."

User: "Anything weird happening?"
→ Think: General health check - look for unusual patterns, recent incidents, devices acting strange
→ Use: get_erratic_devices() + get_recent_incidents(limit=5)
→ Respond: Natural summary of findings or "Everything looks good - no unusual activity detected."

User: "Is my [device] broken?"
→ Think: Check recent activity, incidents, and behavior patterns
→ Use: get_device_incidents() + check_erratic_behavior()
→ Respond: Give clear yes/no with evidence

## Response Format
Always respond conversationally in plain English. If you need to call tools, include JSON blocks.
Be helpful, proactive, and explain things like you're talking to a neighbor.
""")

        return "\n".join(parts)

    # -------------------------------------------------------------------------
    # LLM Call
    # -------------------------------------------------------------------------

    def _build_messages(self, system_prompt: str, user_message: str) -> List[Dict[str, str]]:
        """Build message list with history"""
        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history
        memory = self._get_session_memory()
        for msg in memory[-self.llm_context_turns:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": user_message})
        return messages

    async def _call_llm_with_tools(self, messages: List[Dict[str, str]], tool_schemas: List[Dict]) -> str:
        """
        Call LLM with tool/function calling support.

        For models that support function calling, they can request tool invocations.
        For models that don't, we provide tool schemas in the system prompt.
        """
        # Add tool awareness to system prompt
        if tool_schemas:
            tool_desc = self._format_tools_for_prompt(tool_schemas)
            messages[0]["content"] += f"\n\n{tool_desc}"

        resp_text, _ = await self.llm.chat_async(
            messages=messages,
            temperature=self.chat_temperature,
            max_tokens=self.chat_max_tokens
        )

        return resp_text

    async def _call_llm_simple(self, messages: List[Dict[str, str]]) -> str:
        """Simple LLM call without tools"""
        resp_text, _ = await self.llm.chat_async(
            messages=messages,
            temperature=self.chat_temperature,
            max_tokens=self.chat_max_tokens
        )
        return resp_text

    def _format_tools_for_prompt(self, tool_schemas: List[Dict]) -> str:
        """Format tool schemas for inclusion in system prompt"""
        if not tool_schemas:
            return ""

        tools_text = "# Available Tools\n\nYou can invoke the following tools:\n\n"

        for schema in tool_schemas:
            func = schema["function"]
            tools_text += f"**{func['name']}**: {func['description']}\n"

            if func['parameters']['properties']:
                tools_text += "Parameters:\n"
                for param_name, param_info in func['parameters']['properties'].items():
                    required = "(required)" if param_name in func['parameters'].get('required', []) else "(optional)"
                    tools_text += f"  - {param_name} {required}: {param_info['description']}\n"

            tools_text += "\n"

        tools_text += """
To use a tool, include a JSON block in your response:
```json
{"tool": "tool_name", "args": {"param1": "value1"}}
```

You can call multiple tools by including multiple JSON blocks.
After I execute the tools, I'll provide the results and you can synthesize the final response.
"""

        return tools_text

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
