"""Chat service with multi-turn conversation and function calling"""

import logging
import json
import httpx
import time
from typing import Dict, Any, Optional, List, Tuple
from models.chat import ChatRequest, ChatResponse
from services.session_service import SessionService
from llm.provider import LLMProvider
from llm.tools import ToolRegistry, get_default_tools
from rag.engine import RAGEngine
from metrics.metrics import rag_retrieval_duration, rag_retrievals, chat_actions, llm_inferences, llm_inference_duration

logger = logging.getLogger(__name__)


class ChatService:
    """
    Conversational AI service with:
    - Multi-turn conversation support (cloud or local mode)
    - Function/tool calling (cloud mode only)
    - RAG-enhanced responses with source attribution
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        session_service: SessionService,
        rag_engine: Optional[RAGEngine] = None,
        tool_registry: Optional[ToolRegistry] = None,
        backend_url: str = "http://localhost:8080"
    ):
        self.llm = llm_provider
        self.sessions = session_service
        self.rag = rag_engine
        self.tools = tool_registry or get_default_tools()
        self.backend_url = backend_url

        # Register tool implementations
        self._register_tool_implementations()

    def _register_tool_implementations(self):
        """Register actual implementations for tools"""

        # Get device history
        async def get_device_history(device_id: str, hours: int = 24):
            """Get device history from API"""
            # TODO: Call Go backend API to get device history
            logger.info(f"Getting history for device {device_id} (last {hours}h)")
            return {
                "device_id": device_id,
                "status": "operational",
                "recent_events": ["No recent incidents"],
                "message": f"Device {device_id} is functioning normally with no issues in the last {hours} hours."
            }

        # Reset device
        async def reset_device(device_id: str):
            """Reset a device"""
            # TODO: Call Go backend API to reset device
            logger.info(f"Resetting device {device_id}")
            return {
                "device_id": device_id,
                "status": "reset_initiated",
                "message": f"Reset command sent to device {device_id}. The device will reinitialize shortly."
            }

        # Schedule technician
        async def schedule_technician(device_id: str, issue_description: str, priority: str):
            """Schedule a technician visit"""
            # TODO: Integrate with scheduling system
            logger.info(f"Scheduling technician for {device_id}: {issue_description} ({priority} priority)")
            return {
                "device_id": device_id,
                "ticket_id": f"TECH-{device_id[:8].upper()}",
                "priority": priority,
                "status": "scheduled",
                "message": f"Technician visit scheduled with {priority} priority. Ticket ID: TECH-{device_id[:8].upper()}"
            }

        # Update device settings
        async def update_device_settings(device_id: str, settings: Dict[str, Any]):
            """Update device configuration"""
            # TODO: Call Go backend API to update settings
            logger.info(f"Updating settings for {device_id}: {settings}")
            return {
                "device_id": device_id,
                "settings_updated": settings,
                "status": "success",
                "message": f"Settings updated for device {device_id}"
            }

        # Search knowledge base
        async def search_knowledge_base(query: str, device_type: Optional[str] = None):
            """Search RAG for relevant documentation"""
            if not self.rag:
                return {"message": "Knowledge base not available"}

            logger.info(f"Searching knowledge base: {query}")
            results = self.rag.query(query, n_results=3)

            docs = []
            for r in results:
                if r.get('relevance_score', 0) > 0.3:
                    docs.append({
                        "source": r['metadata'].get('source', 'Unknown'),
                        "relevance": round(r['relevance_score'], 3),
                        "excerpt": r['text'][:200]
                    })

            return {
                "query": query,
                "results_found": len(docs),
                "documents": docs
            }

        # Get current incidents
        async def get_current_incidents(location: Optional[str] = None, severity: Optional[str] = None):
            """Get current active incidents from the Go backend"""
            try:
                logger.info(f"Fetching current incidents (location={location}, severity={severity})")

                # Build query parameters
                params = {"status": "active"}

                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(
                        f"{self.backend_url}/api/incidents",
                        params=params
                    )
                    response.raise_for_status()

                    incidents = response.json()

                    # Filter by location if specified
                    if location:
                        incidents = [
                            inc for inc in incidents
                            if location.lower() in inc.get('location', '').lower() or
                               location.lower() in inc.get('device_name', '').lower() or
                               location.lower() in inc.get('type', '').lower()
                        ]

                    # Filter by severity if specified
                    if severity:
                        incidents = [
                            inc for inc in incidents
                            if inc.get('severity', '').lower() == severity.lower()
                        ]

                    if not incidents:
                        return {
                            "count": 0,
                            "incidents": [],
                            "message": f"No active incidents found" + (f" in {location}" if location else "")
                        }

                    return {
                        "count": len(incidents),
                        "incidents": incidents,
                        "message": f"Found {len(incidents)} active incident(s)" + (f" in {location}" if location else "")
                    }

            except httpx.RequestError as e:
                logger.error(f"Failed to fetch incidents from backend: {e}")
                return {
                    "error": f"Failed to connect to backend: {str(e)}",
                    "count": 0,
                    "incidents": []
                }
            except Exception as e:
                logger.error(f"Error getting current incidents: {e}")
                return {
                    "error": str(e),
                    "count": 0,
                    "incidents": []
                }

        # Attach implementations to tools
        tool = self.tools.get("get_device_history")
        if tool:
            tool.function = get_device_history

        tool = self.tools.get("reset_device")
        if tool:
            tool.function = reset_device

        tool = self.tools.get("schedule_technician")
        if tool:
            tool.function = schedule_technician

        tool = self.tools.get("update_device_settings")
        if tool:
            tool.function = update_device_settings

        tool = self.tools.get("search_knowledge_base")
        if tool:
            tool.function = search_knowledge_base

        tool = self.tools.get("get_current_incidents")
        if tool:
            tool.function = get_current_incidents

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """
        Handle a chat request with multi-turn conversation and function calling

        Args:
            request: ChatRequest with message, optional session_id, and context

        Returns:
            ChatResponse with AI response and session info
        """
        # Get or create session
        session = self.sessions.get_or_create_session(
            session_id=request.session_id,
            context=request.context
        )

        # Add user message to session
        self.sessions.add_message(
            session_id=session.session_id,
            role="user",
            content=request.message
        )

        # Build conversation history for LLM
        messages = self._build_messages(session)

        # Enhance with RAG if available (pass session for device context)
        rag_context = await self._get_rag_context(request.message, session)
        if rag_context:
            # Add RAG context to system message
            if messages and messages[0]["role"] == "system":
                messages[0]["content"] += f"\n\n{rag_context}"
            else:
                messages.insert(0, {
                    "role": "system",
                    "content": f"You are a helpful home maintenance assistant.\n\n{rag_context}"
                })

        # Get tools in OpenAI format
        tools = self.tools.get_openai_tools() if self.llm.openai_client else None

        # Determine if this chat is about a specific incident -> force local LLM for privacy/safety
        session_incident_context = session.context.get('incident') if session and session.context else None

        # Generate response with potential function calling
        # Use override_mode parameter instead of mutating shared state (RACE-CONDITION-FREE)
        if session_incident_context:
            logger.info("Forcing local LLM for incident chat (incident context present)")
            response_text, tool_calls = self.llm.chat(
                messages=messages,
                tools=tools,
                temperature=0.7,
                max_tokens=1000,
                override_mode='local'  # Force local for this request only
            )
        else:
            response_text, tool_calls = self.llm.chat(
                messages=messages,
                tools=tools,
                temperature=0.7,
                max_tokens=1000
                # No override - use configured default mode
            )

        # Execute any tool calls
        actions_taken = []
        if tool_calls:
            tool_results = await self._execute_tools(tool_calls)
            actions_taken = tool_results

            # If tools were executed, generate a follow-up response incorporating the results
            if tool_results:
                # Add tool results to messages
                tool_result_msg = self._format_tool_results(tool_results)
                messages.append({"role": "user", "content": tool_result_msg})

                # Generate final response
                final_response, _ = self.llm.chat(
                    messages=messages,
                    tools=None,
                    temperature=0.7,
                    max_tokens=800
                )
                response_text = final_response

        # Add assistant response to session
        self.sessions.add_message(
            session_id=session.session_id,
            role="assistant",
            content=response_text,
            metadata={"actions_taken": actions_taken} if actions_taken else None
        )

        return ChatResponse(
            response=response_text,
            session_id=session.session_id,
            actions_taken=actions_taken if actions_taken else None
        )

    def _build_messages(self, session) -> List[Dict[str, str]]:
        """Build message history for LLM"""

        # Build system prompt with incident context if available
        system_content = (
            "You are a helpful home maintenance assistant for HomeSight, a home monitoring system. "
            "You can help users understand device issues, analyze incidents, and take actions like "
            "resetting devices or scheduling technicians.\n\n"
        )

        # CRITICAL: Add incident context if this chat is about a specific incident
        incident_context = session.context.get("incident") if session.context else None
        if incident_context:
            system_content += (
                f"🚨 INCIDENT CONTEXT:\n"
                f"The user is asking about this SPECIFIC incident:\n"
                f"- Title: {incident_context.get('title', 'Unknown')}\n"
                f"- Description: {incident_context.get('description', 'N/A')}\n"
                f"- Severity: {incident_context.get('severity', 'Unknown')}\n"
                f"- ID: {incident_context.get('id', 'Unknown')}\n\n"
                f"IMPORTANT: Focus your responses on THIS incident. Do NOT make up or hallucinate other incidents. "
                f"If you don't have information, say so clearly. Use tools like get_current_incidents only if the user "
                f"asks about OTHER incidents or the general home status.\n\n"
            )
        else:
            system_content += (
                "IMPORTANT: When users ask about the status of their home, specific rooms (like 'basement', "
                "'kitchen'), or general questions like 'how is everything', you MUST use the get_current_incidents "
                "tool to check for active alerts before responding. Do not assume there are no issues - always check.\n\n"
            )

        system_content += (
            "Available tools:\n"
            "- get_current_incidents: Check for active incidents/alerts\n"
            "- get_device_history: View device metrics and history\n"
            "- reset_device: Reset a malfunctioning device\n"
            "- schedule_technician: Schedule service calls\n"
            "- update_device_settings: Change device configuration\n"
            "- search_knowledge_base: Find documentation and guides\n\n"
            "🚫 CRITICAL: NEVER make up, invent, or hallucinate incidents that don't exist. "
            "If a tool returns empty results, acknowledge that truthfully. "
            "If you don't have information, say 'I don't have that information' - don't fabricate details.\n\n"
            "Be proactive, concise, helpful, and actionable."
        )

        messages = [{"role": "system", "content": system_content}]

        # Add conversation history (last 10 messages for context window management)
        for msg in session.messages[-10:]:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })

        return messages

    async def _get_rag_context(self, query: str, session=None) -> Optional[str]:
        """Get relevant context from RAG, enhanced with device and conversation context"""
        if not self.rag:
            return None

        rag_start = time.time()
        try:
            # Build enhanced query from multiple sources:
            # 1. Current user query
            # 2. Device/incident context
            # 3. Recent conversation history (for continuity)

            enhanced_query = query

            if session:
                # Add device/incident context
                if session.context:
                    incident = session.context.get("incident", {})
                    device_id = incident.get("device_id", "")
                    device_name = incident.get("device_name", "")

                    if device_name:
                        enhanced_query = f"{query} {device_name}".strip()
                    elif device_id:
                        enhanced_query = f"{query} device {device_id}".strip()

                # Add context from recent conversation (last 2-3 messages)
                # This helps maintain context across multi-turn conversations
                if session.messages:
                    recent_context = []
                    for msg in session.messages[-4:]:  # Last 4 messages = 2 turns
                        if msg.role == "assistant":
                            # Extract key info from assistant responses
                            content = msg.content
                            # Pull out specific terms like battery types, model numbers, etc.
                            if any(word in content.lower() for word in ["battery", "cr2032", "aa", "aaa", "model", "sensor", "device"]):
                                recent_context.append(content[:200])  # First 200 chars

                    if recent_context:
                        # Add conversation context to query for continuity
                        enhanced_query = f"{enhanced_query} (context: {' '.join(recent_context[:2])})"

            results = self.rag.query(enhanced_query, n_results=5)
            rag_duration = time.time() - rag_start
            rag_retrieval_duration.observe(rag_duration)

            if not results:
                rag_retrievals.labels(status="empty").inc()
                return None

            rag_retrievals.labels(status="success").inc()
            context_parts = ["Relevant device documentation:"]
            for r in results:
                if r.get('relevance_score', 0) > 0.3:
                    source = r['metadata'].get('source', 'Unknown')
                    text = r['text'][:1500]  # Full context for better answers
                    context_parts.append(f"\n[{source}]\n{text}")

            return "\n".join(context_parts) if len(context_parts) > 1 else None

        except Exception as e:
            logger.error(f"RAG query failed: {e}")
            rag_retrievals.labels(status="error").inc()
            return None

    async def _execute_tools(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute tool calls and return results"""
        results = []

        for tc in tool_calls:
            tool_name = tc["name"]
            arguments = tc["arguments"]

            logger.info(f"Executing tool: {tool_name} with args: {arguments}")

            try:
                result = await self.tools.execute(tool_name, arguments)

                chat_actions.labels(action_type=tool_name, status="success").inc()
                results.append({
                    "tool": tool_name,
                    "arguments": arguments,
                    "result": result,
                    "status": "success"
                })

            except Exception as e:
                logger.error(f"Tool execution failed: {e}")
                chat_actions.labels(action_type=tool_name, status="error").inc()
                results.append({
                    "tool": tool_name,
                    "arguments": arguments,
                    "error": str(e),
                    "status": "error"
                })

        return results

    def _format_tool_results(self, results: List[Dict[str, Any]]) -> str:
        """Format tool execution results for LLM"""
        formatted = ["Tool execution results:"]

        for r in results:
            if r["status"] == "success":
                formatted.append(f"\n- {r['tool']}: {json.dumps(r['result'])}")
            else:
                formatted.append(f"\n- {r['tool']}: Error - {r['error']}")

        return "\n".join(formatted)
