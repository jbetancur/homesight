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
import uvicorn
import logging
from pathlib import Path
from contextlib import asynccontextmanager

# Configuration
from config import get_config

# Metrics
from metrics import get_metrics, active_sessions

# Models
from models.chat import ChatRequest, ChatResponse
from models.analyze import AnalyzeRequest, AnalyzeResponse
from models.device import DeviceEvent

# Services
from services.session_service import SessionService
from services.chat_service import ChatService
from services.analysis_service import AnalysisService
from services.document_service import DocumentService

# LLM and RAG
from llm.provider import HybridLLMProvider, _init_executor
from rag.engine import RAGEngine

# Queue management
from analysis_queue import AnalysisQueue

# Configure logging to both console and file
log_dir = Path('/app/log')
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

        # Initialize ThreadPoolExecutor with configured worker count
        _init_executor(max_workers=config.llm.inference.max_worker_threads)

        # Initialize LLM provider
        logger.info("Initializing hybrid LLM provider...")
        llm_provider = HybridLLMProvider(config.llm)

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

        # Initialize analysis queue with configured concurrency limit
        analysis_queue = AnalysisQueue(max_concurrent=config.llm.inference.max_concurrent_tasks)
        logger.info("✅ All services initialized")
        logger.info(f"Analysis queue: max_concurrent={config.llm.inference.max_concurrent_tasks}, "
                    f"max_worker_threads={config.llm.inference.max_worker_threads}")

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
    if not chat_service:
        raise HTTPException(status_code=503, detail="Chat service not initialized")

    try:
        response = await chat_service.chat(request)
        logger.info(f"Chat response - session_id: {response.session_id}, actions: {response.actions_taken}")
        return response
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        manufacturer = device_data.get("manufacturer", "")
        model = device_data.get("model", "")

        if manufacturer and model:
            logger.info(f"Device created: {manufacturer} {model} - queuing comprehensive doc discovery")

            # Queue document discovery in background
            background_tasks.add_task(discover_device_docs, device_data)

            return {
                "status": "queued",
                "message": f"Comprehensive doc discovery queued for {manufacturer} {model}"
            }
        else:
            return {
                "status": "skipped",
                "message": "Device missing manufacturer or model metadata"
            }

    return {"status": "ignored", "message": f"Unknown event type: {event_type}"}


async def discover_device_docs(device: dict):
    """Background task for comprehensive document discovery"""
    try:
        device_id = device.get("id")
        logger.info(f"Starting document discovery for device: {device_id}")

        if document_service:
            result = await document_service.discover_and_ingest_device_docs(device)
            logger.info(f"Doc discovery complete: {result}")

            # Update device documentation status in Go backend
            if device_id:
                logger.info(f"Updating device {device_id} docs status in Go backend...")
                await update_device_docs_status(device_id, result)
                logger.info(f"Successfully updated device {device_id} docs status")
            else:
                logger.warning("Device ID not found in discovery result")
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
