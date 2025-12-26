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
import os
import json
import time
import fcntl
from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path

from config import get_config

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
from .weather_client import WeatherClient
from .hsil_ml_river import HSILRiverLearningEngine
from .river_feedback_adapter import RiverFeedbackAdapter
from .incident_generator import IncidentGenerator
from .climate_insights import (
    compute_climate_context,
    generate_rule_based_insights,
    generate_llm_insights,
    validate_insights,
)

logger = logging.getLogger(__name__)

# Shared cache directory for multi-worker coordination
CACHE_DIR = Path("/tmp/homesight_cache")
CACHE_DIR.mkdir(exist_ok=True)
CLIMATE_INSIGHTS_CACHE_FILE = CACHE_DIR / "climate_insights.json"
CLIMATE_INSIGHTS_LOCK_FILE = CACHE_DIR / "climate_insights.lock"


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

        # Get config
        config = get_config()

        # Weather client - fetches from Go API
        self.weather_service = WeatherClient()

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

        # Concurrency control for LLM access
        import asyncio
        self._llm_lock = asyncio.Lock()  # Prevent simultaneous LLM calls
        self._background_task = None

        logger.info("✅ HSIL services initialized (simplified architecture)")

    async def start(self):
        """Start background services"""
        logger.info("Starting HSIL background services...")

        # Initialize conversational agent (needed by all workers)
        await self.conversational_agent.initialize()

        # Only run background tasks in one worker to avoid duplicate work
        import asyncio
        worker_id = os.getenv("WORKER_ID", "0")
        if worker_id == "0" or not os.getenv("GUNICORN_WORKERS"):
            logger.info(f"Worker {worker_id}: Starting background tasks (climate insights)")

            # Weather is now fetched on-demand from Go API - no polling needed

            # Start climate insights regeneration (LLM call every 10 min)
            self._background_task = asyncio.create_task(self._climate_insights_background_loop())
        else:
            logger.info(f"Worker {worker_id}: Skipping background tasks (only run in worker 0)")

        logger.info("✅ HSIL background services started")

    async def stop(self):
        """Stop background services"""
        logger.info("Stopping HSIL background services...")
        # Weather client doesn't need cleanup
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
        No lock needed here - the LLM provider has its own thread safety for local models.
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

    async def _climate_insights_background_loop(self):
        """Background task that regenerates climate insights every 10 minutes"""
        import asyncio
        import time

        # Wait 2 minutes after startup before first generation
        await asyncio.sleep(120)

        while True:
            try:
                logger.info("Background: Regenerating climate insights...")
                await self._generate_climate_insights_internal()
                logger.info("Background: Climate insights regenerated successfully")
            except Exception as e:
                logger.error(f"Background climate insights regeneration failed: {e}")

            # Wait 10 minutes before next regeneration
            await asyncio.sleep(600)

    async def get_climate_insights(self) -> Dict[str, Any]:
        """
        Get AI-powered climate insights using hybrid approach:
        1. Rule-based computation of all numeric facts
        2. LLM reasoning with strict guardrails (optional)

        Results are cached and regenerated in background every 10 minutes.
        """
        # Check shared file cache first (works across all workers)
        try:
            if CLIMATE_INSIGHTS_CACHE_FILE.exists():
                with open(CLIMATE_INSIGHTS_CACHE_FILE, 'r') as f:
                    cache_data = json.load(f)
                    cached_time = cache_data.get('cached_at', 0)
                    # Cache is valid for up to 15 minutes
                    if time.time() - cached_time < 900:
                        logger.debug("Returning cached climate insights")
                        return cache_data.get('data', {})
        except Exception as e:
            logger.warning(f"Failed to read cache file: {e}")

        # Generate fresh insights
        logger.info("No cached insights, generating...")
        try:
            return await self._generate_climate_insights_internal()
        except Exception as e:
            logger.error(f"Failed to generate climate insights: {e}")
            return {
                "insights": [{
                    "type": "warning",
                    "title": "Insights Unavailable",
                    "description": "Climate insights are being generated. Please refresh in a moment."
                }],
                "timestamp": datetime.now().isoformat(),
                "source": "error"
            }

    async def _generate_climate_insights_internal(self) -> Dict[str, Any]:
        """
        Generate climate insights using hybrid architecture:
        1. compute_climate_context() - all numeric facts computed deterministically
        2. generate_llm_insights() or generate_rule_based_insights() - insight generation
        3. validate_insights() - post-validation against ground truth
        """
        try:
            # Step 1: Compute all climate facts (pure data, no LLM)
            context = await compute_climate_context(
                backend_url=self.backend_url,
                weather_service=self.weather_service,
            )

            # Step 2: Generate insights
            # Try LLM first if available, fall back to rules
            use_llm = self.llm_provider and self.llm_provider.is_available()

            if use_llm:
                logger.info("Generating climate insights with LLM")
                insights = await generate_llm_insights(context, self.llm_provider)
                # Step 3: Validate LLM output against ground truth
                insights = validate_insights(insights, context)
                source = "llm"
            else:
                logger.info("Generating climate insights with rules")
                insights = generate_rule_based_insights(context)
                source = "rule_based"

            # Convert to dict format
            result = {
                "insights": [i.model_dump() for i in insights],
                "timestamp": datetime.now().isoformat(),
                "source": source
            }

            # Cache result
            self._write_climate_insights_cache(result)
            return result

        except Exception as e:
            logger.error(f"Error generating climate insights: {e}", exc_info=True)
            return {
                "insights": [{
                    "type": "warning",
                    "title": "Insights Unavailable",
                    "description": "Unable to generate climate insights at this time."
                }],
                "timestamp": datetime.now().isoformat(),
                "source": "error"
            }

    def _write_climate_insights_cache(self, result: Dict[str, Any]):
        """Write climate insights to shared cache file with file locking"""
        try:
            with open(CLIMATE_INSIGHTS_LOCK_FILE, 'w') as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    cache_data = {
                        'data': result,
                        'cached_at': time.time()
                    }
                    with open(CLIMATE_INSIGHTS_CACHE_FILE, 'w') as f:
                        json.dump(cache_data, f)
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except Exception as e:
            logger.error(f"Failed to write climate insights cache: {e}")
