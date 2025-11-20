"""
HomeSight AI Sidecar Service

This Python service handles all LLM inference and RAG operations for HomeSight.
It provides a REST API for chat, metric analysis, and incident explanation.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import uvicorn
import logging
import os
import yaml
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="HomeSight AI Service")

# Add CORS middleware to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances (lazy loaded)
llm = None
rag_engine = None
document_fetcher = None

# Load config to get OpenAI API key
def load_config():
    """Load configuration from config.yaml"""
    config_path = os.getenv("HOMESIGHT_CONFIG", "config.yaml")

    # Try multiple locations
    possible_paths = [
        Path(config_path) if os.path.isabs(config_path) else None,
        Path(__file__).parent.parent / config_path,
        Path.cwd() / config_path,
        Path.cwd().parent / config_path,
    ]

    config_file = None
    for path in possible_paths:
        if path and path.exists():
            config_file = path
            break

    if not config_file:
        logger.warning(f"Config file not found. Tried: {[str(p) for p in possible_paths if p]}")
        return {}

    logger.info(f"Loading config from: {config_file}")
    try:
        with open(config_file, 'r') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {}

config = load_config()


class ChatRequest(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    response: str


class AnalyzeRequest(BaseModel):
    type: str  # "metrics" or "incident"
    data: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None


class AnalyzeResponse(BaseModel):
    analysis: str
    insights: List[str]
    actions: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


def initialize_llm():
    """Initialize the OpenAI client (lazy loading)"""
    global llm

    if llm is not None:
        return llm

    try:
        from openai import OpenAI

        api_key = config.get("ai", {}).get("openai_api_key")
        if not api_key:
            logger.warning("No OpenAI API key found in config")
            return None

        llm = OpenAI(api_key=api_key)
        logger.info("OpenAI client initialized successfully")
        return llm

    except ImportError:
        logger.error("openai package not installed")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI client: {e}")
        return None


def initialize_rag():
    """Initialize RAG engine with home maintenance knowledge"""
    global rag_engine
    
    if rag_engine is not None:
        return rag_engine
    
    try:
        from rag_engine import RAGEngine
        
        # OpenAI key is optional now - only needed for LLM-powered document finding
        # Embeddings use local FastEmbed model (fully offline)
        openai_api_key = os.getenv("OPENAI_API_KEY") or config.get("ai", {}).get("openai_api_key")
        
        # Initialize RAG engine with persistent storage
        # Try system path first, fall back to local for development
        rag_path = Path("/var/lib/homesight/rag")
        try:
            rag_path.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            logger.warning("Permission denied for /var/lib/homesight, using local directory")
            rag_path = Path(__file__).parent.parent / "data" / "rag"
            rag_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initializing RAG engine at {rag_path}")
        rag_engine = RAGEngine(
            persist_directory=str(rag_path),
            openai_api_key=openai_api_key  # Optional - only for doc finding
        )
        
        # Check if we have documents indexed
        stats = rag_engine.get_stats()
        if stats["total_documents"] == 0:
            logger.warning("No documents in RAG database yet. Run ingest-docs.py to add manufacturer documentation.")
        else:
            logger.info(f"RAG engine loaded with {stats['total_documents']} documents")
        
        return rag_engine
        
    except ImportError as e:
        logger.warning(f"RAG dependencies not installed: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize RAG: {e}")
        return None


def generate_response(prompt: str, system_prompt: str = None) -> str:
    """Generate a response using OpenAI"""
    llm_instance = initialize_llm()

    if llm_instance is None:
        return "AI service is not configured. Please check your OpenAI API key in config.yaml."

    try:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = llm_instance.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=512,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI API call failed: {e}")
        return f"I apologize, but I'm having trouble generating a response: {str(e)}"


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    rag_stats = {}
    if rag_engine is not None:
        try:
            rag_stats = rag_engine.get_stats()
        except:
            pass
    
    return {
        "status": "healthy",
        "llm_loaded": llm is not None,
        "rag_loaded": rag_engine is not None,
        "rag_documents": rag_stats.get("total_documents", 0)
    }


@app.get("/rag/status")
async def rag_status():
    """Get RAG engine status and statistics"""
    rag_instance = initialize_rag()
    
    if rag_instance is None:
        return {
            "enabled": False,
            "message": "RAG engine not initialized"
        }
    
    try:
        stats = rag_instance.get_stats()
        return {
            "enabled": True,
            "stats": stats,
            "message": "RAG engine operational" if stats["total_documents"] > 0 else "No documents indexed yet"
        }
    except Exception as e:
        return {
            "enabled": False,
            "error": str(e)
        }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Chat endpoint for conversational AI with RAG enhancement"""
    try:
        # Build system prompt
        system_prompt = "You are a helpful home maintenance assistant for HomeSight, a home monitoring system. Provide clear, actionable advice for homeowners dealing with device issues and incidents."

        # Build user message with context
        user_message = request.message
        if request.context:
            user_message = f"Context: {request.context}\n\nQuestion: {request.message}"

        # Try to enhance with RAG if relevant
        rag_context = ""
        rag_instance = initialize_rag()
        if rag_instance is not None:
            try:
                results = rag_instance.query(request.message, n_results=2)
                if results and len(results) > 0:
                    rag_context = "\n\nRelevant documentation:\n"
                    for result in results:
                        if result.get("relevance_score", 0) > 0.3:
                            source = result.get("metadata", {}).get("source", "Unknown")
                            text = result.get("text", "")[:300]
                            rag_context += f"\n- {source}: {text}\n"
            except Exception as e:
                logger.error(f"RAG enhancement failed for chat: {e}")

        full_message = user_message + rag_context
        response_text = generate_response(full_message, system_prompt)
        return ChatResponse(response=response_text)
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    """Analyze metrics or incidents"""
    try:
        if request.type == "metrics":
            return analyze_metrics(request.data, request.context)
        elif request.type == "incident":
            return analyze_incident(request.data, request.context)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown analysis type: {request.type}")
            
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def analyze_metrics(data: Dict[str, Any], context: Optional[Dict[str, Any]]) -> AnalyzeResponse:
    """Analyze sensor metrics for anomalies"""
    sensor_id = data.get("sensor_id", "unknown")
    values = data.get("values", [])
    
    # Simple anomaly detection (in production, use more sophisticated methods)
    insights = []
    actions = []
    
    if len(values) > 0:
        avg = sum(values) / len(values)
        max_val = max(values)
        min_val = min(values)
        
        if max_val > avg * 1.5:
            insights.append(f"Detected spike in readings (max: {max_val:.2f}, avg: {avg:.2f})")
            actions.append("Investigate sensor for potential issues")
        
        if min_val < avg * 0.5:
            insights.append(f"Detected drop in readings (min: {min_val:.2f}, avg: {avg:.2f})")
    
    analysis = f"Analyzed {len(values)} readings from sensor {sensor_id}."
    
    if not insights:
        insights.append("Readings appear normal, no anomalies detected")
    
    return AnalyzeResponse(
        analysis=analysis,
        insights=insights,
        actions=actions if actions else None,
        metadata={"sensor_id": sensor_id, "samples": len(values)}
    )


def analyze_incident(data: Dict[str, Any], context: Optional[Dict[str, Any]]) -> AnalyzeResponse:
    """Analyze an incident and provide recommendations using RAG + LLM"""
    incident_type = data.get("type", "unknown")
    severity = data.get("severity", "unknown")
    incident_id = data.get("id", "unknown")
    device_id = data.get("device_id", None)
    
    insights = []
    actions = []
    rag_sources = []
    
    # Try to use RAG for enhanced analysis
    rag_instance = initialize_rag()
    if rag_instance is not None:
        try:
            # Build a better query based on incident type
            query_terms = [incident_type]
            
            # Add context-specific terms
            if "leak" in incident_type.lower():
                query_terms.append("water emergency plumbing")
            elif "freeze" in incident_type.lower():
                query_terms.append("pipe freeze winterization")
            elif "heater" in incident_type.lower() or "water heater" in incident_type.lower():
                query_terms.append("water heater maintenance T&P valve")
            elif "sump" in incident_type.lower():
                query_terms.append("sump pump drainage")
            elif "battery" in incident_type.lower() and device_id:
                query_terms.append("device battery replacement maintenance")
            
            query = " ".join(query_terms)
            
            logger.info(f"Querying RAG for incident: {query}")
            results = rag_instance.query(query, n_results=3)
            
            # Extract relevant information from RAG results
            if results and len(results) > 0:
                for result in results:
                    relevance = result.get("relevance_score", 0.0)
                    if relevance > 0.2:  # Lower threshold for more results
                        source = result.get("metadata", {}).get("source", "Unknown")
                        content = result.get("text", "")
                        rag_sources.append({
                            "source": source,
                            "relevance": relevance,
                            "excerpt": content[:200]
                        })
                        logger.info(f"Found relevant doc: {source} (relevance: {relevance:.3f})")
                    else:
                        logger.info(f"Skipping doc with low relevance: {result.get('metadata', {}).get('source', 'Unknown')} ({relevance:.3f})")
        except Exception as e:
            logger.error(f"RAG query failed: {e}")
    
    # Rule-based insights with RAG enhancement
    if "leak" in incident_type.lower():
        insights.append("Water leak detected - potential for property damage")
        actions.append("Locate and shut off water source immediately")
        actions.append("Check for visible damage and call plumber if needed")
        actions.append("Document damage for insurance purposes")
        
        # Add RAG-sourced insights if available
        if rag_sources:
            insights.append(f"Found {len(rag_sources)} relevant maintenance guides")
            for src in rag_sources[:2]:  # Top 2 sources
                insights.append(f"📖 {src['source']}: {src['excerpt'][:100]}...")
    
    elif "freeze" in incident_type.lower():
        insights.append("Freeze risk detected - pipes may be at risk")
        actions.append("Increase heating in affected area")
        actions.append("Open cabinet doors to allow warm air circulation")
        actions.append("Consider pipe insulation for long-term prevention")
        
        if rag_sources:
            insights.append(f"Found {len(rag_sources)} relevant winterization guides")
            for src in rag_sources[:2]:
                insights.append(f"📖 {src['source']}: {src['excerpt'][:100]}...")
    
    elif "sump" in incident_type.lower():
        insights.append("Excessive sump pump activity - possible drainage issue")
        actions.append("Check for heavy rain or snow melt")
        actions.append("Inspect sump pump for proper operation")
        actions.append("Consider backup sump pump if not present")
        
        if rag_sources:
            for src in rag_sources[:1]:
                insights.append(f"📖 {src['source']}: {src['excerpt'][:100]}...")
    
    elif "battery" in incident_type.lower():
        insights.append("Device battery running low")
        actions.append("Replace batteries soon to maintain monitoring")
    
    else:
        insights.append(f"Incident of type '{incident_type}' with severity '{severity}'")
        actions.append("Review incident details and take appropriate action")
        
        if rag_sources:
            insights.append(f"Found {len(rag_sources)} relevant documents")
            for src in rag_sources[:2]:
                insights.append(f"📖 {src['source']}")
    
    analysis = f"Incident Analysis: {incident_type} (Severity: {severity})"
    if rag_sources:
        analysis += f" [Enhanced with {len(rag_sources)} document(s)]"
    
    metadata = {
        "type": incident_type,
        "severity": severity,
        "incident_id": incident_id
    }
    
    if rag_sources:
        metadata["rag_sources"] = [
            {"source": src["source"], "relevance": src["relevance"]}
            for src in rag_sources
        ]
    
    return AnalyzeResponse(
        analysis=analysis,
        insights=insights,
        actions=actions,
        metadata=metadata
    )


@app.post("/events/device")
async def handle_device_event(event: dict, background_tasks: BackgroundTasks):
    """
    Handle device lifecycle events from HomeSight daemon
    
    Automatically fetches and ingests documentation when new devices are discovered.
    Zero configuration required!
    """
    event_type = event.get("type", "")
    
    if event_type == "device.created":
        device_data = event.get("data", {})
        manufacturer = device_data.get("manufacturer", "")
        model = device_data.get("model", "")
        
        if manufacturer and model:
            logger.info(f"Device created: {manufacturer} {model} - queuing doc fetch")
            
            # Queue document fetch in background (don't block response)
            background_tasks.add_task(fetch_device_docs, device_data)
            
            return {
                "status": "queued",
                "message": f"Queued doc fetch for {manufacturer} {model}"
            }
        else:
            return {
                "status": "skipped",
                "message": "Device missing manufacturer or model metadata"
            }
    
    return {"status": "ignored", "message": f"Unknown event type: {event_type}"}


async def fetch_device_docs(device: dict):
    """Background task to fetch and ingest device documentation"""
    try:
        fetcher = get_document_fetcher()
        if fetcher:
            success = await fetcher.fetch_for_device(device)
            if success:
                logger.info(f"Successfully fetched docs for {device.get('manufacturer')} {device.get('model')}")
            else:
                logger.warning(f"Could not fetch docs for {device.get('manufacturer')} {device.get('model')}")
    except Exception as e:
        logger.error(f"Error fetching docs: {e}")


def get_document_fetcher():
    """Initialize document fetcher (lazy load)"""
    global document_fetcher, rag_engine
    
    if document_fetcher is not None:
        return document_fetcher
    
    # Need RAG engine first
    rag_instance = initialize_rag()
    if rag_instance is None:
        return None
    
    try:
        from document_fetcher import DocumentAutoFetcher
        
        # Get OpenAI key for LLM-powered document finding
        openai_api_key = os.getenv("OPENAI_API_KEY") or config.get("ai", {}).get("openai_api_key")
        
        cache_dir = Path.home() / ".homesight" / "manuals"
        document_fetcher = DocumentAutoFetcher(
            rag_instance,
            cache_dir,
            openai_api_key=openai_api_key
        )
        
        if openai_api_key:
            logger.info(f"Document auto-fetcher initialized with LLM support (cache: {cache_dir})")
        else:
            logger.info(f"Document auto-fetcher initialized (template mode, cache: {cache_dir})")
        
        return document_fetcher
    except ImportError as e:
        logger.warning(f"Could not initialize document fetcher: {e}")
        return None


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("Starting HomeSight AI Service")
    # Lazy load LLM and RAG on first request to speed up startup


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down HomeSight AI Service")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        log_level="info"
    )
