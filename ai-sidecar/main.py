"""
HomeSight AI Sidecar Service
"""

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from typing import Optional
from datetime import datetime
import logging
import os
import httpx
from pathlib import Path
from contextlib import asynccontextmanager

# Configuration
from config import get_config

# Metrics
from metrics.metrics import get_metrics, active_sessions, chat_response_time, chat_requests

# Models
from models.chat import ChatRequest, ChatResponse
from models.analyze import AnalyzeRequest, AnalyzeResponse
from models.device import DeviceEvent
from models.device_profile import DeviceProfile

# Services
from services.session_service import SessionService
from services.document_service import DocumentService
from services.mqtt_service import initialize_mqtt_service, shutdown_mqtt_service, get_mqtt_service
from services.sse_service import SSEService, get_sse_service

# LLM and RAG
from llm.provider import LLMProvider
from rag.engine import RAGEngine

# Prompts
from hsil.prompts import get_prompt

# Queue management
from queues.task_queue import TaskQueue, QueueType, QueueConfig

# Configure logging to both console and file
# Use /app/log in Docker, logs locally
if os.path.exists('/.dockerenv'):
    log_dir = Path('/app/log')
else:
    log_dir = Path('logs')
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / 'ai.log'

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# File handler (to file)
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)

# Console handler (to stdout)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)

# Remove existing handlers to avoid duplication
root_logger.handlers = []

# Add new handlers
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# Create module logger
logger = logging.getLogger(__name__)


# Global service instances (initialized on startup)
llm_provider = None
rag_engine = None
session_service = None
document_service = None
hsil_service = None  # HSIL service (handles all chat)

# Task queues
discovery_queue = None
ingestion_queue = None
analysis_task_queue = None

# Incident analysis cache (in-memory storage for background analyses)
# Key: incident_id, Value: {analysis, insights, actions, metadata, timestamp, status}
incident_analysis_cache = {}

# Cached health status (updated periodically, never blocks)
import asyncio
cached_health_status = {
    "status": "initializing",
    "llm": {"available": False},
    "rag": {"available": False, "documents": 0},
    "sessions": {"active": 0}
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("🚀 Starting HomeSight AI Service")

    # Initialize services
    global llm_provider, rag_engine, session_service, chat_service, document_service
    global discovery_queue, ingestion_queue, analysis_task_queue, hsil_service

    try:
        config = get_config()

        # Initialize RAG engine
        rag_path = Path(config.rag.persist_directory)
        try:
            rag_path.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            logger.warning(f"Permission denied for {rag_path}, using fallback")
            rag_path = Path(config.rag.fallback_directory)
            rag_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initializing RAG engine at {rag_path}")
        rag_engine = RAGEngine(persist_directory=str(rag_path))

        stats = rag_engine.get_stats()
        logger.info(f"RAG loaded: {stats['total_documents']} documents")

        # Initialize LLM provider with config-driven chat mode
        logger.info(f"Initializing LLM provider (chat_mode={config.llm.chat_mode})...")
        llm_provider = LLMProvider(config.llm)

        if llm_provider.is_available():
            info = llm_provider.get_info()
            logger.info(f"LLM ready: {info}")
        else:
            logger.error("❌ No LLM available!")

        # Initialize manufacturer domain registry
        logger.info("Initializing manufacturer domain registry...")
        from rag.manufacturer_domains import initialize_known_domains
        initialize_known_domains()
        logger.info("✅ Manufacturer domain registry initialized")

        # Initialize services
        session_service = SessionService(session_timeout_minutes=60)
        document_service = DocumentService(
            rag_engine=rag_engine,
            cache_dir=Path(config.document_fetcher.cache_directory).expanduser(),
            openai_api_key=config.llm.openai_api_key
        )

        # Initialize task queues with resource awareness
        discovery_queue = TaskQueue(
            QueueType.DISCOVERY,
            QueueConfig(
                max_concurrent=config.queues.discovery.max_concurrent,
                max_queue_depth=config.queues.discovery.max_queue_depth,
                cpu_threshold=config.queues.discovery.cpu_threshold,
                memory_threshold=config.queues.discovery.memory_threshold
            )
        )

        ingestion_queue = TaskQueue(
            QueueType.INGESTION,
            QueueConfig(
                max_concurrent=config.queues.ingestion.max_concurrent,
                max_queue_depth=config.queues.ingestion.max_queue_depth,
                cpu_threshold=config.queues.ingestion.cpu_threshold,
                memory_threshold=config.queues.ingestion.memory_threshold
            )
        )

        analysis_task_queue = TaskQueue(
            QueueType.ANALYSIS,
            QueueConfig(
                max_concurrent=config.queues.analysis.max_concurrent,
                max_queue_depth=config.queues.analysis.max_queue_depth,
                cpu_threshold=config.queues.analysis.cpu_threshold,
                memory_threshold=config.queues.analysis.memory_threshold
            )
        )

        # Initialize MQTT service for real-time device state
        logger.info("Initializing MQTT service...")
        try:
            mqtt_broker = os.getenv("MQTT_BROKER_URL", "localhost")
            mqtt_port = int(os.getenv("MQTT_BROKER_PORT", "1883"))
            initialize_mqtt_service(broker_url=mqtt_broker, broker_port=mqtt_port)
            logger.info(f"✅ MQTT service connected to {mqtt_broker}:{mqtt_port}")

            # Register incident callback for real-time analysis
            mqtt_svc = get_mqtt_service()
            if mqtt_svc:
                def on_incident_received(incident_payload):
                    """Queue incidents for AI analysis when received via MQTT."""
                    logger.info(f"Incident received via MQTT: {incident_payload.get('title')}")
                    # TODO: Queue for analysis using analysis_queue

                mqtt_svc.on_incident(on_incident_received)
                logger.info("✅ Registered MQTT incident callback")
        except Exception as e:
            logger.warning(f"Failed to initialize MQTT service: {e}")
            logger.warning("Continuing without real-time MQTT updates...")

        # Initialize HSIL (HomeSight Intelligence Layer)
        logger.info("Initializing HSIL (HomeSight Intelligence Layer)...")
        try:
            from hsil.service import HSILService

            # Get MQTT client
            mqtt_service = get_mqtt_service()
            mqtt_client = mqtt_service.client if mqtt_service else None

            # Get ChromaDB client from RAG engine
            chroma_client = rag_engine.client if rag_engine else None

            hsil_service = HSILService(
                chroma_client=chroma_client,
                llm_provider=llm_provider,
                mqtt_client=mqtt_client,
                rag_engine=rag_engine,  # Pass full RAGEngine for troubleshooting queries
                backend_url=config.backend_url,
                db_path="/var/lib/homesight/hsil_memory.db"
            )

            # Start HSIL background services (weather sync, device ontology)
            await hsil_service.start()

            logger.info("✅ HSIL initialized and started successfully")
        except Exception as e:
            logger.error(f"Failed to initialize HSIL: {e}")
            logger.warning("Continuing without HSIL...")

        logger.info("✅ All services and queues initialized")
        logger.info(f"Queues: discovery={config.queues.discovery.max_concurrent}, "
                    f"ingestion={config.queues.ingestion.max_concurrent}, "
                    f"analysis={config.queues.analysis.max_concurrent}")

    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise

    # Start background task to update health status periodically
    # This ensures health endpoint is NEVER blocked by inference work
    async def update_health_status():
        """Periodically update cached health status (never blocks)"""
        while True:
            try:
                await asyncio.sleep(2)  # Update every 2 seconds
                global cached_health_status

                active_session_count = len(session_service._sessions) if session_service else 0
                doc_count = getattr(rag_engine, '_cached_count', 0) if rag_engine else 0

                cached_health_status = {
                    "status": "healthy",
                    "llm": {
                        "available": llm_provider is not None and llm_provider.is_available()
                    } if llm_provider else {"available": False},
                    "rag": {
                        "available": rag_engine is not None,
                        "documents": doc_count
                    },
                    "sessions": {
                        "active": active_session_count
                    }
                }

                # Update Prometheus metrics
                active_sessions.set(active_session_count)

            except Exception as e:
                logger.error(f"Error updating health status: {e}")

    # Start health status updater in background
    health_task = asyncio.create_task(update_health_status())

    # Optionally start vendor indexer (background documentation crawler)
    vendor_indexer_task = None
    if config.search.enable_vendor_indexer:
        try:
            logger.info("Starting vendor indexer (background documentation crawler)...")
            from vendor_indexer import start_background_indexer
            vendor_indexer_task = asyncio.create_task(start_background_indexer())
            logger.info("✅ Vendor indexer started")
        except Exception as e:
            logger.warning(f"Failed to start vendor indexer: {e}")

    yield

    # Shutdown
    logger.info("Shutting down services...")

    # Shutdown HSIL services
    if hsil_service:
        logger.info("Stopping HSIL background services...")
        await hsil_service.stop()

    # Shutdown MQTT service
    shutdown_mqtt_service()

    # Cancel background tasks on shutdown
    health_task.cancel()
    if vendor_indexer_task:
        logger.info("Stopping vendor indexer...")
        from vendor_indexer import stop_background_indexer
        await stop_background_indexer()
    logger.info("Shutting down HomeSight AI Service")


# Create FastAPI app
app = FastAPI(
    title="HomeSight AI Service",
    description="Conversational AI with RAG and function calling",
    version="2.0.0",
    lifespan=lifespan
)

# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint (instant response from cache, never blocks)

    Returns cached health status updated by background task every 2 seconds.
    This ensures the health endpoint is NEVER blocked by LLM inference,
    database queries, or other operations.
    """
    return cached_health_status


# Prometheus metrics endpoint
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint

    Returns metrics in Prometheus text format.
    Scrape this endpoint with Prometheus to collect performance data.
    """
    return Response(content=get_metrics(), media_type="text/plain; charset=utf-8")


# Analysis endpoint - RAG-based document retrieval for incidents
@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    """
    Get contextual AI analysis for an incident.

    Fetches device context, zone info, and recent incidents to provide
    actionable recommendations using LLM reasoning.
    """
    import httpx

    try:
        config = get_config()
        # Extract incident info
        data = request.data
        device_id = data.get("device_id", "")
        incident_type = data.get("type", "unknown")
        severity = data.get("severity", "unknown")
        description = data.get("description", "")

        # Fetch device context from Go API
        device_context = None
        device_incidents = []
        zone_devices = []

        async with httpx.AsyncClient(timeout=10.0) as client:
            # Get device details
            if device_id:
                try:
                    resp = await client.get(f"{config.backend_url}/api/devices/{device_id}")
                    if resp.status_code == 200:
                        device_context = resp.json()
                except Exception as e:
                    logger.warning(f"Failed to fetch device {device_id}: {e}")

                # Get recent incidents for this device
                try:
                    resp = await client.get(f"{config.backend_url}/api/devices/{device_id}/incidents")
                    if resp.status_code == 200:
                        device_incidents = resp.json() or []
                        # Filter to recent incidents (last 5)
                        device_incidents = device_incidents[:5]
                except Exception as e:
                    logger.warning(f"Failed to fetch incidents for {device_id}: {e}")

            # Get zone context if device has a zone
            zone_id = device_context.get("zone_id") if device_context else None
            if zone_id and zone_id != "N/A":
                try:
                    resp = await client.get(f"{config.backend_url}/api/devices")
                    if resp.status_code == 200:
                        all_devices = resp.json()
                        devices_list = all_devices.get("devices", []) if isinstance(all_devices, dict) else all_devices
                        zone_devices = [d for d in devices_list if d.get("zone_id") == zone_id and d.get("id") != device_id]
                except Exception as e:
                    logger.warning(f"Failed to fetch zone devices: {e}")

        # Query RAG for relevant documentation
        rag_sources = []
        if rag_engine:
            manufacturer = device_context.get("manufacturer", "") if device_context else ""
            model = device_context.get("model", "") if device_context else ""

            # Simple query: device + incident type
            query_parts = []
            if manufacturer:
                query_parts.append(manufacturer)
            if model:
                query_parts.append(model)
            query_parts.append(incident_type.replace("_", " "))
            if description:
                query_parts.append(description[:150])

            query = " ".join(query_parts)
            where_filter = {"manufacturer": manufacturer.title()} if manufacturer else None

            try:
                results = rag_engine.query(query, n_results=3, where=where_filter)
                for r in results or []:
                    relevance = r.get('relevance_score', 0)
                    if relevance > 0.25:
                        rag_sources.append({
                            "source": r['metadata'].get('source', 'Documentation'),
                            "relevance": relevance,
                            "excerpt": r['text']  # Use full text, not truncated
                        })
            except Exception as e:
                logger.warning(f"RAG query failed: {e}")

        # Build contextual analysis using LLM
        insights = []
        actions = []
        analysis = ""

        if llm_provider and llm_provider.is_available():
            # Build context for LLM
            context_parts = []

            if device_context:
                device_info = f"Device: {device_context.get('name', device_id)}"
                if device_context.get('manufacturer'):
                    device_info += f" ({device_context.get('manufacturer')} {device_context.get('model', '')})"
                if zone_id:
                    device_info += f" in {zone_id}"
                context_parts.append(device_info)

                # Add battery status if relevant
                if device_context.get("battery"):
                    battery = device_context["battery"]
                    context_parts.append(f"Battery: {battery.get('level', 'unknown')}%")

            if device_incidents:
                recent = [f"- {i.get('title', 'Unknown')} ({i.get('status', 'unknown')})" for i in device_incidents[:3]]
                context_parts.append(f"Recent incidents on this device:\n" + "\n".join(recent))

            if zone_devices:
                other_devices = [d.get('name', d.get('id')) for d in zone_devices[:3]]
                context_parts.append(f"Other devices in {zone_id}: {', '.join(other_devices)}")

            # Build documentation context with full excerpts
            documentation_text = ""
            if rag_sources:
                doc_sections = []
                for idx, s in enumerate(rag_sources[:3], 1):
                    # Use full excerpt for better context
                    doc_sections.append(f"Documentation Source {idx} ({s['source']}):\n{s['excerpt']}")
                documentation_text = "\n\n".join(doc_sections)

            # Build base context without docs
            base_context = chr(10).join(context_parts) if context_parts else "No additional context available."

            # Create incident-focused prompt that extracts device-specific instructions
            # Load from external YAML for hot-reload capability
            if documentation_text:
                prompt = get_prompt(
                    "incident_analysis",
                    "with_documentation",
                    incident_type=incident_type.replace('_', ' ').title(),
                    severity=severity,
                    description=description,
                    device_context=base_context,
                    documentation=documentation_text
                )
            else:
                # Fallback when no documentation available
                prompt = get_prompt(
                    "incident_analysis",
                    "without_documentation",
                    incident_type=incident_type.replace('_', ' ').title(),
                    severity=severity,
                    description=description,
                    device_context=base_context
                )

            try:
                response = await llm_provider.simple_generate_async(prompt, max_tokens=config.llm.analysis_max_tokens)

                # Parse LLM response
                if "ANALYSIS:" in response and "ACTIONS:" in response:
                    parts = response.split("ACTIONS:")
                    analysis = parts[0].replace("ANALYSIS:", "").strip()

                    action_lines = parts[1].strip().split("\n")
                    for line in action_lines:
                        line = line.strip()
                        if line and line[0].isdigit():
                            # Remove number prefix
                            action = line.lstrip("0123456789.").strip()
                            if action:
                                actions.append(action)
                else:
                    # Fallback if format isn't followed
                    analysis = response.strip()
                    actions = ["Check device status in the Devices view", "Use Chat with AI for detailed troubleshooting"]

            except Exception as e:
                logger.error(f"LLM analysis failed: {e}")
                analysis = f"Analysis unavailable. {incident_type.replace('_', ' ').title()} detected on {device_context.get('name', device_id) if device_context else device_id}."
                actions = ["Check device status", "Review device documentation"]
        else:
            # Fallback without LLM
            device_name = device_context.get('name', device_id) if device_context else device_id
            analysis = f"{incident_type.replace('_', ' ').title()} detected on {device_name}."

            if device_incidents:
                analysis += f" This device has {len(device_incidents)} recent incident(s)."

            actions = [
                f"Check {device_name} physical status and connections",
                "Review device readings in the Devices view",
                "Use Chat with AI for detailed troubleshooting steps"
            ]

        # Build insights from context
        if device_incidents and len(device_incidents) > 1:
            insights.append(f"This device has had {len(device_incidents)} incidents recently - may indicate a recurring issue")

        if device_context and device_context.get("battery", {}).get("is_low"):
            insights.append("Device battery is low - this may be related to the current issue")

        if zone_devices:
            insights.append(f"There are {len(zone_devices)} other device(s) in the same zone that may be affected")

        if rag_sources:
            insights.append(f"Found {len(rag_sources)} relevant documentation source(s)")

        if not insights:
            insights.append("No additional context available for this incident")

        return AnalyzeResponse(
            analysis=analysis,
            insights=insights,
            actions=actions if actions else ["Check device status", "Use Chat with AI for help"],
            metadata={
                "type": incident_type,
                "severity": severity,
                "device_id": device_id,
                "zone_id": zone_id,
                "device_name": device_context.get("name") if device_context else None,
                "recent_incidents_count": len(device_incidents),
                "zone_devices_count": len(zone_devices),
                "rag_sources": rag_sources,
                "documentation_available": len(rag_sources) > 0
            }
        )
    except Exception as e:
        logger.error(f"Analysis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Simple chat endpoint (OpenAI-based, used for KB generation)
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Simple OpenAI chat endpoint for knowledge base generation.
    
    This endpoint uses RAG to ground responses in actual device documentation.
    For conversational AI with context, use /hsil/chat instead.
    """
    if not llm_provider:
        raise HTTPException(status_code=503, detail="LLM provider not initialized")
    
    if not llm_provider.openai_client:
        raise HTTPException(status_code=503, detail="OpenAI client not available")
    
    try:
        # Extract device info from context or message for RAG lookup
        rag_context = ""
        if rag_engine:
            message_lower = request.message.lower()
            
            # Get device info from context if provided
            ctx = request.context or {}
            manufacturer_filter = ctx.get("manufacturer")
            model_filter = ctx.get("model")
            device_name = ctx.get("device_name")  # Often contains actual model number
            
            # Fall back to extracting from message if not in context
            if not manufacturer_filter:
                manufacturers = ["zooz", "aqara", "philips", "hue", "lutron", "honeywell", "ecobee", "ring", "nest", "yale", "schlage", "kwikset"]
                for mfg in manufacturers:
                    if mfg in message_lower:
                        manufacturer_filter = mfg.title()
                        break
            
            # Build RAG query from message
            rag_query = request.message
            
            # Query RAG for relevant documentation
            # Try multiple filter strategies to find best match
            try:
                rag_results = None
                filter_used = None
                
                # Strategy 1: Try model match first
                if model_filter and manufacturer_filter:
                    where_filter = {"$and": [
                        {"manufacturer": manufacturer_filter},
                        {"model": model_filter}
                    ]}
                    rag_results = rag_engine.query(rag_query, n_results=5, where=where_filter)
                    if rag_results:
                        filter_used = f"model={model_filter}"
                
                # Strategy 2: Try device_name as model (often contains actual model number like ZST39)
                if not rag_results and device_name and manufacturer_filter:
                    where_filter = {"$and": [
                        {"manufacturer": manufacturer_filter},
                        {"model": device_name}
                    ]}
                    rag_results = rag_engine.query(rag_query, n_results=5, where=where_filter)
                    if rag_results:
                        filter_used = f"device_name={device_name}"
                        logger.info(f"Found RAG results using device_name '{device_name}' as model")
                
                # Strategy 3: Try manufacturer only
                if not rag_results and manufacturer_filter:
                    logger.info(f"No results with model filters, trying manufacturer only")
                    where_filter = {"manufacturer": manufacturer_filter}
                    rag_results = rag_engine.query(rag_query, n_results=5, where=where_filter)
                    if rag_results:
                        filter_used = f"manufacturer={manufacturer_filter}"
                
                if rag_results:
                    # Build context from RAG results
                    rag_docs = []
                    for r in rag_results:
                        # RAG engine returns 'text' key, not 'content'
                        content = r.get("text", "") or r.get("content", "")
                        source = r.get("metadata", {}).get("source", "Unknown")
                        if content:
                            rag_docs.append(f"[Source: {source}]\n{content}")
                    
                    if rag_docs:
                        rag_context = "\n\n---\n\n".join(rag_docs[:3])  # Use top 3 results
                        logger.info(f"RAG context found: {len(rag_docs)} documents, {len(rag_context)} chars (filter={filter_used}, device_name={device_name})")
            except Exception as e:
                logger.warning(f"RAG query failed (continuing without context): {e}")
        
        # Build system prompt with RAG context
        # Load from external YAML for hot-reload capability
        system_prompt = get_prompt("chat", "system_prompt")

        if rag_context:
            system_prompt += "\n" + get_prompt("chat", "with_rag_context", rag_context=rag_context)
        else:
            system_prompt += "\n" + get_prompt("chat", "without_rag_context")
        
        # Build message list
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.message}
        ]
        
        # Use OpenAI for KB generation
        response_text, _ = llm_provider.chat(
            messages=messages,
            tools=None,
            temperature=0.3,  # Lower temperature for more factual responses
            max_tokens=1500,
            override_mode='cloud'  # Always use OpenAI for KB generation
        )
        
        return ChatResponse(
            response=response_text,
            session_id=request.session_id or "single-turn",
            actions_taken=None
        )
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Device event handler (auto-discovery and doc ingestion)
@app.post("/events/device")
async def handle_device_event(event: dict, background_tasks: BackgroundTasks):
    """
    Handle device lifecycle events

    Automatically discovers and ingests comprehensive documentation:
    - Official manufacturer PDFs
    - Support forums
    - Reddit discussions
    - Community guides
    - AI-generated knowledge
    """
    event_type = event.get("type", "")

    if event_type == "device.created":
        device_data = event.get("data", {})
        force = event.get("force", False)  # Force refresh/re-ingest flag

        # Convert to DeviceProfile for type safety
        try:
            device = DeviceProfile.from_dict(device_data)
        except Exception as e:
            logger.error(f"Invalid device data: {e}")
            return {
                "status": "error",
                "message": f"Invalid device data: {str(e)}"
            }

        action = "force refresh" if force else "comprehensive doc discovery"
        logger.info(f"Device created: {device.manufacturer} {device.model} - queuing {action}")

        # Queue document discovery in background
        background_tasks.add_task(discover_device_docs, device, force=force)

        return {
            "status": "queued",
            "message": f"{action.title()} queued for {device.manufacturer} {device.model}",
            "force": force
        }

    return {"status": "ignored", "message": f"Unknown event type: {event_type}"}


async def discover_device_docs(device: DeviceProfile, force: bool = False):
    """
    Background task for comprehensive document discovery

    Args:
        device: DeviceProfile with full device metadata
        force: If True, bypass cache and force refresh
    """
    try:
        logger.info(f"Starting document discovery for device: {device.id} (force={force})")

        if document_service:
            result = await document_service.discover_and_ingest_device_docs(device, force=force)
            logger.info(f"Doc discovery complete: {result}")

            # Verify documents are queryable before updating status
            if result.get("status") == "success":
                verified = await verify_documents_queryable(device)
                if not verified:
                    logger.error(f"Document verification failed for {device.manufacturer} {device.model}")
                    result["status"] = "partial"
                    result["verification_failed"] = True
                else:
                    # Force filesystem sync to ensure durability across container restarts
                    await force_rag_sync()
                    logger.info(f"✅ Documents verified and synced for {device.manufacturer} {device.model}")

            # Update device documentation status in Go backend
            logger.info(f"Updating device {device.id} docs status in Go backend...")
            await update_device_docs_status(device.id, result)
            logger.info(f"Successfully updated device {device.id} docs status")
        else:
            logger.warning("Document service not available")
    except Exception as e:
        logger.error(f"Error in document discovery: {e}", exc_info=True)


async def update_device_docs_status(device_id: str, discovery_result: dict):
    """Send document discovery result back to Go API"""
    import httpx

    try:
        config = get_config()
        status = discovery_result.get("status", "error")
        ingested = status in ["success", "partial"]

        update_payload = {
            "status": status,
            "ingested": ingested,
            "ingested_at": None,  # Let the Go backend set the timestamp
            "kb_content": discovery_result.get("kb_content"),  # Pass generated KB content
            "source_urls": discovery_result.get("source_urls", []),  # Pass source URLs
        }

        url = f"{config.backend_url}/api/devices/{device_id}/docs-status"
        logger.info(f"Posting to {url} with payload: status={status}, ingested={ingested}, kb_content={'yes' if update_payload['kb_content'] else 'no'}")

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(url, json=update_payload)

            if response.status_code == 200:
                logger.info(f"✅ Updated device {device_id} docs status: {status}")
            else:
                logger.warning(f"Failed to update device docs status. Status code: {response.status_code}, Response: {response.text}")
    except httpx.ConnectTimeout:
        logger.error(f"Connection timeout updating device {device_id} docs status - backend may be unreachable")
    except Exception as e:
        logger.error(f"Error updating device docs status: {e}", exc_info=True)


async def verify_documents_queryable(device) -> bool:
    """
    Verify that documents are actually queryable in ChromaDB.

    This ensures that documents have been fully ingested and are available
    for retrieval before we update the device status in the Go backend.
    """
    try:
        if not rag_engine:
            logger.warning("RAG engine not available for verification")
            return False

        # Try to retrieve device-specific documents from ChromaDB
        results = rag_engine.collection.get(
            where={
                "$and": [
                    {"manufacturer": device.manufacturer.title()},
                    {"model": device.model}
                ]
            },
            limit=1
        )

        doc_count = len(results.get('ids', []))
        if doc_count > 0:
            logger.info(f"✅ Verification successful: Found {doc_count} documents for {device.manufacturer} {device.model}")
            return True
        else:
            logger.warning(f"⚠️  Verification failed: No documents found for {device.manufacturer} {device.model}")
            return False

    except Exception as e:
        logger.error(f"Document verification query failed: {e}", exc_info=True)
        return False


async def force_rag_sync():
    """
    Force filesystem sync on RAG directory to ensure durability.

    This addresses the Docker volume buffering issue where data might be
    in OS buffers but not yet written to disk. Critical for container
    restart scenarios.
    """
    try:
        import os
        config = get_config()
        rag_path = Path(config.rag.persist_directory if hasattr(config, 'rag') else "./rag-db")

        if not rag_path.exists():
            logger.warning(f"RAG directory does not exist: {rag_path}")
            return

        # Open directory and force fsync to flush OS buffers to disk
        fd = os.open(str(rag_path), os.O_RDONLY)
        try:
            os.fsync(fd)
            logger.debug(f"RAG directory fsync completed: {rag_path}")
        finally:
            os.close(fd)

    except Exception as e:
        # Log warning but don't fail - this is a safety measure
        # that degrades gracefully if OS doesn't support it
        logger.warning(f"Failed to fsync RAG directory (non-critical): {e}")


# Incident event handler (background analysis)
@app.post("/events/incident")
async def handle_incident_event(event: dict, background_tasks: BackgroundTasks):
    """
    Handle incident lifecycle events and trigger background analysis

    When an incident is created, automatically analyze it in the background
    and notify the Go backend when complete via callback.
    """
    event_type = event.get("type", "")

    if event_type == "incident.created":
        incident_data = event.get("data", {})
        incident_id = incident_data.get("id")
        callback_url = event.get("callback_url")  # Optional callback URL from Go backend

        if not incident_id:
            raise HTTPException(status_code=400, detail="Incident ID required")

        # Mark analysis as pending in cache
        incident_analysis_cache[incident_id] = {
            "status": "pending",
            "analysis": "",
            "insights": [],
            "timestamp": None
        }

        # Queue background analysis with callback
        background_tasks.add_task(analyze_incident_background, incident_data, callback_url)

        logger.info(f"Queued background analysis for incident {incident_id}")
        return {
            "status": "queued",
            "incident_id": incident_id,
            "message": "Incident analysis queued"
        }

    return {"status": "ignored", "message": f"Event type {event_type} not handled"}


async def analyze_incident_background(incident_data: dict, callback_url: Optional[str] = None):
    """
    Analyze incident in background using LLM + RAG documentation.

    Queries RAG for relevant device documentation and uses LLM to extract
    specific, actionable instructions from the documentation.
    """
    import httpx

    incident_id = incident_data.get("id")

    if not incident_id:
        return

    try:
        logger.info(f"Starting background analysis for incident {incident_id}")

        # Call the main analyze endpoint logic
        incident_type = incident_data.get("title", "Unknown incident")
        device_id = incident_data.get("device_id", "")
        description = incident_data.get("description", "")
        severity = incident_data.get("severity", "unknown")

        # Build request for analyze endpoint
        analyze_request = AnalyzeRequest(
            type="incident",
            data={
                "id": incident_id,
                "type": incident_type,
                "severity": severity,
                "device_id": device_id,
                "description": description
            },
            context={
                "incident_id": incident_id,
                "device_id": device_id
            }
        )

        # Call analyze function to get LLM-based analysis
        response = await analyze(analyze_request)

        analysis = response.analysis
        insights = response.insights
        actions = response.actions
        sources = response.metadata.get("rag_sources", []) if response.metadata else []

        logger.info(f"✅ Completed analysis for incident {incident_id}")

        # Save analysis to Go backend database via HTTP PATCH
        try:
            config = get_config()
            go_backend_url = config.backend_url
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.patch(
                    f"{go_backend_url}/api/incidents/{incident_id}/analysis",
                    json={
                        "analysis_status": "completed",
                        "analysis": analysis,
                        "insights": insights,
                        "actions": actions,
                        "analysis_data": {
                            "sources": sources,
                            "severity": severity,
                            "device_id": device_id
                        },
                    }
                )
            logger.info(f"✅ Saved analysis for incident {incident_id} to database")
        except Exception as db_err:
            logger.error(f"Failed to save analysis for incident {incident_id}: {db_err}")

    except Exception as e:
        logger.error(f"Background analysis failed for incident {incident_id}: {e}")

        # Save error status to Go backend database
        try:
            config = get_config()
            go_backend_url = config.backend_url
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.patch(
                    f"{go_backend_url}/api/incidents/{incident_id}/analysis",
                    json={
                        "analysis_status": "failed",
                        "analysis": "Analysis failed",
                        "insights": [str(e)],
                    }
                )
            logger.info(f"Saved error status for incident {incident_id}")
        except Exception as db_err:
            logger.error(f"Failed to save error status for incident {incident_id}: {db_err}")


# Get cached incident analysis
@app.get("/incidents/{incident_id}/analysis")
async def get_incident_analysis(incident_id: str):
    """
    Retrieve cached incident analysis

    Returns pre-computed analysis if available, otherwise returns pending status.
    UI should poll this endpoint after incident creation.
    """
    analysis = incident_analysis_cache.get(incident_id)

    if not analysis:
        return {
            "status": "not_found",
            "message": "No analysis available for this incident"
        }

    return {
        "status": analysis["status"],
        "analysis": analysis.get("analysis", ""),
        "insights": analysis.get("insights", []),
        "actions": analysis.get("actions"),
        "metadata": analysis.get("metadata"),
        "loading": analysis["status"] == "pending"
    }


# RAG status endpoint
@app.get("/rag/status")
async def rag_status():
    """Get RAG engine status and statistics (may be slow during ingestion)"""
    if not rag_engine:
        return {"enabled": False, "message": "RAG engine not initialized"}

    try:
        stats = rag_engine.get_stats()
        return {
            "enabled": True,
            "stats": stats,
            "message": "RAG operational" if stats["total_documents"] > 0 else "No documents yet"
        }
    except Exception as e:
        return {"enabled": False, "error": str(e)}


# Ingestion monitoring endpoints
@app.get("/ingestion/stats")
async def ingestion_stats():
    """Get ingestion statistics and monitoring data"""
    from services.document_service import get_ingestion_tracker
    tracker = get_ingestion_tracker()
    return tracker.get_stats()


@app.get("/ingestion/log")
async def ingestion_log(limit: int = 50):
    """Get recent ingestion records"""
    from services.document_service import get_ingestion_tracker
    tracker = get_ingestion_tracker()
    return {
        "records": tracker.get_ingestion_log(limit),
        "total_returned": min(limit, len(tracker.records))
    }


# Detailed status endpoint (can be slow)
@app.get("/status")
async def detailed_status():
    """Get detailed service status (warning: may be slow during ingestion)"""
    rag_stats = rag_engine.get_stats() if rag_engine else {}
    llm_info = llm_provider.get_info() if llm_provider else {}
    session_stats = session_service.get_stats() if session_service else {}

    return {
        "status": "healthy",
        "llm": llm_info,
        "rag": {
            "available": rag_engine is not None,
            "documents": rag_stats.get("total_documents", 0),
            "details": rag_stats
        },
        "sessions": session_stats
    }


# Session management endpoints
@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session information"""
    if not session_service:
        raise HTTPException(status_code=503, detail="Session service not initialized")

    session = session_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session.session_id,
        "message_count": len(session.messages),
        "created_at": session.created_at,
        "updated_at": session.updated_at
    }


@app.delete("/sessions/{session_id}")
async def clear_session(session_id: str):
    """Clear a conversation session"""
    if not session_service:
        raise HTTPException(status_code=503, detail="Session service not initialized")

    session_service.clear_session(session_id)
    return {"status": "cleared", "session_id": session_id}


# ==================== HSIL ENDPOINTS ====================

@app.post("/hsil/events")
async def hsil_process_event(event: dict):
    """
    Process a sensor event through HSIL pipeline.

    Pipeline:
    1. Event ingestion (normalize, enrich with trends/anomalies)
    2. Feature extraction (extract high-level features)
    3. Adaptive learning (update baselines, learn patterns)
    4. Behavior predictions
    5. Policy decisions
    6. Action dispatch
    """
    if not hsil_service:
        raise HTTPException(status_code=503, detail="HSIL not initialized")

    try:
        result = await hsil_service.process_event(
            device_id=event.get("device_id"),
            sensor_id=event.get("sensor_id", event.get("device_id")),
            event_type=event.get("event_type", "unknown"),
            value=event.get("value"),
            location=event.get("location", "Unknown"),
            device_type=event.get("device_type", "unknown"),
            metadata=event.get("metadata")
        )
        return result
    except Exception as e:
        logger.error(f"HSIL event processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/hsil/events")
async def hsil_events(request: Request):
    """
    Server-Sent Events (SSE) stream for real-time incident notifications.
    
    Clients connect to this endpoint to receive push notifications when
    incidents occur. This enables the chat UI to display alerts in real-time.
    
    Example usage:
    ```javascript
    const eventSource = new EventSource('/hsil/events');
    eventSource.addEventListener('incident_alert', (event) => {
        const data = JSON.parse(event.data);
        console.log('New incident:', data.message);
    });
    ```
    """
    sse_service = get_sse_service()
    return await sse_service.subscribe(request)


@app.post("/hsil/chat")
async def hsil_chat(request: dict):
    """
    Conversational interface to HSIL.

    Integrates:
    - Learned preferences
    - Current home state
    - Memory/history
    - Policy engine for actions
    - Conditional RAG for troubleshooting intents
    """
    if not hsil_service:
        raise HTTPException(status_code=503, detail="HSIL not initialized")

    try:
        response = await hsil_service.chat(
            message=request.get("message"),
            session_id=request.get("session_id")
        )
        # Return dict for JSON serialization
        result = {
            "reply": response.reply,
            "action": response.action.model_dump() if response.action else None
        }
        
        # Include clarification if present
        if response.clarification:
            result["clarification"] = response.clarification
            
        return result
    except Exception as e:
        logger.error(f"HSIL chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/hsil/feedback")
async def hsil_feedback(feedback: dict):
    """
    Record user feedback on HSIL responses.

    This is how the system learns from user interactions.
    """
    if not hsil_service:
        raise HTTPException(status_code=503, detail="HSIL not initialized")

    try:
        await hsil_service.provide_feedback(
            interaction_id=feedback.get("interaction_id"),
            feedback_type=feedback.get("feedback_type"),
            rating=feedback.get("rating"),
            correction=feedback.get("correction")
        )
        return {"status": "recorded"}
    except Exception as e:
        logger.error(f"HSIL feedback error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/hsil/state")
async def hsil_get_state():
    """
    Get current home state with HSIL enrichment.

    Returns all devices with:
    - Current values
    - Learned baselines
    - Anomaly detection
    - Predictions
    """
    if not hsil_service:
        raise HTTPException(status_code=503, detail="HSIL not initialized")

    try:
        state = await hsil_service.get_home_state()
        return state.model_dump(mode='json')
    except Exception as e:
        logger.error(f"HSIL state error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/hsil/stats")
async def hsil_get_stats():
    """Get HSIL statistics and learning metrics"""
    if not hsil_service:
        raise HTTPException(status_code=503, detail="HSIL not initialized")

    try:
        stats = await hsil_service.get_stats()
        return stats
    except Exception as e:
        logger.error(f"HSIL stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/hsil/preferences")
async def hsil_get_preferences():
    """Get all learned preferences"""
    if not hsil_service:
        raise HTTPException(status_code=503, detail="HSIL not initialized")

    try:
        prefs = await hsil_service.get_learned_preferences()
        return prefs
    except Exception as e:
        logger.error(f"HSIL preferences error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/hsil/erratic")
async def hsil_get_erratic_devices():
    """
    Get devices exhibiting erratic behavior patterns.
    
    Returns ML-learned statistics about event frequency anomalies,
    indicating possible sensor malfunctions or environmental interference.
    """
    if not hsil_service:
        raise HTTPException(status_code=503, detail="HSIL not initialized")

    try:
        erratic_devices = await hsil_service.learning.get_all_erratic_devices()
        return {
            "erratic_devices": erratic_devices,
            "count": len(erratic_devices),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"HSIL erratic devices error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/hsil/erratic/{device_id}")
async def hsil_get_device_erratic_stats(device_id: str):
    """
    Get erratic behavior statistics for a specific device.

    Returns ML-learned event frequency patterns and erratic score.
    """
    if not hsil_service:
        raise HTTPException(status_code=503, detail="HSIL not initialized")

    try:
        stats = await hsil_service.learning.get_device_erratic_stats(device_id)
        if stats is None:
            raise HTTPException(status_code=404, detail=f"No data for device {device_id}")
        return stats
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"HSIL device erratic stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/hsil/model-health")
async def hsil_get_model_health():
    """
    Get detailed model health and maturity metrics.

    Returns:
    - Model maturity status (immature/developing/mature)
    - Confidence scores for each model
    - Learning velocity metrics
    - Feedback loop statistics
    """
    if not hsil_service:
        raise HTTPException(status_code=503, detail="HSIL not initialized")

    try:
        health = await hsil_service.get_model_health()
        return health
    except Exception as e:
        logger.error(f"HSIL model health error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/hsil/device-health")
async def hsil_get_device_health():
    """
    Get per-device health metrics.

    Returns:
    - Anomaly scores for each device
    - Baseline statistics (mean, variance, std deviation)
    - Erratic behavior scores with time-based decay
    - Recent event counts
    """
    if not hsil_service:
        raise HTTPException(status_code=503, detail="HSIL not initialized")

    try:
        health = await hsil_service.get_device_health()
        return health
    except Exception as e:
        logger.error(f"HSIL device health error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/hsil/climate-insights")
async def hsil_get_climate_insights():
    """
    Get AI-powered climate insights based on ML learnings, weather, and home state.

    Returns:
    - LLM-generated insights using ML data
    - Weather correlation insights
    - Comfort recommendations based on learned preferences
    - Equipment health status
    """
    if not hsil_service:
        raise HTTPException(status_code=503, detail="HSIL not initialized")

    try:
        insights = await hsil_service.get_climate_insights()
        return insights
    except Exception as e:
        logger.error(f"HSIL climate insights error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
