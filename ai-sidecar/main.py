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
import uvicorn
import logging
from pathlib import Path
from contextlib import asynccontextmanager

# Configuration
from config import get_config

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
from llm.provider import HybridLLMProvider
from rag.engine import RAGEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global service instances (initialized on startup)
llm_provider = None
rag_engine = None
session_service = None
chat_service = None
analysis_service = None
document_service = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("🚀 Starting HomeSight AI Service")

    # Initialize services
    global llm_provider, rag_engine, session_service, chat_service, analysis_service, document_service

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

        logger.info("✅ All services initialized")

    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise

    yield

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
    """Health check endpoint (lightweight, non-blocking)"""
    # Don't call potentially blocking operations during health checks
    # Just return basic availability status
    return {
        "status": "healthy",
        "llm": {
            "available": llm_provider is not None and llm_provider.is_available()
        } if llm_provider else {"available": False},
        "rag": {
            "available": rag_engine is not None,
            "documents": getattr(rag_engine, '_cached_count', 0) if rag_engine else 0
        },
        "sessions": {
            "active": len(session_service._sessions) if session_service else 0
        }
    }


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
    """
    if not analysis_service:
        raise HTTPException(status_code=503, detail="Analysis service not initialized")

    try:
        response = await analysis_service.analyze(request)
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
        if document_service:
            result = await document_service.discover_and_ingest_device_docs(device)
            logger.info(f"Doc discovery complete: {result}")
        else:
            logger.warning("Document service not available")
    except Exception as e:
        logger.error(f"Error in document discovery: {e}")


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
