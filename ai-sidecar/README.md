# HomeSight AI Sidecar

Python-based AI service for HomeSight that handles all LLM inference and RAG operations.

## Features

- Local LLM inference using llama.cpp
- RAG (Retrieval-Augmented Generation) for home maintenance knowledge
- REST API for chat and analysis
- Metric anomaly detection
- Incident analysis and recommendations

## Installation

```bash
pip install -r requirements.txt
```

## Model Setup

Place your GGUF model file in one of these locations:
- `/var/lib/homesight/models/llama-2-7b-chat.gguf`
- `./models/llama-2-7b-chat.gguf`
- `~/models/llama-2-7b-chat.gguf`

Recommended models:
- Llama 2 7B Chat (GGUF format)
- Mistral 7B Instruct (GGUF format)

## Running

```bash
python main.py
```

The service will start on `http://localhost:8001`

## API Endpoints

### Health Check
```bash
GET /health
```

### Chat
```bash
POST /chat
{
  "message": "How do I winterize my pipes?",
  "context": {}
}
```

### Analyze
```bash
POST /analyze
{
  "type": "incident",
  "data": {
    "type": "leak_detected",
    "severity": "critical"
  }
}
```

## Configuration

Set environment variables:
- `AI_MODEL_PATH`: Path to LLM model file
- `AI_PORT`: Port to run service on (default: 8001)
