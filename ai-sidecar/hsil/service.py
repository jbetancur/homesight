"""
HSIL Service Coordinator

Main service that coordinates all HSIL components:
- Event Ingestion
- Feature Extraction
- Memory
- Behavior Models
- Policy Engine
- Conversational Agent
- Action Dispatcher
- Adaptive Learning
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from .types import (
    EventContext,
    DeviceState,
    HomeState,
    ConversationRequest,
    ConversationResponse
)
from .event_ingestion import EventIngestionService
from .feature_extraction import FeatureExtractionService
from .memory import HomeMemoryService
from .policy_engine import PolicyEngineService
from .action_dispatcher import ActionDispatcherService
from .conversational_agent import ConversationalAgentService
from .feedback_learning import FeedbackLearningService
from .weather_service import WeatherService
from .weather_sync import WeatherSyncService
from .hsil_ml_river import HSILRiverLearningEngine
from .river_feedback_adapter import RiverFeedbackAdapter

logger = logging.getLogger(__name__)


class HSILService:
    """
    HomeSight Intelligence Layer - Main Service Coordinator
    """

    def __init__(
        self,
        chroma_client=None,
        llm_provider=None,
        mqtt_client=None,
        backend_url: str = "http://localhost:8080",
        db_path: str = "/var/lib/homesight/hsil_memory.db"
    ):
        """
        Initialize HSIL service with shared resources from ai-sidecar.

        Args:
            chroma_client: Shared ChromaDB client from RAG engine
            llm_provider: Shared LLM provider from ai-sidecar
            mqtt_client: Shared MQTT client
            backend_url: HomeSight backend API URL
            db_path: Path to HSIL SQLite database
        """
        self.backend_url = backend_url
        self.db_path = db_path

        # Initialize all sub-services
        logger.info("Initializing HSIL services...")

        # Weather & Environmental (initialize first)
        self.weather_service = WeatherService()
        self.weather_sync = WeatherSyncService(
            weather_service=self.weather_service,
            refresh_interval_minutes=90
        )

        # Core data processing
        self.event_ingestion = EventIngestionService(db_path=db_path)
        self.feature_extraction = FeatureExtractionService()

        # Memory & Learning
        self.memory = HomeMemoryService(
            db_path=db_path,
            chroma_client=chroma_client
        )
        self.learning = HSILRiverLearningEngine(
            db_path=db_path,
            weather_service=self.weather_service
        )
        self.river_feedback = RiverFeedbackAdapter(learning_engine=self.learning)
        self.feedback_learning = FeedbackLearningService(db_path=db_path)

        # Intelligence
        self.policy_engine = PolicyEngineService()

        # Output
        self.action_dispatcher = ActionDispatcherService(
            mqtt_client=mqtt_client
        )

        # Conversational interface
        self.conversational_agent = ConversationalAgentService(
            llm_provider=llm_provider,
            memory_service=self.memory,
            feedback_learning=self.feedback_learning,
            policy_engine=self.policy_engine,
            weather_service=self.weather_service,
            backend_url=backend_url
        )

        logger.info("✅ HSIL services initialized successfully")

    async def start(self):
        """Start background services"""
        logger.info("Starting HSIL background services...")

        # Start weather sync service
        await self.weather_sync.start()

        # Initialize conversational agent's device ontology
        await self.conversational_agent.initialize()

        logger.info("✅ HSIL background services started")

    async def stop(self):
        """Stop background services"""
        logger.info("Stopping HSIL background services...")

        # Stop weather sync
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
        Process an incoming sensor event through the HSIL pipeline.

        Pipeline:
        1. Event Ingestion (normalize, enrich with trends/anomalies)
        2. Feature Extraction (extract high-level features)
        3. Adaptive Learning (update baselines, learn patterns)
        4. Behavior Model (make predictions if applicable)
        5. Policy Engine (determine if action needed)
        6. Action Dispatcher (execute action if needed)

        Returns:
            Processing result with context, features, predictions, actions
        """
        try:
            # 1. Ingest and enrich event
            context = await self.event_ingestion.ingest_mqtt_event(
                device_id=device_id,
                sensor_id=sensor_id,
                event_type=event_type,
                value=value,
                location=location,
                device_type=device_type,
                metadata=metadata
            )

            # 2. Extract features
            features = await self.feature_extraction.extract_features(context)

            # 3. Get cached environmental context (no blocking API call)
            env = self.weather_service.cached_context

            # 4. Learn from sensor data (River ML engine)
            await self.learning.learn_from_sensor_data(context, env)

            # 5. Check for anomalies using River ML
            predictions = []
            actions_taken = []

            # Check if anomalous
            if isinstance(value, (int, float)):
                is_anomalous, anomaly_score = await self.learning.is_anomalous(
                    device_id=device_id,
                    metric=event_type,
                    value=float(value)
                )

                if is_anomalous:
                    logger.warning(
                        f"Anomaly detected: {device_id}/{event_type} = {value} "
                        f"(anomaly_score: {anomaly_score:.2f})"
                    )

            # River ML handles predictions via learn_from_sensor_data
            # Policy engine can still trigger actions based on thresholds

            return {
                "status": "processed",
                "context": context.model_dump(mode='json'),
                "features": [f.model_dump(mode='json') for f in features],
                "predictions": [p.model_dump(mode='json') for p in predictions],
                "actions_taken": actions_taken,
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
        Conversational interface to HSIL.

        Args:
            message: User's message
            session_id: Optional session ID for multi-turn conversation

        Returns:
            ConversationResponse with reply and optional action
        """
        # Get current home state
        home_state = await self.get_home_state()

        # Process conversation
        response = await self.conversational_agent.chat(
            message=message,
            home_state=home_state.model_dump(mode='json'),
            session_id=session_id
        )

        # If action recommended, dispatch it
        if response.action:
            await self.action_dispatcher.dispatch(response.action)

            # Get environmental context
            env = await self.weather_service.get_environmental_context()

            # Learn from this user action (River ML)
            await self.river_feedback.learn_from_user_feedback(
                user_intent=message,
                location="home",  # TODO: Extract from context
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
        """Record user feedback on a conversation"""
        await self.conversational_agent.provide_feedback(
            interaction_id=interaction_id,
            feedback_type=feedback_type,
            rating=rating,
            correction=correction
        )

    # ==================== HOME STATE ====================

    async def get_home_state(self) -> HomeState:
        """
        Get current state of all devices in the home.

        Fetches from HomeSight backend and enriches with HSIL context.
        """
        import httpx

        try:
            # Fetch devices from backend
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.backend_url}/api/devices")
                response.raise_for_status()
                devices_data = response.json()

            # Convert to DeviceState with HSIL enrichment
            device_states = []

            # Handle both list and dict responses
            if isinstance(devices_data, dict):
                devices_list = devices_data.get("devices", [])
            else:
                devices_list = devices_data

            for device in devices_list:
                device_id = device.get("id")
                if not device_id:
                    continue

                # Use enriched data from backend (state, active, value already included)
                state_value = device.get("state", "normal")
                current_value = device.get("value")
                active = device.get("active", False)
                trend = device.get("trend")

                # Debug logging
                logger.debug(f"Device {device_id}: state={state_value}, active={active}, raw_device={device}")

                # Determine device type for icon
                device_type = device.get("type", "unknown")
                if "temp" in device_type.lower():
                    device_type = "temp"
                elif "humid" in device_type.lower():
                    device_type = "humidity"
                elif "leak" in device_type.lower() or "water" in device_type.lower():
                    device_type = "leak"
                elif "motion" in device_type.lower():
                    device_type = "motion"

                # Build DeviceState
                state = DeviceState(
                    id=device_id,
                    type=device_type,
                    label=device.get("name", "Unknown Device"),
                    state=state_value,
                    value=current_value,
                    active=active,
                    location=device.get("zone_id", "Unknown"),
                    last_updated=datetime.now(),
                    trend=trend
                )

                device_states.append(state)

            logger.info(f"Fetched {len(device_states)} devices from backend")

            return HomeState(
                devices=device_states,
                timestamp=datetime.now()
            )

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching home state: {e}")
            return HomeState(
                devices=[],
                timestamp=datetime.now(),
                summary={"error": f"HTTP error: {str(e)}"}
            )
        except Exception as e:
            logger.error(f"Error fetching home state: {e}", exc_info=True)
            return HomeState(
                devices=[],
                timestamp=datetime.now(),
                summary={"error": str(e)}
            )

    # ==================== STATISTICS & MONITORING ====================

    async def get_stats(self) -> Dict[str, Any]:
        """Get HSIL statistics"""
        feedback_stats = await self.feedback_learning.get_stats()
        river_stats = await self.learning.get_stats()

        return {
            "hsil_version": "2.0.0-river",
            "feedback_learning": feedback_stats,
            "river_ml": river_stats,
            "timestamp": datetime.now().isoformat()
        }

    async def get_learned_preferences(self) -> Dict[str, Any]:
        """Get all learned preferences"""
        # Get River ML comfort preferences for all known locations
        # (River learns these automatically from sensor data)
        river_comfort = {}

        # Get locations from baseline models
        for device_id in self.learning.baseline_models.keys():
            # Extract location from device context if available
            # For now, use device_id as location proxy
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
