"""
HomeSight AI Sidecar Service

This Python service handles all LLM inference and RAG operations for HomeSight.
It provides a REST API for chat, metric analysis, and incident explanation.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import uvicorn
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="HomeSight AI Service")

# Global LLM instance (lazy loaded)
llm = None
rag_engine = None


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
    """Initialize the LLM model (lazy loading)"""
    global llm
    
    if llm is not None:
        return llm
    
    try:
        from llama_cpp import Llama
        
        # Look for model in common locations
        model_paths = [
            "/var/lib/homesight/models/llama-2-7b-chat.gguf",
            "./models/llama-2-7b-chat.gguf",
            str(Path.home() / "models" / "llama-2-7b-chat.gguf"),
        ]
        
        model_path = None
        for path in model_paths:
            if Path(path).exists():
                model_path = path
                break
        
        if not model_path:
            logger.warning("No LLM model found, using mock responses")
            return None
        
        logger.info(f"Loading LLM model from {model_path}")
        llm = Llama(
            model_path=model_path,
            n_ctx=2048,
            n_threads=4,
            n_gpu_layers=0,  # Set > 0 if using GPU
        )
        logger.info("LLM model loaded successfully")
        return llm
        
    except ImportError:
        logger.warning("llama-cpp-python not installed, using mock responses")
        return None
    except Exception as e:
        logger.error(f"Failed to load LLM: {e}")
        return None


def initialize_rag():
    """Initialize RAG engine with home maintenance knowledge"""
    global rag_engine
    
    if rag_engine is not None:
        return rag_engine
    
    try:
        from langchain.vectorstores import FAISS
        from langchain.embeddings import HuggingFaceEmbeddings
        
        # Initialize embeddings
        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        
        # TODO: Load home maintenance documentation
        # For now, return None - will be implemented with actual docs
        logger.info("RAG engine initialized")
        rag_engine = {
            "embeddings": embeddings,
            "vectorstore": None
        }
        return rag_engine
        
    except ImportError:
        logger.warning("RAG dependencies not installed")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize RAG: {e}")
        return None


def generate_response(prompt: str) -> str:
    """Generate a response using LLM or mock"""
    llm_instance = initialize_llm()
    
    if llm_instance is None:
        # Mock response when LLM is not available
        return f"[Mock Response] I understand you're asking about: {prompt[:100]}. In a production environment, this would be answered by a local LLM."
    
    try:
        output = llm_instance(
            prompt,
            max_tokens=512,
            temperature=0.7,
            stop=["Human:", "\n\n"],
        )
        return output["choices"][0]["text"].strip()
    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        return "I apologize, but I'm having trouble generating a response right now."


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "llm_loaded": llm is not None,
        "rag_loaded": rag_engine is not None
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Chat endpoint for conversational AI"""
    try:
        # Build context-aware prompt
        context_str = ""
        if request.context:
            context_str = f"\nContext: {request.context}\n"
        
        prompt = f"""You are a helpful home maintenance assistant for HomeSight, a home monitoring system.

{context_str}
Human: {request.message}
Assistant: """
        
        response = generate_response(prompt)
        return ChatResponse(response=response)
        
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
    """Analyze an incident and provide recommendations"""
    incident_type = data.get("type", "unknown")
    severity = data.get("severity", "unknown")
    
    insights = []
    actions = []
    
    # Rule-based insights (in production, use LLM for more sophisticated analysis)
    if "leak" in incident_type.lower():
        insights.append("Water leak detected - potential for property damage")
        actions.append("Locate and shut off water source immediately")
        actions.append("Check for visible damage and call plumber if needed")
        actions.append("Document damage for insurance purposes")
    
    elif "freeze" in incident_type.lower():
        insights.append("Freeze risk detected - pipes may be at risk")
        actions.append("Increase heating in affected area")
        actions.append("Open cabinet doors to allow warm air circulation")
        actions.append("Consider pipe insulation for long-term prevention")
    
    elif "sump" in incident_type.lower():
        insights.append("Excessive sump pump activity - possible drainage issue")
        actions.append("Check for heavy rain or snow melt")
        actions.append("Inspect sump pump for proper operation")
        actions.append("Consider backup sump pump if not present")
    
    elif "battery" in incident_type.lower():
        insights.append("Device battery running low")
        actions.append("Replace batteries soon to maintain monitoring")
    
    else:
        insights.append(f"Incident of type '{incident_type}' with severity '{severity}'")
        actions.append("Review incident details and take appropriate action")
    
    analysis = f"Incident Analysis: {incident_type} (Severity: {severity})"
    
    return AnalyzeResponse(
        analysis=analysis,
        insights=insights,
        actions=actions,
        metadata={"type": incident_type, "severity": severity}
    )


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
