# HomeSight AI Sidecar

Optional Python service for AI-powered incident analysis.

## What It Does

- Analyzes incidents and suggests actions
- Provides conversational interface for home maintenance questions
- Runs completely local (no cloud dependencies)

## Setup

```bash
cd ai-sidecar
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
# Start the service
python main.py
```

Service runs on `http://localhost:8001`

## Endpoints

### Health Check
```bash
curl http://localhost:8001/health
```

### Chat
```bash
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How do I prevent frozen pipes?"}'
```

### Analyze Incident
```bash
curl -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "type": "incident",
    "data": {
      "type": "leak_detected",
      "severity": "critical"
    }
  }'
```

## LLM Support

The service works with or without a local LLM:

**With LLM**: Place a GGUF model file in `/var/lib/homesight/models/`
**Without LLM**: Falls back to rule-based responses

## Requirements

- Python 3.10+
- FastAPI
- (Optional) llama-cpp-python for LLM support

## Dependencies

See `requirements.txt` for full list.
