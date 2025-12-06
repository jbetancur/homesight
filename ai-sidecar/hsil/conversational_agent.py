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
            db_path=None,
            ontology=self.ontology
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
        
        Following LLM-as-Orchestrator pattern: LLM decides what tools to use,
        tools execute deterministically, LLM synthesizes results.
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

        Pure LLM-as-Orchestrator pattern:
        - LLM analyzes the user's intent
        - LLM decides which tools (if any) to invoke
        - Tools execute deterministically
        - LLM synthesizes results into natural language
        
        No hardcoded rules - the LLM is fully in control.
        """
        logger.info(f"🔧 Orchestrating with {len(self.tools.tools)} tools available")

        # Build system prompt with tool awareness
        system_prompt = self._build_orchestrator_prompt(context)

        # Get tool schemas for function calling
        tool_schemas = self.tools.get_tool_schemas()

        # First LLM call: planning (with tool selection)
        messages = self._build_messages(system_prompt, message)

        try:
            # LLM decides tools
            llm_response = await self._call_llm_with_tools(messages, tool_schemas)
            
            logger.info(f"📝 LLM response length: {len(llm_response)} chars")
            logger.info(f"📝 LLM response preview: {llm_response[:200]}")

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
                    "content": f"Tool results:\n\n{json.dumps(tool_results, indent=2)}\n\nNow provide a helpful, conversational response to the user based on these results."
                })

                # Second LLM call: synthesis with tool results
                final_response = await self._call_llm_simple(messages)
                logger.info(f"✅ LLM synthesized response: {len(final_response)} chars")
                return final_response

            # No tools needed - direct response
            logger.info("💬 LLM responded directly (no tools needed)")
            return llm_response

        except Exception as e:
            logger.error(f"Orchestration error: {e}", exc_info=True)
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
        - JSON code blocks: ```json {"tool": "...", "args": {...}} ```
        - Bare JSON: {"tool": "...", "args": {...}}
        """
        tool_calls = []

        # Try to find JSON tool call blocks in response (fenced code blocks)
        json_blocks = re.findall(r'```(?:json)?\s*(\{.*?\})\s*```', llm_response, re.DOTALL)

        # For bare JSON, try to parse the entire response if it looks like JSON
        if llm_response.strip().startswith('{') and llm_response.strip().endswith('}'):
            try:
                parsed = json.loads(llm_response.strip())
                if "tool" in parsed:
                    tool_calls.append({
                        "name": parsed["tool"],
                        "arguments": parsed.get("args", parsed.get("arguments", {}))
                    })
                    return tool_calls
            except json.JSONDecodeError:
                pass

        # Also try to find JSON objects with "tool" key using simple search
        # Look for {"tool": anywhere in the response
        if '"tool"' in llm_response or "'tool'" in llm_response:
            # Try to extract JSON starting from { to matching }
            stack = []
            start_idx = None
            for i, char in enumerate(llm_response):
                if char == '{':
                    if not stack:
                        start_idx = i
                    stack.append(char)
                elif char == '}' and stack:
                    stack.pop()
                    if not stack and start_idx is not None:
                        # Found complete JSON object
                        potential_json = llm_response[start_idx:i+1]
                        try:
                            parsed = json.loads(potential_json)
                            if "tool" in parsed:
                                tool_calls.append({
                                    "name": parsed["tool"],
                                    "arguments": parsed.get("args", parsed.get("arguments", {}))
                                })
                        except json.JSONDecodeError:
                            pass
                        start_idx = None

        # Process any fenced code blocks found
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
            "IMPORTANT: When users ask for documentation, manuals, or how-to info - you MUST use the get_device_documentation tool. Do NOT make up documentation!",
            "",
            "## Core Context",
        ]

        # Device list with IDs for tool calls
        if "devices" in context:
            parts.append(f"### Devices ({len(context['devices'])} sensors)")
            parts.append("Device ID mapping (use these IDs when calling tools):")
            for dev in context.get("devices", []):
                dev_id = dev.get("id", "")
                dev_name = dev.get("name", dev_id)
                dev_type = dev.get("type", "sensor")
                zone = dev.get("zone", "")
                parts.append(f"  - {dev_id}: {dev_name} ({dev_type}) in {zone}")
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
## Tool Usage Rules - CRITICAL

**YOU MUST CALL TOOLS TO ANSWER QUESTIONS.**

Do NOT respond with phrases like:
- "Let me check that for you"
- "I'll need to query the data"
- "Let me fetch that information"

Instead, IMMEDIATELY call the appropriate tool using this EXACT format:
```json
{"tool": "tool_name", "args": {"param": "value"}}
```

### When to Use Each Tool:

**User asks: "Which sensors?" / "What devices in basement?" / "List devices" / "Show me sensors"**
→ Call: `list_devices` to get ALL devices in a zone or entire home
→ Example:
```json
{"tool": "list_devices", "args": {"zone": "basement"}}
```

**User asks: "How's the basement?" / "Everything OK in basement?" / "Any issues?"**
→ Call: `check_erratic_behavior` for all basement devices + `get_recent_incidents` for basement
→ Example:
```json
{"tool": "check_erratic_behavior", "args": {"device_id": "zwave-31"}}
```

**User asks: "What's the battery level?" / "Battery status?" / "Check battery"**
→ Call: `get_device_status` to see CURRENT battery level
→ Example:
```json
{"tool": "get_device_status", "args": {"device_id": "zwave-31"}}
```

**User asks: "Comfort levels?" / "How's the temperature?"**
→ Call: `get_comfort_preferences` for learned temperature/humidity preferences
→ Example:
```json
{"tool": "get_comfort_preferences", "args": {}}
```

**User asks: "When did X happen?" / "Last time there was a leak?"**
→ Call: `get_recent_incidents` or `get_device_incidents`
→ Example:
```json
{"tool": "get_recent_incidents", "args": {"limit": 10}}
```

**User asks: "Is my sensor broken?" / "Acting weird?"**
→ Call: `check_erratic_behavior` to see if behavior is unusual
→ Example:
```json
{"tool": "check_erratic_behavior", "args": {"device_id": "zwave-31"}}
```

**User asks: "Show me docs" / "How do I use X?" / "Manual for sensor"**
→ Call: `get_device_documentation`
→ Example:
```json
{"tool": "get_device_documentation", "args": {"device_id": "zwave-31"}}
```

### Response Flow:
1. User asks question
2. YOU call appropriate tool(s) - NO explanatory text, just the JSON
3. I execute the tool and give you results
4. YOU synthesize results into a natural, helpful response

DO NOT say you're "going to check" - JUST CHECK by calling the tool!
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
## CRITICAL: Tool Calling Format

When you need to answer a question with data, you MUST call a tool.

**Correct Format - Output ONLY the JSON:**
{"tool": "tool_name", "args": {"param": "value"}}

**WRONG - Do NOT output explanatory text:**
❌ "Let me check that for you."
❌ "I'll need to query the data."
❌ "To check X, I'll use tool Y."

**RIGHT - Just call the tool:**
✅ {"tool": "get_device_baseline", "args": {"device_id": "zwave-31", "metric": "battery"}}

After I execute the tool, I'll give you the results and THEN you respond conversationally.
"""

        return tools_text

    # -------------------------------------------------------------------------
    # Response Parsing
    # -------------------------------------------------------------------------

    def _parse_response(self, llm_response: str) -> ConversationResponse:
        """Parse LLM response, extracting reply and optional action or clarification."""
        action = None
        clarification = None
        reply = llm_response
        
        # Check if this is a clarification response (structured JSON from system)
        try:
            if llm_response.strip().startswith('{"type"'):
                parsed = json.loads(llm_response.strip())
                if parsed.get("type") == "clarification" and parsed.get("data"):
                    clarification_data = parsed["data"]
                    # Format as user-friendly message
                    reply = clarification_data["question"]
                    return ConversationResponse(
                        reply=reply,
                        action=None,
                        clarification=clarification_data
                    )
        except json.JSONDecodeError as e:
            logger.debug(f"Not a clarification JSON: {e}")
        
        # Strip LLM special tokens (Llama/Qwen format markers that shouldn't appear)
        reply = re.sub(r'<\|[^|>]+\|>', '', reply)  # <|eot_header_id|>, <|start_header_id|>, etc.
        reply = re.sub(r'<\|im_start\|>.*?<\|im_end\|>', '', reply, flags=re.DOTALL)  # ChatML format
        reply = re.sub(r'<\|im_start\|>|<\|im_end\|>', '', reply)  # Leftover ChatML markers
        
        # Strip hallucinated role markers and JSON blocks that look like system messages
        reply = re.sub(r'>?\s*system\s*\n?\{.*?\}', '', reply, flags=re.DOTALL | re.IGNORECASE)
        reply = re.sub(r'>?\s*assistant\s*\n?\{.*?\}', '', reply, flags=re.DOTALL | re.IGNORECASE)
        
        # Strip fake conversation continuations (model hallucinating multi-turn)
        # Stop at first "user" or "assistant" role marker if model outputs them
        if 'user<|' in reply.lower() or '\nuser\n' in reply.lower():
            reply = re.split(r'(?i)user<\||\nuser\n', reply)[0]
        if 'assistant<|' in reply.lower():
            reply = re.split(r'(?i)assistant<\|', reply)[0]
        
        # Strip raw tool call JSON from response (should never be shown to user)
        # Remove: {"tool": "...", "args": {...}} including nested args
        reply = re.sub(r'\{"tool"\s*:\s*"[^"]+"\s*,\s*"args"\s*:\s*\{[^}]*\}\s*\}', '', reply)
        reply = re.sub(r"\{'tool'\s*:\s*'[^']+'\s*,\s*'args'\s*:\s*\{[^}]*\}\s*\}", '', reply)
        # Remove: ```json ... ``` blocks containing tool calls
        reply = re.sub(r'```(?:json)?\s*\{[^}]*"tool"[^}]*\}\s*```', '', reply, flags=re.DOTALL)
        # Remove standalone ``` markers left over
        reply = re.sub(r'```(?:json)?', '', reply)
        reply = re.sub(r'```', '', reply)
        
        # Clean up extra whitespace
        reply = re.sub(r'\n\s*\n\s*\n+', '\n\n', reply).strip()
        
        # If response is now empty or just filler, provide fallback
        if not reply or reply in ["I'll run these checks and let you know what I find.", 
                                   "Let me check that for you.",
                                   "I'll look into that."]:
            reply = ""  # Will be filled by tool execution results
        
        try:
            # Find structured JSON response (for actions)
            match = re.search(r"\{(?:[^{}]|(?:\{[^}]*\}))*\}", llm_response, re.DOTALL)
            if match:
                raw = match.group(0)
                # Skip if it's a tool call or clarification
                if '"tool"' in raw or '"type"' in raw:
                    pass
                else:
                    # Clean trailing commas
                    cleaned = re.sub(r",\s*}", "}", raw)
                    cleaned = re.sub(r",\s*]", "]", cleaned)
                    
                    parsed = json.loads(cleaned)
                    if "reply" in parsed:
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
        
        return ConversationResponse(reply=reply, action=action, clarification=clarification)

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
