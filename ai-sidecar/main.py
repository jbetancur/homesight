"""
HomeSight AI Sidecar Service - Refactored

Clean, modular architecture with:
- Multi-turn conversational AI
- Function/tool calling
- Enhanced document discovery (manuals, forums, Reddit, etc.)
- AI-powered incident analysis (no hard-coded rules)
- Hybrid LLM support (OpenAI + local fallback)
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from typing import Optional
import uvicorn
import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager

# Configuration
from config import get_config

# Metrics
from metrics import get_metrics, active_sessions, chat_response_time, chat_requests

# Models
from models.chat import ChatRequest, ChatResponse
from models.analyze import AnalyzeRequest, AnalyzeResponse
from models.device import DeviceEvent
from models.device_profile import DeviceProfile

# Services
from services.session_service import SessionService
from services.chat_service import ChatService
from services.analysis_service import AnalysisService
from services.document_service import DocumentService

# LLM and RAG
from llm.provider import LLMProvider
from rag.engine import RAGEngine

# Queue management
from analysis_queue import AnalysisQueue
from task_queue import TaskQueue, QueueType, QueueConfig

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
chat_service = None
analysis_service = None
document_service = None
analysis_queue = None

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
    global llm_provider, rag_engine, session_service, chat_service, analysis_service, document_service, analysis_queue
    global discovery_queue, ingestion_queue, analysis_task_queue

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

        # Initialize services
        session_service = SessionService(session_timeout_minutes=60)
        chat_service = ChatService(
            llm_provider=llm_provider,
            session_service=session_service,
            rag_engine=rag_engine,
            backend_url=config.backend_url
        )
        analysis_service = AnalysisService(
            llm_provider=llm_provider,
            rag_engine=rag_engine
        )
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

        # Keep old analysis_queue for backward compatibility
        analysis_queue = AnalysisQueue(max_concurrent=config.llm.inference.max_concurrent_tasks)

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

    yield

    # Cancel background task on shutdown
    health_task.cancel()
    logger.info("Shutting down HomeSight AI Service")


# Create FastAPI app
app = FastAPI(
    title="HomeSight AI Service",
    description="Conversational AI with RAG and function calling",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware - restricted to Go API only
# Web UI now goes through Go API proxy (/api/ai/*)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",  # Go API server
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
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


# Chat endpoint with multi-turn conversation and function calling
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat with the AI assistant

    Supports:
    - Multi-turn conversations (pass session_id)
    - Function calling (device actions)
    - RAG-enhanced responses
    """
    import time
    start_time = time.time()
    status = "error"

    if not chat_service:
        raise HTTPException(status_code=503, detail="Chat service not initialized")

    try:
        response = await chat_service.chat(request)
        logger.info(f"Chat response - session_id: {response.session_id}, actions: {response.actions_taken}")
        status = "success"
        return response
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Track chat metrics
        duration = time.time() - start_time
        chat_response_time.observe(duration)
        chat_requests.labels(status=status).inc()


# Analysis endpoint (AI-powered, no hard-coded rules!)
@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    """
    Analyze metrics or incidents using AI

    Uses LLM + RAG instead of hard-coded rules
    Queued to prevent concurrent LLM inference from blocking other requests
    """
    if not analysis_service:
        raise HTTPException(status_code=503, detail="Analysis service not initialized")
    if not analysis_queue:
        raise HTTPException(status_code=503, detail="Analysis queue not initialized")

    try:
        # Queue the analysis task to limit concurrent LLM inference
        async def analyze_task():
            return await analysis_service.analyze(request)

        response = await analysis_queue.execute(analyze_task, task_id="analyze")
        return response
    except Exception as e:
        logger.error(f"Analysis error: {e}")
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
            "ingested_at": None  # Let the Go backend set the timestamp
        }

        url = f"{config.backend_url}/api/devices/{device_id}/docs-status"
        logger.info(f"Posting to {url} with payload: {update_payload}")

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
    Analyze incident in background and save results to Go backend database

    This allows the UI to retrieve pre-computed analysis instead of
    waiting for LLM inference when the user expands the incident.
    """
    import httpx
    import time

    incident_id = incident_data.get("id")

    if not incident_id or not analysis_service:
        return

    try:
        logger.info(f"Starting background analysis for incident {incident_id}")

        # Create analysis request
        request = AnalyzeRequest(
            type="incident",
            data={
                "id": incident_id,
                "type": incident_data.get("title", "Unknown incident"),
                "severity": incident_data.get("severity", "unknown"),
                "device_id": incident_data.get("device_id"),
                "description": incident_data.get("description", "")
            },
            context={
                "incident_id": incident_id,
                "device_id": incident_data.get("device_id")
            }
        )

        # Perform analysis
        result = await analysis_service.analyze(request)

        logger.info(f"✅ Completed analysis for incident {incident_id}")

        # Save analysis to Go backend database via HTTP PATCH
        try:
            go_backend_url = os.getenv("BACKEND_URL", "http://localhost:8080")
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.patch(
                    f"{go_backend_url}/api/incidents/{incident_id}/analysis",
                    json={
                        "analysis_status": "completed",
                        "analysis": result.analysis,
                        "insights": result.insights,
                        "actions": result.actions,
                        "analysis_data": result.metadata,
                    }
                )
            logger.info(f"✅ Saved analysis for incident {incident_id} to database")
        except Exception as db_err:
            logger.error(f"Failed to save analysis for incident {incident_id}: {db_err}")

    except Exception as e:
        logger.error(f"Background analysis failed for incident {incident_id}: {e}")

        # Save error status to Go backend database
        try:
            go_backend_url = os.getenv("BACKEND_URL", "http://localhost:8080")
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


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        log_level="info",
        reload=False
    )
