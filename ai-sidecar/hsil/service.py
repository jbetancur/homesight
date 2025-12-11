"""
HSIL Service Coordinator (Simplified)

ML data → LLM → response architecture.

Core components:
- Event Ingestion: Receives sensor events
- ML Learning (River): Learns patterns, detects anomalies/erratic behavior
- Device Ontology: Knows what devices exist and their capabilities
- Weather Service: Environmental context
- Memory: Conversation history
- Conversational Agent: LLM reasons from all data
- Action Dispatcher: Executes actions
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from .types import (
    EventContext,
    DeviceState,
    HomeState,
    ConversationResponse
)
from .event_ingestion import EventIngestionService
from .memory import HomeMemoryService
from .action_dispatcher import ActionDispatcherService
from .conversational_agent import ConversationalAgentService
from .feedback_learning import FeedbackLearningService
from .weather_service import WeatherService
from .weather_sync import WeatherSyncService
from .hsil_ml_river import HSILRiverLearningEngine
from .river_feedback_adapter import RiverFeedbackAdapter
from .incident_generator import IncidentGenerator

logger = logging.getLogger(__name__)


class HSILService:
    """
    HomeSight Intelligence Layer - Simplified Service

    Architecture: ML data → LLM → response
    - ML learns patterns and detects anomalies
    - LLM reasons from all available data
    - No hardcoded intent parsing or reasoning templates
    """

    def __init__(
        self,
        chroma_client=None,
        llm_provider=None,
        mqtt_client=None,
        rag_engine=None,
        backend_url: str = "http://localhost:8080",
        db_path: str = "/var/lib/homesight/hsil_memory.db"
    ):
        self.backend_url = backend_url
        self.db_path = db_path
        self.rag_engine = rag_engine
        self.llm_provider = llm_provider

        logger.info("Initializing HSIL services...")

        # Weather & Environmental
        from config import get_config
        config = get_config()
        self.weather_service = WeatherService(
            zip_code=config.weather.zip_code,
            location_name=config.weather.location_name
        )
        self.weather_sync = WeatherSyncService(
            weather_service=self.weather_service,
            refresh_interval_minutes=config.weather.refresh_interval_minutes
        )

        # Event ingestion
        self.event_ingestion = EventIngestionService(db_path=db_path)

        # Memory
        self.memory = HomeMemoryService(
            db_path=db_path,
            chroma_client=chroma_client
        )

        # ML Learning (River) - core pattern detection
        self.learning = HSILRiverLearningEngine(
            db_path=db_path,
            weather_service=self.weather_service,
            erratic_decay_half_life=config.hsil.erratic.decay_half_life_seconds,
            erratic_threshold=config.hsil.erratic.threshold,
            erratic_list_threshold=config.hsil.erratic.list_threshold
        )
        self.river_feedback = RiverFeedbackAdapter(learning_engine=self.learning)
        self.feedback_learning = FeedbackLearningService(db_path=db_path)

        # Action dispatcher
        self.action_dispatcher = ActionDispatcherService(
            mqtt_client=mqtt_client
        )

        # Incident generator (for creating incidents from ML detections)
        self.incident_generator = IncidentGenerator(
            backend_url=backend_url,
            dry_run=False
        )

        # Conversational agent - LLM-as-Orchestrator with tool calling
        self.conversational_agent = ConversationalAgentService(
            llm_provider=llm_provider,
            learning_engine=self.learning,
            memory_service=self.memory,
            feedback_learning=self.feedback_learning,
            weather_service=self.weather_service,
            rag_engine=self.rag_engine,
            backend_url=backend_url
        )

        logger.info("✅ HSIL services initialized (simplified architecture)")

    async def start(self):
        """Start background services"""
        logger.info("Starting HSIL background services...")
        await self.weather_sync.start()
        await self.conversational_agent.initialize()
        logger.info("✅ HSIL background services started")

    async def stop(self):
        """Stop background services"""
        logger.info("Stopping HSIL background services...")
        await self.weather_sync.stop()
        logger.info("✅ HSIL background services stopped")

    # ==================== EVENT PROCESSING ====================

    async def process_event(
        self,
        device_id: str,
        sensor_id: str,
        event_type: str,
        value: Any,
        location: str = "Unknown",
        device_type: str = "unknown",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process sensor event through simplified pipeline:
        1. Ingest event
        2. ML learning (River learns patterns)
        3. Check for anomalies/erratic behavior
        4. Generate incidents if needed
        """
        try:
            # 1. Ingest event
            context = await self.event_ingestion.ingest_mqtt_event(
                device_id=device_id,
                sensor_id=sensor_id,
                event_type=event_type,
                value=value,
                location=location,
                device_type=device_type,
                metadata=metadata
            )

            # 2. Get environmental context
            env = self.weather_service.cached_context

            # 3. ML learning - River learns from this event
            await self.learning.learn_from_sensor_data(context, env)

            # 4. Check for anomalies
            anomaly_detected = False
            anomaly_score = 0.0
            if isinstance(value, (int, float)):
                anomaly_detected, anomaly_score = await self.learning.is_anomalous(
                    device_id=device_id,
                    metric=event_type,
                    value=float(value)
                )
                if anomaly_detected:
                    logger.warning(
                        f"Anomaly: {device_id}/{event_type}={value} (score: {anomaly_score:.2f})"
                    )

            # 5. Check erratic behavior (from frequency tracking)
            erratic_data = await self.learning.get_all_erratic_devices()
            is_erratic = any(d["device_id"] == device_id and d["is_erratic"] for d in erratic_data)

            return {
                "status": "processed",
                "device_id": device_id,
                "event_type": event_type,
                "value": value,
                "anomaly_detected": anomaly_detected,
                "anomaly_score": anomaly_score,
                "is_erratic": is_erratic,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    # ==================== CONVERSATIONAL INTERFACE ====================

    async def chat(
        self,
        message: str,
        session_id: Optional[str] = None
    ) -> ConversationResponse:
        """
        Chat interface - LLM reasons from all available data.
        """
        home_state = await self.get_home_state()

        response = await self.conversational_agent.chat(
            message=message,
            home_state=home_state.model_dump(mode='json'),
            session_id=session_id
        )

        # Execute action if recommended
        if response.action:
            await self.action_dispatcher.dispatch(response.action)

            # Learn from user action
            env = await self.weather_service.get_environmental_context()
            await self.river_feedback.learn_from_user_feedback(
                user_intent=message,
                location="home",
                action_taken=response.action,
                env=env
            )

        return response

    async def provide_feedback(
        self,
        interaction_id: str,
        feedback_type: str,
        rating: Optional[int] = None,
        correction: Optional[str] = None
    ):
        """Record user feedback"""
        await self.conversational_agent.provide_feedback(
            interaction_id=interaction_id,
            feedback_type=feedback_type,
            rating=rating,
            correction=correction
        )

    # ==================== HOME STATE ====================

    async def get_home_state(self) -> HomeState:
        """Get current state of all devices"""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.backend_url}/api/devices")
                response.raise_for_status()
                devices_data = response.json()

            device_states = []
            devices_list = devices_data.get("devices", []) if isinstance(devices_data, dict) else devices_data

            for device in devices_list:
                device_id = device.get("id")
                if not device_id:
                    continue

                state = DeviceState(
                    id=device_id,
                    type=device.get("type", "unknown"),
                    label=device.get("name", "Unknown Device"),
                    state=device.get("state", "normal"),
                    value=device.get("value"),
                    active=device.get("active", False),
                    location=device.get("zone_id", "Unknown"),
                    last_updated=datetime.now(),
                    trend=device.get("trend"),
                    readings=device.get("readings")  # Include all sensor readings
                )
                device_states.append(state)

            logger.info(f"Fetched {len(device_states)} devices from backend")
            return HomeState(devices=device_states, timestamp=datetime.now())

        except Exception as e:
            logger.error(f"Error fetching home state: {e}", exc_info=True)
            return HomeState(devices=[], timestamp=datetime.now(), summary={"error": str(e)})

    # ==================== STATISTICS ====================

    async def get_stats(self) -> Dict[str, Any]:
        """Get HSIL statistics"""
        return {
            "hsil_version": "3.0.0-simplified",
            "architecture": "ML → LLM → response",
            "feedback_learning": await self.feedback_learning.get_stats(),
            "river_ml": await self.learning.get_stats(),
            "incident_generator": await self.incident_generator.get_stats(),
            "timestamp": datetime.now().isoformat()
        }

    async def get_learned_preferences(self) -> Dict[str, Any]:
        """Get learned preferences from ML"""
        river_comfort = {}
        for device_id in self.learning.baseline_models.keys():
            location = device_id.split("_")[0] if "_" in device_id else device_id
            if location not in river_comfort:
                river_pref = await self.learning.get_comfort_preference(location)
                if river_pref:
                    river_comfort[location] = river_pref

        user_prefs = await self.feedback_learning.get_all_preferences(min_confidence=0.6)
        return {
            "river_comfort_preferences": river_comfort,
            "user_preferences": user_prefs,
            "timestamp": datetime.now().isoformat()
        }

    async def get_model_health(self) -> Dict[str, Any]:
        """
        Get detailed model health metrics.

        Returns model maturity, confidence scores, learning velocity, and training status.
        """
        stats = await self.learning.get_stats()

        return {
            "model_maturity": stats.get("model_maturity", {}),
            "learning_velocity": stats.get("learning_velocity", {}),
            "model_counts": {
                "comfort_updates": stats.get("comfort_model_updates", 0),
                "routine_updates": stats.get("routine_model_updates", 0),
                "occupancy_updates": stats.get("occupancy_model_updates", 0),
                "total_updates": stats.get("total_model_updates", 0),
                "anomaly_models": stats.get("anomaly_models_active", 0),
                "baseline_models": stats.get("baseline_models_active", 0),
            },
            "feedback_stats": await self.feedback_learning.get_stats(),
            "timestamp": datetime.now().isoformat()
        }

    async def get_device_health(self) -> Dict[str, Any]:
        """
        Get per-device health metrics.

        Returns anomaly scores, baseline statistics, and erratic behavior for each device.
        """
        stats = await self.learning.get_stats()
        device_health = stats.get("device_health", [])

        return {
            "devices": device_health,
            "total_devices": len(device_health),
            "erratic_count": sum(1 for d in device_health if d.get("is_erratic", False)),
            "timestamp": datetime.now().isoformat()
        }

    async def get_climate_insights(self) -> Dict[str, Any]:
        """
        Get AI-powered climate insights using ML learnings and LLM reasoning.

        Combines:
        - Current device readings (temperature, humidity, etc.)
        - Weather data and correlations
        - ML-learned baselines and anomalies
        - Comfort preferences
        - Equipment health status

        Returns LLM-generated insights for display in UI.
        """
        try:
            # Gather all necessary data
            home_state = await self.get_home_state()
            weather_ctx = await self.weather_service.get_environmental_context()
            ml_stats = await self.learning.get_stats()
            preferences = await self.get_learned_preferences()

            # Extract climate-relevant devices
            climate_devices = []
            for device in home_state.devices:
                # Include temperature, humidity, thermostats, HVAC, etc.
                device_type_lower = device.type.lower() if device.type else ""
                readings = device.readings or {}

                if any(keyword in device_type_lower for keyword in ["temperature", "humidity", "thermostat", "hvac", "climate"]):
                    climate_devices.append({
                        "id": device.id,
                        "label": device.label,
                        "type": device.type,
                        "location": device.location,
                        "readings": readings,
                        "value": device.value
                    })
                # Also include if readings contain climate metrics
                elif any(key in readings for key in ["temperature", "humidity", "targetTemperature"]):
                    climate_devices.append({
                        "id": device.id,
                        "label": device.label,
                        "type": device.type,
                        "location": device.location,
                        "readings": readings,
                        "value": device.value
                    })

            # Build prompt for LLM
            prompt = f"""Analyze the current climate conditions and provide 3-5 actionable insights.

Current Climate Data:
{self._format_climate_devices(climate_devices)}

Weather Context:
{self._format_weather_context(weather_ctx)}

ML Learned Baselines:
{self._format_ml_stats(ml_stats)}

Comfort Preferences:
{preferences.get('river_comfort_preferences', {})}

Generate exactly 3-5 insights following these rules:
1. Each insight must have: type (info/warning/success), title, and description
2. Types: "info" for general observations, "warning" for issues, "success" for positive conditions
3. Focus on: comfort analysis, weather impact, equipment efficiency, energy savings, health concerns
4. Be specific and actionable
5. Use actual data from above (temperatures, humidity, equipment status)
6. Reference specific rooms/zones when relevant
7. IMPORTANT: When comparing indoor and outdoor temperatures:
   - If indoor > outdoor, say "warmer inside than outside" or "indoor temperature is higher"
   - If indoor < outdoor, say "cooler inside than outside" or "indoor temperature is lower"
   - Be mathematically accurate with all temperature comparisons

Return ONLY a JSON array with this exact structure:
[
  {{"type": "info|warning|success", "title": "Brief title", "description": "Detailed insight with specific data"}}
]"""

            # Call LLM
            if not self.llm_provider or not self.llm_provider.is_available():
                # Fallback to simple insights if LLM unavailable
                return await self._fallback_climate_insights(climate_devices, weather_ctx)

            response_text, _ = self.llm_provider.chat(
                messages=[{"role": "user", "content": prompt}],
                tools=None,
                temperature=0.3,
                max_tokens=1000
            )

            # Parse JSON response
            import json
            # Extract JSON array from response (handle markdown code blocks)
            response_text = response_text.strip()
            if response_text.startswith("```"):
                # Remove markdown code block
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1]) if len(lines) > 2 else response_text

            insights = json.loads(response_text)

            return {
                "insights": insights,
                "timestamp": datetime.now().isoformat(),
                "source": "llm"
            }

        except Exception as e:
            logger.error(f"Error generating climate insights: {e}", exc_info=True)
            # Fallback to simple insights on error
            try:
                home_state = await self.get_home_state()
                weather_ctx = await self.weather_service.get_environmental_context()
                climate_devices = [d for d in home_state.devices if d.type and "temperature" in d.type.lower()]
                return await self._fallback_climate_insights(climate_devices, weather_ctx)
            except:
                return {
                    "insights": [{
                        "type": "warning",
                        "title": "Insights Unavailable",
                        "description": "Unable to generate climate insights at this time."
                    }],
                    "timestamp": datetime.now().isoformat(),
                    "source": "error"
                }

    def _format_climate_devices(self, devices) -> str:
        """Format climate devices for LLM prompt"""
        if not devices:
            return "No climate devices found"

        lines = []
        for device in devices:
            readings = device.get("readings", {})
            location = device.get("location", "Unknown")
            label = device.get("label", "Unknown")

            reading_str = ", ".join([f"{k}={v}" for k, v in readings.items()])
            lines.append(f"- {label} ({location}): {reading_str}")

        return "\n".join(lines)

    def _format_weather_context(self, weather_ctx) -> str:
        """Format weather context for LLM prompt"""
        if not weather_ctx:
            return "Weather data unavailable"

        # EnvironmentalContext has nested weather object
        weather = weather_ctx.weather if hasattr(weather_ctx, 'weather') else weather_ctx

        return f"""Temperature: {weather.temperature}°F
Feels Like: {weather.feels_like}°F
Humidity: {weather.humidity}%
Conditions: {weather.description}
Wind: {weather.wind_speed} mph"""

    def _format_ml_stats(self, stats) -> str:
        """Format ML stats for LLM prompt"""
        device_health = stats.get("device_health", [])
        if not device_health:
            return "No ML baseline data available yet"

        lines = []
        for device in device_health[:10]:  # Limit to top 10
            device_id = device.get("device_id", "unknown")
            baseline = device.get("baseline", {})
            mean = baseline.get("mean")
            if mean is not None:
                lines.append(f"- {device_id}: baseline={mean:.1f}, anomaly_score={device.get('anomaly_score', 0):.2f}")

        return "\n".join(lines) if lines else "Learning baselines..."

    async def _fallback_climate_insights(self, climate_devices, weather_ctx) -> Dict[str, Any]:
        """Fallback insights when LLM is unavailable"""
        insights = []

        # Simple temperature check
        if climate_devices:
            temps = []
            for device in climate_devices:
                readings = device.get("readings", {})
                if "temperature" in readings:
                    temps.append(readings["temperature"])

            if temps:
                avg_temp = sum(temps) / len(temps)
                if avg_temp < 65:
                    insights.append({
                        "type": "info",
                        "title": "Cool Indoor Temperature",
                        "description": f"Average temperature is {avg_temp:.1f}°F. Consider adjusting heating."
                    })
                elif avg_temp > 78:
                    insights.append({
                        "type": "info",
                        "title": "Warm Indoor Temperature",
                        "description": f"Average temperature is {avg_temp:.1f}°F. Consider adjusting cooling."
                    })

        # Weather insight
        if weather_ctx:
            insights.append({
                "type": "info",
                "title": f"Current Weather: {weather_ctx.conditions}",
                "description": f"Outside temperature is {weather_ctx.temperature}°F with {weather_ctx.humidity}% humidity."
            })

        if not insights:
            insights.append({
                "type": "info",
                "title": "Climate Monitoring Active",
                "description": "Gathering baseline data. Insights will improve as the system learns your patterns."
            })

        return {
            "insights": insights,
            "timestamp": datetime.now().isoformat(),
            "source": "fallback"
        }
