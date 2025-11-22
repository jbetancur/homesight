# HomeSight AI Sidecar

Optional Python service for RAG-powered incident analysis and chat.

## Quick Start

```bash
cd ai-sidecar
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

Service runs on `http://localhost:8001`

## How It Works

1. **Incident Analysis**: Main daemon sends incidents → AI service provides recommendations
2. **Document Fetching**: When devices are onboarded, OpenAI finds and caches manufacturer docs
3. **RAG Indexing**: PDFs embedded into ChromaDB vector database
4. **Semantic Search**: Incidents query vector DB for relevant docs → LLM generates recommendations

**Cloud**: Only used for doc discovery (OpenAI API)
**Local**: All embeddings, indexing, and analysis happen locally

## Endpoints

```bash
# Health check
curl http://localhost:8001/health

# RAG status (docs indexed)
curl http://localhost:8001/rag/status

# Chat
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How do I prevent frozen pipes?"}'

# Analyze incident
curl -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{"type": "leak_detected", "severity": "critical"}'
```

## Architecture

```mermaid
graph TB
    DAEMON["HomeSight Daemon :8080<br/>Device Onboarded Event"]

    subgraph "AI Sidecar :8001"
        API["FastAPI Server"]
        SESSION["Session Service"]
        CHAT["Chat Service"]
        ANALYSIS["Analysis Service"]
        DOC["Document Service"]
    end

    subgraph "Local Processing"
        RAG["RAG Engine"]
        EMBED["FastEmbed<br/>Embeddings"]
        CHROMADB["ChromaDB<br/>Vector DB"]
        QUEUE["Analysis Queue"]
    end

    subgraph "Cloud Setup Only"
        OPENAI["OpenAI API<br/>Doc Discovery"]
    end

    %% API flows
    DAEMON -->|Incident| API
    API --> SESSION
    API --> CHAT
    API --> ANALYSIS

    %% Internal flows
    CHAT --> ANALYSIS
    ANALYSIS --> QUEUE
    QUEUE --> RAG
    RAG --> EMBED
    EMBED --> CHROMADB

    %% Doc fetching
    DAEMON -->|Device onboarded| DOC
    DOC -.->|Find docs| OPENAI
    DOC -->|Cache + Index| RAG

    %% Styling
    classDef daemon fill:#4a9eff,stroke:#2d5f9f,stroke-width:2px,color:#fff
    classDef service fill:#ff9800,stroke:#e65100,stroke-width:2px,color:#fff
    classDef local fill:#66bb6a,stroke:#388e3c,stroke-width:2px,color:#fff
    classDef cloud fill:#03a9f4,stroke:#0277bd,stroke-width:2px,stroke-dasharray:5,5,color:#fff

    class DAEMON daemon
    class API,SESSION,CHAT,ANALYSIS,DOC service
    class RAG,EMBED,CHROMADB,QUEUE local
    class OPENAI cloud
```

## Configuration

See `config.py` for:

- OpenAI API key (for doc discovery)
- ChromaDB path
- Model selection
- RAG parameters

## Requirements

- Python 3.10+
- FastAPI, ChromaDB, FastEmbed
- (Optional) OpenAI API key for doc discovery
- (Optional) llama-cpp-python for local LLM
