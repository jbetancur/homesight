"""
Conversational Agent

Wrapper around LLM (OpenAI/Claude) that integrates:
- Event context
- Memory results
- Home state summary
- Learned preferences

Provides natural language interface to HSIL.
"""

import logging
from typing import Optional, Dict, Any, List
import json

from .types import (
    ConversationRequest,
    ConversationResponse,
    ActionCommand,
    EventContext,
    MemoryEntry
)

logger = logging.getLogger(__name__)


class ConversationalAgentService:
    """
    Conversational interface to HSIL using LLM.

    Integrates with existing LLMProvider from ai-sidecar.
    """

    def __init__(
        self,
        llm_provider,
        memory_service,
        learning_service,
        policy_engine
    ):
        self.llm = llm_provider
        self.memory = memory_service
        self.learning = learning_service
        self.policy = policy_engine

        logger.info("ConversationalAgentService initialized")

    async def chat(
        self,
        message: str,
        event_context: Optional[EventContext] = None,
        home_state: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None
    ) -> ConversationResponse:
        """
        Process a conversational request.

        Args:
            message: User's message
            event_context: Optional current event context
            home_state: Optional current home state
            session_id: Optional session ID for multi-turn conversation

        Returns:
            ConversationResponse with reply and optional action
        """
        # Build enriched context for LLM
        enriched_context = await self._build_context(
            message,
            event_context,
            home_state
        )

        # Get system prompt with learned preferences
        system_prompt = await self._build_system_prompt(enriched_context)

        # Call LLM
        try:
            llm_response = await self._call_llm(
                system_prompt=system_prompt,
                user_message=message,
                context=enriched_context,
                session_id=session_id
            )

            # Parse response
            response = await self._parse_llm_response(llm_response, enriched_context)

            # Record interaction for learning
            if self.learning:
                interaction_id = f"{session_id}_{__import__('uuid').uuid4().hex[:8]}"
                await self.learning.record_interaction(
                    interaction_id=interaction_id,
                    user_query=message,
                    system_response=response.reply,
                    action_taken=response.action.model_dump(mode='json') if response.action else None,
                    context=enriched_context
                )

            return response

        except Exception as e:
            logger.error(f"Conversational agent error: {e}")
            return ConversationResponse(
                reply=f"I apologize, I encountered an error: {str(e)}",
                action=None
            )

    async def _build_context(
        self,
        message: str,
        event_context: Optional[EventContext],
        home_state: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build enriched context for LLM"""
        context = {
            "user_message": message,
            "timestamp": __import__("datetime").datetime.now().isoformat()
        }

        # Add event context if provided
        if event_context:
            context["event"] = {
                "device_id": event_context.device_id,
                "type": event_context.event_type,
                "value": event_context.event_value,
                "location": event_context.location,
                "trend_1h": event_context.trend_1h,
                "anomaly_score": event_context.anomaly_score
            }

        # Add home state if provided
        if home_state:
            context["home_state"] = home_state

        # Retrieve relevant memories
        # (Simple keyword search for now - could use semantic search with embeddings)
        try:
            if self.memory:
                memories = await self.memory.search_keyword(
                    query=message,
                    limit=3
                )
                context["memories"] = [
                    {"content": m.content, "type": m.type.value}
                    for m in memories
                ]
        except Exception as e:
            logger.warning(f"Failed to retrieve memories: {e}")

        # Add learned preferences
        try:
            if self.learning:
                location = event_context.location if event_context else "home"
                comfort_prefs = await self.learning.get_comfort_preference(location)
                if comfort_prefs:
                    context["learned_preferences"] = comfort_prefs
        except Exception as e:
            logger.warning(f"Failed to retrieve learned preferences: {e}")

        return context

    async def _build_system_prompt(self, context: Dict[str, Any]) -> str:
        """Build system prompt with learned preferences and context"""

        prompt = """You are HomeSight, an intelligent home assistant.

Your capabilities:
- Monitor home sensors (temperature, humidity, water, motion, etc.)
- Control HVAC, water valves, and other devices
- Learn user preferences and adapt over time
- Detect anomalies and safety issues

Current Context:
"""

        # Add home state
        if "home_state" in context:
            prompt += f"\nHome State:\n{json.dumps(context['home_state'], indent=2)}\n"

        # Add event context
        if "event" in context:
            prompt += f"\nCurrent Event:\n{json.dumps(context['event'], indent=2)}\n"

        # Add learned preferences
        if "learned_preferences" in context:
            prefs = context["learned_preferences"]
            prompt += f"""
Learned User Preferences (based on {prefs.get('sample_count', 0)} interactions):
- Preferred temperature: {prefs.get('temp_min', 68):.1f}°F - {prefs.get('temp_max', 75):.1f}°F
- Preferred humidity: {prefs.get('humidity_min', 35):.0f}% - {prefs.get('humidity_max', 55):.0f}%
"""

        # Add relevant memories
        if "memories" in context and context["memories"]:
            prompt += "\nRelevant Past Interactions:\n"
            for mem in context["memories"]:
                prompt += f"- [{mem['type']}] {mem['content']}\n"

        prompt += """
IMPORTANT Response Format:
You must respond ONLY with valid JSON in this exact format. Do not include any text before or after the JSON.

{
  "reply": "Your natural, conversational response to the user here",
  "action": {
    "topic": "homesight/device/command",
    "command": "command_name",
    "value": <value>
  }
}

If no action is needed, use: {"reply": "your response", "action": null}

Example:
User: "I'm cold"
Response: {"reply": "I'll increase the temperature to make it more comfortable for you.", "action": {"topic": "homesight/hvac/command", "command": "set_temperature", "value": 72}}
```

If no action is needed, omit the action field.
"""

        return prompt

    async def _call_llm(
        self,
        system_prompt: str,
        user_message: str,
        context: Dict[str, Any],
        session_id: Optional[str]
    ) -> str:
        """Call LLM provider"""

        # Use existing LLM provider from ai-sidecar
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        # Call LLM provider's chat_async method
        # Returns tuple of (response_text, tool_calls)
        response_text, _ = await self.llm.chat_async(
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )

        return response_text

    async def _parse_llm_response(
        self,
        llm_response: str,
        context: Dict[str, Any]
    ) -> ConversationResponse:
        """Parse LLM response into ConversationResponse"""

        # Try to extract JSON if present
        action = None
        reply = llm_response

        try:
            # Look for JSON code block
            if "```json" in llm_response:
                json_start = llm_response.find("```json") + 7
                json_end = llm_response.find("```", json_start)
                json_str = llm_response[json_start:json_end].strip()

                parsed = json.loads(json_str)
                reply = parsed.get("reply", llm_response)

                if "action" in parsed and parsed["action"]:
                    action_data = parsed["action"]
                    action = ActionCommand(
                        topic=action_data["topic"],
                        command=action_data["command"],
                        value=action_data["value"]
                    )

            # Also try parsing entire response as JSON
            elif llm_response.strip().startswith("{"):
                parsed = json.loads(llm_response)
                reply = parsed.get("reply", llm_response)

                if "action" in parsed and parsed["action"]:
                    action_data = parsed["action"]
                    action = ActionCommand(
                        topic=action_data["topic"],
                        command=action_data["command"],
                        value=action_data["value"]
                    )

        except json.JSONDecodeError:
            # LLM didn't return JSON, use raw response as reply
            pass

        # If no action found but user intent suggests one, use policy engine
        if not action and self.policy:
            try:
                user_message = context.get("user_message", "")
                policy_decision = await self.policy.evaluate_user_intent(
                    intent=user_message,
                    context=context.get("home_state", {})
                )

                if policy_decision.action:
                    action = policy_decision.action
                    # Augment reply with policy reasoning
                    if policy_decision.reasoning:
                        reply += f"\n\n({policy_decision.reasoning})"

            except Exception as e:
                logger.warning(f"Policy engine evaluation failed: {e}")

        return ConversationResponse(
            reply=reply,
            action=action
        )

    async def provide_feedback(
        self,
        interaction_id: str,
        feedback_type: str,
        rating: Optional[int] = None,
        correction: Optional[str] = None
    ):
        """
        Record user feedback on a response.

        This is how the system learns from user feedback.
        """
        if not self.learning:
            logger.warning("Learning service not available for feedback")
            return

        from .learning import UserFeedback, FeedbackType

        feedback = UserFeedback(
            interaction_id=interaction_id,
            feedback_type=FeedbackType(feedback_type),
            rating=rating,
            correction=correction
        )

        await self.learning.record_feedback(feedback)

        logger.info(f"Recorded user feedback: {feedback_type} for {interaction_id}")
