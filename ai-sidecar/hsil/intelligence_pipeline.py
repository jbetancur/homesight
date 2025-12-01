"""
Intelligence Pipeline - Unified ML + LLM + Reasoning Coordinator

Orchestrates the complete intelligence flow:
1. Sensor ingestion
2. Sensor fusion
3. ML anomaly/prediction
4. Scenario detection
5. Reasoning templates
6. LLM enhancement (optional)
7. Safety validation
8. Action dispatch
9. Learning feedback

Architecture:
- ML triggers LLM reasoning for complex/uncertain scenarios
- LLM can query ML for predictions
- Safety guardian validates all actions
- All results logged for learning
"""

import logging
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
import time

from .hil_types import (
    PipelineResult, PipelineStage, FusedContext, SensorSignal,
    SignalType, ActionProposal, ActionResult, SafetyDecision,
    ReasoningResult, ScenarioMatch, Severity, ActionMode
)
from .sensor_fusion import SensorFusionEngine
from .safety_guardian import SafetyGuardian
from .reasoning_templates import ScenarioDetector, ReasoningEngine
from .types import EventContext, ActionCommand

# Integration with existing services (avoid duplication)
from .intent_parser import IntentParser
from .temperature_intent import TemperatureIntent

logger = logging.getLogger(__name__)


class IntelligencePipeline:
    """
    Unified intelligence pipeline coordinating all HIL components.

    Flow:
    1. INGESTION: Receive sensor event
    2. FUSION: Combine with context (weather, time, behavior, history)
    3. DETECTION: Detect scenarios using signatures
    4. ML ANALYSIS: Run anomaly detection and predictions
    5. REASONING: Apply chain-of-thought templates
    6. LLM ENHANCEMENT: Optionally enhance with LLM for complex cases
    7. SAFETY: Validate actions through SafetyGuardian
    8. ACTION: Dispatch approved actions
    9. LEARNING: Record outcomes for model improvement
    """

    def __init__(
        self,
        fusion_engine: Optional[SensorFusionEngine] = None,
        safety_guardian: Optional[SafetyGuardian] = None,
        reasoning_engine: Optional[ReasoningEngine] = None,
        scenario_detector: Optional[ScenarioDetector] = None,
        ml_engine=None,  # HSILRiverLearningEngine
        llm_provider=None,
        action_dispatcher=None,
        feedback_learning=None,  # FeedbackLearningService - reuse existing
        backend_url: str = "http://localhost:8080"
    ):
        self.fusion = fusion_engine or SensorFusionEngine(backend_url=backend_url)
        self.safety = safety_guardian or SafetyGuardian()
        self.reasoning = reasoning_engine or ReasoningEngine()
        self.detector = scenario_detector or ScenarioDetector()
        self.ml_engine = ml_engine
        self.llm = llm_provider
        self.dispatcher = action_dispatcher
        self.backend_url = backend_url
        
        # Integrate existing services (avoid duplication)
        self.feedback_learning = feedback_learning  # Reuse FeedbackLearningService
        self.intent_parser = IntentParser()  # Reuse existing intent parser
        self.temp_intent = TemperatureIntent()  # Reuse existing temp intent

        # Configuration
        self.llm_threshold = 0.6  # Use LLM if confidence below this
        self.auto_action_threshold = 0.85  # Auto-act if confidence above this
        self.max_actions_per_event = 3

        # Metrics
        self.events_processed = 0
        self.scenarios_detected = 0
        self.actions_taken = 0
        self.llm_invocations = 0

        logger.info("IntelligencePipeline initialized")

    async def process_event(
        self,
        event_context: EventContext,
        enable_llm: bool = True,
        enable_actions: bool = True
    ) -> PipelineResult:
        """
        Process a sensor event through the complete pipeline.

        Args:
            event_context: Normalized event from EventIngestionService
            enable_llm: Whether to use LLM for complex reasoning
            enable_actions: Whether to dispatch actions

        Returns:
            PipelineResult with all processing results
        """
        start_time = time.time()
        stage_times: Dict[str, int] = {}
        errors: List[str] = []
        stages_completed: List[PipelineStage] = []

        result = PipelineResult(
            trigger_type="sensor_event",
            trigger_data={
                "device_id": event_context.device_id,
                "event_type": event_context.event_type,
                "value": event_context.event_value,
                "location": event_context.location
            }
        )

        try:
            # Stage 1: INGESTION (already done - event_context provided)
            stages_completed.append(PipelineStage.INGESTION)
            stage_times["ingestion"] = 0

            # Stage 2: FUSION
            stage_start = time.time()
            trigger_signal = self._context_to_signal(event_context)
            self.fusion.add_signal(trigger_signal)

            fused_context = await self.fusion.fuse(
                trigger_signal=trigger_signal,
                include_weather=True,
                include_behavioral=True
            )
            result.fused_context = fused_context
            stages_completed.append(PipelineStage.FUSION)
            stage_times["fusion"] = int((time.time() - stage_start) * 1000)

            # Stage 3: ML ANALYSIS (anomaly detection, predictions)
            stage_start = time.time()
            ml_results = await self._run_ml_analysis(event_context, fused_context)
            stages_completed.append(PipelineStage.DETECTION)
            stage_times["ml_analysis"] = int((time.time() - stage_start) * 1000)

            # Stage 4: SCENARIO DETECTION
            stage_start = time.time()
            matched_scenarios = self.detector.detect(fused_context)
            result.matched_scenarios = matched_scenarios
            self.scenarios_detected += len(matched_scenarios)
            stage_times["scenario_detection"] = int((time.time() - stage_start) * 1000)

            # Stage 5: REASONING
            stage_start = time.time()
            reasoning_result = await self._apply_reasoning(
                fused_context, matched_scenarios, ml_results, enable_llm
            )
            result.reasoning_result = reasoning_result
            stages_completed.append(PipelineStage.REASONING)
            stage_times["reasoning"] = int((time.time() - stage_start) * 1000)

            # Stage 6: SAFETY & ACTION
            if enable_actions and reasoning_result.recommended_actions:
                stage_start = time.time()
                safety_decisions, actions_taken = await self._process_actions(
                    reasoning_result.recommended_actions,
                    fused_context,
                    reasoning_result.primary_confidence
                )
                result.safety_decisions = safety_decisions
                result.actions_taken = actions_taken
                stages_completed.append(PipelineStage.SAFETY)
                stages_completed.append(PipelineStage.ACTION)
                stage_times["safety_action"] = int((time.time() - stage_start) * 1000)

            # Stage 7: LEARNING (record for model improvement)
            stage_start = time.time()
            await self._record_for_learning(event_context, result)
            stages_completed.append(PipelineStage.LEARNING)
            stage_times["learning"] = int((time.time() - stage_start) * 1000)

            # Build summary
            result.stages_completed = stages_completed
            result.stage_times = stage_times
            result.summary = self._build_summary(result)
            result.insights_count = len(reasoning_result.insights) if reasoning_result else 0
            result.actions_count = len(result.actions_taken)

        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            errors.append(str(e))
            result.errors = errors

        result.total_processing_time_ms = int((time.time() - start_time) * 1000)
        self.events_processed += 1

        return result

    async def process_user_message(
        self,
        message: str,
        session_id: Optional[str] = None,
        home_state: Optional[Dict[str, Any]] = None
    ) -> PipelineResult:
        """
        Process a user message through the pipeline.
        
        NOTE: For full conversational handling, use ConversationalAgentService.chat()
        which has better implementation (temperature preference model, device ontology,
        home health engine, etc.).
        
        This method is for lightweight intent detection + action execution only.
        It delegates parsing to existing IntentParser/TemperatureIntent.
        """
        start_time = time.time()

        result = PipelineResult(
            trigger_type="user_message",
            trigger_data={"message": message, "session_id": session_id}
        )

        try:
            # Get fused context for action processing
            fused_context = await self.fusion.fuse(include_weather=True)
            result.fused_context = fused_context

            # Parse user intent using existing implementations
            intent_result = await self._parse_user_intent(message, fused_context)
            
            # Handle high-confidence structured intents directly
            if intent_result.get("confidence", 0) > 0.85:
                intent_type = intent_result.get("intent")
                
                # Temperature adjustment - create action
                if intent_type == "temperature_adjustment":
                    delta = intent_result.get("delta")
                    target = intent_result.get("target")
                    
                    if target:
                        action = {"action": "set_temperature", "value": target, "device_id": "thermostat"}
                    elif delta:
                        # Would need current temp - delegate to ConversationalAgentService
                        result.summary = f"Temperature adjustment: {delta:+d}°F"
                        return result
                    
                    if action:
                        safety_decisions, actions_taken = await self._process_actions(
                            [action], fused_context, intent_result["confidence"]
                        )
                        result.safety_decisions = safety_decisions
                        result.actions_taken = actions_taken
                
                # Valve control
                elif intent_type in ["close_main_valve", "open_main_valve"]:
                    action = {
                        "action": intent_type,
                        "device_id": "main_valve",
                        "value": intent_type == "close_main_valve"
                    }
                    safety_decisions, actions_taken = await self._process_actions(
                        [action], fused_context, intent_result["confidence"]
                    )
                    result.safety_decisions = safety_decisions
                    result.actions_taken = actions_taken
                
                result.summary = f"Intent: {intent_type}"
            else:
                # Low confidence - needs LLM via ConversationalAgentService
                result.summary = "Requires conversational handling"

        except Exception as e:
            logger.error(f"User message pipeline error: {e}", exc_info=True)
            result.errors.append(str(e))

        except Exception as e:
            logger.error(f"User message pipeline error: {e}", exc_info=True)
            result.errors.append(str(e))

        result.total_processing_time_ms = int((time.time() - start_time) * 1000)
        return result

    def _context_to_signal(self, event_context: EventContext) -> SensorSignal:
        """Convert EventContext to SensorSignal"""
        return SensorSignal(
            device_id=event_context.device_id,
            sensor_id=event_context.sensor_id,
            signal_type=SignalType.SENSOR_READING,
            value=event_context.event_value,
            timestamp=event_context.timestamp,
            confidence=1.0 - (event_context.anomaly_score or 0),
            metadata={
                "event_type": event_context.event_type,
                "location": event_context.location,
                "device_type": event_context.device_type,
                "trend_1h": event_context.trend_1h,
                "trend_24h": event_context.trend_24h,
                "anomaly_score": event_context.anomaly_score
            }
        )

    async def _run_ml_analysis(
        self,
        event_context: EventContext,
        fused_context: FusedContext
    ) -> Dict[str, Any]:
        """Run ML analysis on the event"""
        results = {
            "anomaly_detected": False,
            "anomaly_score": 0.0,
            "predictions": {}
        }

        if not self.ml_engine:
            return results

        try:
            # Check for anomaly
            if isinstance(event_context.event_value, (int, float)):
                is_anomalous, score = await self.ml_engine.is_anomalous(
                    device_id=event_context.device_id,
                    metric=event_context.event_type,
                    value=float(event_context.event_value)
                )
                results["anomaly_detected"] = is_anomalous
                results["anomaly_score"] = score

                if is_anomalous:
                    logger.info(
                        f"ML anomaly detected: {event_context.device_id}/{event_context.event_type} "
                        f"= {event_context.event_value} (score: {score:.2f})"
                    )

            # Get comfort prediction
            if event_context.event_type in ["temperature", "temp"]:
                pred, conf = await self.ml_engine.predict_preferred_value(
                    location=event_context.location,
                    metric="temperature",
                    current_value=float(event_context.event_value)
                )
                if pred:
                    results["predictions"]["preferred_temp"] = pred
                    results["predictions"]["temp_confidence"] = conf

        except Exception as e:
            logger.warning(f"ML analysis error: {e}")

        return results

    async def _apply_reasoning(
        self,
        fused_context: FusedContext,
        matched_scenarios: List[ScenarioMatch],
        ml_results: Dict[str, Any],
        enable_llm: bool
    ) -> ReasoningResult:
        """Apply reasoning templates and optionally LLM"""

        # Use reasoning engine for template-based reasoning
        reasoning_result = await self.reasoning.reason(fused_context, matched_scenarios)

        # Determine if LLM enhancement is needed
        needs_llm = (
            enable_llm and
            self.llm and
            (
                reasoning_result.primary_confidence < self.llm_threshold or
                len(matched_scenarios) > 2 or  # Multiple scenarios = complex
                ml_results.get("anomaly_detected", False)  # Anomalies need explanation
            )
        )

        if needs_llm:
            enhanced_result = await self._enhance_with_llm(
                reasoning_result, fused_context, ml_results
            )
            self.llm_invocations += 1
            return enhanced_result

        return reasoning_result

    async def _enhance_with_llm(
        self,
        reasoning_result: ReasoningResult,
        fused_context: FusedContext,
        ml_results: Dict[str, Any]
    ) -> ReasoningResult:
        """Enhance reasoning result with LLM analysis"""

        # Build prompt with context and reasoning so far
        prompt = self._build_llm_prompt(reasoning_result, fused_context, ml_results)

        try:
            messages = [
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": prompt}
            ]

            response, _ = await self.llm.chat_async(
                messages=messages,
                temperature=0.3,
                max_tokens=500
            )

            # Parse LLM response and enhance result
            enhanced = self._parse_llm_enhancement(response, reasoning_result)
            return enhanced

        except Exception as e:
            logger.warning(f"LLM enhancement failed: {e}")
            return reasoning_result

    def _build_llm_prompt(
        self,
        reasoning_result: ReasoningResult,
        fused_context: FusedContext,
        ml_results: Dict[str, Any]
    ) -> str:
        """Build prompt for LLM enhancement"""
        lines = [
            "Analyze this home automation scenario and provide insights:",
            "",
            "CONTEXT:",
            self.fusion.format_for_llm(fused_context),
            "",
            "ML ANALYSIS:",
            f"- Anomaly detected: {ml_results.get('anomaly_detected', False)}",
            f"- Anomaly score: {ml_results.get('anomaly_score', 0):.2f}",
        ]

        if ml_results.get("predictions"):
            lines.append(f"- Predictions: {ml_results['predictions']}")

        lines.extend([
            "",
            "INITIAL REASONING:",
            reasoning_result.primary_conclusion,
            "",
            "TASK:",
            "1. Validate or refine the initial reasoning",
            "2. Add any insights missed by template-based reasoning",
            "3. Suggest additional actions if appropriate",
            "4. Provide a natural language summary for the user",
            "",
            "Respond in JSON format:",
            '{"refined_conclusion": "...", "additional_insights": [...], "user_summary": "..."}'
        ])

        return "\n".join(lines)

    def _get_system_prompt(self) -> str:
        """Get system prompt for LLM"""
        return """You are an expert home automation analyst. Your role is to:
1. Analyze sensor data and ML predictions
2. Identify potential issues or optimizations
3. Provide clear, actionable recommendations
4. Explain reasoning in simple terms

Rules:
- Never invent data - only use what's provided
- Be conservative with recommendations
- Prioritize safety (water leaks, smoke, CO)
- Consider user comfort and preferences
- Acknowledge uncertainty when appropriate"""

    def _parse_llm_enhancement(
        self,
        llm_response: str,
        original: ReasoningResult
    ) -> ReasoningResult:
        """Parse LLM response and enhance reasoning result"""
        import json
        import re

        try:
            # Extract JSON from response
            match = re.search(r'\{[^}]+\}', llm_response, re.DOTALL)
            if match:
                data = json.loads(match.group(0))

                if data.get("refined_conclusion"):
                    original.primary_conclusion = data["refined_conclusion"]

                if data.get("user_summary"):
                    original.primary_conclusion = data["user_summary"]

        except Exception as e:
            logger.warning(f"Failed to parse LLM enhancement: {e}")

        return original

    async def _process_actions(
        self,
        recommended_actions: List[Dict[str, Any]],
        fused_context: FusedContext,
        confidence: float
    ) -> Tuple[List[SafetyDecision], List[ActionResult]]:
        """Process recommended actions through safety and dispatch"""
        safety_decisions = []
        actions_taken = []

        for action_data in recommended_actions[:self.max_actions_per_event]:
            # Build action proposal
            proposal = ActionProposal(
                action_type=action_data.get("action", "unknown"),
                target_device_id=action_data.get("device_id", "unknown"),
                command=action_data.get("action", "unknown"),
                value=action_data.get("target", action_data.get("value")),
                source="reasoning",
                confidence=confidence,
                urgency=Severity(action_data.get("severity", "medium")),
                reasoning=action_data.get("scenario_id", "")
            )

            # Evaluate with safety guardian
            decision = await self.safety.evaluate(proposal, fused_context)
            safety_decisions.append(decision)

            # Execute if allowed
            if decision.allowed and decision.action_mode in [ActionMode.ACT, ActionMode.ACT_AND_NOTIFY]:
                action_result = await self._dispatch_action(proposal, decision)
                actions_taken.append(action_result)
                self.actions_taken += 1

                # Record for rate limiting
                for rule_id in decision.triggered_rules:
                    self.safety.record_action_taken(rule_id)

        return safety_decisions, actions_taken

    async def _dispatch_action(
        self,
        proposal: ActionProposal,
        decision: SafetyDecision
    ) -> ActionResult:
        """Dispatch an action"""
        import uuid

        action_id = str(uuid.uuid4())[:8]

        try:
            if self.dispatcher:
                # Build ActionCommand
                command = ActionCommand(
                    topic=f"homesight/{proposal.target_device_id}/command",
                    command=proposal.command,
                    value=proposal.value
                )
                await self.dispatcher.dispatch(command)

                return ActionResult(
                    action_id=action_id,
                    success=True,
                    executed_at=datetime.now(),
                    device_id=proposal.target_device_id,
                    command=proposal.command,
                    value=proposal.value,
                    safety_decision=decision
                )
            else:
                logger.warning("No action dispatcher configured")
                return ActionResult(
                    action_id=action_id,
                    success=False,
                    executed_at=datetime.now(),
                    device_id=proposal.target_device_id,
                    command=proposal.command,
                    value=proposal.value,
                    safety_decision=decision,
                    error_message="No dispatcher configured"
                )

        except Exception as e:
            logger.error(f"Action dispatch failed: {e}")
            return ActionResult(
                action_id=action_id,
                success=False,
                executed_at=datetime.now(),
                device_id=proposal.target_device_id,
                command=proposal.command,
                value=proposal.value,
                safety_decision=decision,
                error_message=str(e)
            )

    async def _record_for_learning(
        self,
        event_context: EventContext,
        result: PipelineResult
    ):
        """Record pipeline results for model improvement"""
        # ML engine learns from events
        if not self.ml_engine:
            return

        # Log scenario matches for pattern analysis
        if result.matched_scenarios:
            logger.debug(
                f"Scenarios matched for {event_context.device_id}: "
                f"{[s.scenario_id for s in result.matched_scenarios]}"
            )
        
        # Record to FeedbackLearningService for later user feedback correlation
        # This integrates with existing feedback system instead of duplicating
        if self.feedback_learning and result.reasoning_result:
            try:
                import uuid
                interaction_id = f"hil_{uuid.uuid4().hex[:8]}"
                
                await self.feedback_learning.record_interaction(
                    interaction_id=interaction_id,
                    user_query=f"sensor_event:{event_context.event_type}",
                    system_response=result.reasoning_result.primary_conclusion,
                    action_taken={
                        "actions": [a.model_dump() for a in result.actions_taken]
                    } if result.actions_taken else None,
                    context={
                        "device_id": event_context.device_id,
                        "scenarios": [s.scenario_id for s in result.matched_scenarios],
                        "confidence": result.reasoning_result.primary_confidence
                    }
                )
            except Exception as e:
                logger.debug(f"Failed to record to feedback learning: {e}")

    async def _parse_user_intent(
        self,
        message: str,
        fused_context: FusedContext
    ) -> Dict[str, Any]:
        """
        Parse user message to determine intent.
        
        DELEGATES to existing IntentParser and TemperatureIntent
        which are more comprehensive implementations.
        
        HIL ScenarioDetector is for SENSOR EVENTS, not user messages.
        """
        # 1. Use existing IntentParser (better regex patterns, room/device extraction)
        intent = self.intent_parser.parse(message)
        if intent and intent.confidence > 0.7:
            logger.debug(f"IntentParser matched: {intent.intent} ({intent.confidence:.2f})")
            return {
                "intent": intent.intent,
                "parsed_intent": intent,
                "confidence": intent.confidence,
                "target_room": intent.target_room,
                "target_device": intent.target_device,
                "target_value": intent.target_value
            }
        
        # 2. Use existing TemperatureIntent (better delta mapping, explicit temps)
        if self.temp_intent.is_temperature_related(message):
            delta = self.temp_intent.parse(message)  # Returns -5 to +5
            target = self.temp_intent.extract_target_temperature(message)
            
            if delta is not None or target is not None:
                logger.debug(f"TemperatureIntent matched: delta={delta}, target={target}")
                return {
                    "intent": "temperature_adjustment",
                    "delta": delta,
                    "target": target,
                    "confidence": 0.9
                }
        
        # 3. Fallback - no structured intent, may need LLM
        return {"intent": "general", "confidence": 0.0}

    async def _generate_llm_response(
        self,
        message: str,
        fused_context: FusedContext,
        reasoning_result: Optional[ReasoningResult]
    ) -> str:
        """Generate LLM response for user message"""
        if not self.llm:
            if reasoning_result:
                return reasoning_result.primary_conclusion
            return "I understand. Let me check on that."

        try:
            context_str = self.fusion.format_for_llm(fused_context)

            prompt = f"""User message: {message}

Current home context:
{context_str}

{f'Analysis: {reasoning_result.primary_conclusion}' if reasoning_result else ''}

Respond helpfully and naturally. If you took an action, confirm it. If you need more information, ask."""

            messages = [
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": prompt}
            ]

            response, _ = await self.llm.chat_async(
                messages=messages,
                temperature=0.7,
                max_tokens=300
            )

            return response

        except Exception as e:
            logger.warning(f"LLM response generation failed: {e}")
            if reasoning_result:
                return reasoning_result.primary_conclusion
            return "I'm having trouble processing that request. Please try again."

    def _build_summary(self, result: PipelineResult) -> str:
        """Build human-readable summary of pipeline result"""
        parts = []

        if result.matched_scenarios:
            scenarios = [s.scenario_name for s in result.matched_scenarios[:3]]
            parts.append(f"Detected: {', '.join(scenarios)}")

        if result.reasoning_result:
            parts.append(result.reasoning_result.primary_conclusion)

        if result.actions_taken:
            actions = [f"{a.command} on {a.device_id}" for a in result.actions_taken]
            parts.append(f"Actions: {', '.join(actions)}")

        return " | ".join(parts) if parts else "No significant events detected"

    async def get_stats(self) -> Dict[str, Any]:
        """Get pipeline statistics"""
        return {
            "events_processed": self.events_processed,
            "scenarios_detected": self.scenarios_detected,
            "actions_taken": self.actions_taken,
            "llm_invocations": self.llm_invocations,
            "safety_stats": await self.safety.get_stats() if self.safety else {}
        }
