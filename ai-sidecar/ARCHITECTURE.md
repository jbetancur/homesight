# HomeSight AI Sidecar - Architecture Reference

## Overview

The AI Sidecar is a pragmatic, resource-aware knowledge base and conversational AI system built with honesty about cloud dependencies and privacy trade-offs.

**Core Philosophy:**

- **Honest about dependencies**: Clear when data goes to cloud (OpenAI) vs stays local
- **Resource-aware**: Queuing and throttling prevent system saturation
- **Knowledge-grounded**: AI-generated content grounded in official documentation where possible
- **User choice**: Explicit control over chat mode (cloud quality vs local privacy)

---

## System Architecture

### High-Level Components

```
User Chat / Technician App
        ↓
FastAPI REST API (main.py)
        ↓
┌─────────────────────────────────────────────────────┐
│                Chat Service                         │
│  - Multi-turn conversation (cloud or local LLM)    │
│  - RAG context injection                           │
│  - Function calling (cloud mode only)              │
└─────────────────────────────────────────────────────┘
        ↓
┌──────────────┬──────────────────────┬──────────────┐
│              │                      │              │
↓              ↓                      ↓              ↓
LLM Provider  RAG Engine          Analysis      Document
(Router)      (ChromaDB)          Service       Service
│              │                      │              │
├─ Local:    │  Vector DB          │              │
│  Llama 3.2 │  + Metadata         │  Queued     │  Queued
│            │                      │  OpenAI     │  PDF fetch
├─ Cloud:    │                      │  Analysis   │  + OpenAI
│  OpenAI    │                      │             │  Generation
└─────────────┘                      └─────────────┘
```

### Configuration-Driven Routing

**Chat Mode** (user-facing, configurable):

```yaml
chat_mode: "cloud"    # Options: "cloud" or "local"
```

- **`cloud`**: Uses OpenAI gpt-4o-mini
  - ✅ Function calling support
  - ✅ Multi-turn conversation
  - ✅ High quality responses
  - ❌ Data sent to OpenAI servers

- **`local`**: Uses local Llama 3.2
  - ✅ 100% private (no external calls)
  - ✅ Offline capable
  - ❌ Limited quality
  - ❌ No function calling

**Background Operations** (always use OpenAI for quality):

- Knowledge generation (grounded in PDFs)
- Incident analysis
- Search result ranking

---

## Knowledge Generation Pipeline

### 1. Device Onboarding

When a device is added:

```
Device Event → Discovery Queue → PDF Fetcher (best effort)
                                       ↓
                            Try official manual
                                       ↓
                        PDF found? ────┬──→ PDF found
                                       │
                                No PDF ↓

Document Service ← Optional PDF text (for grounding)
         ↓
OpenAI generates structured knowledge:
  - Specifications
  - Setup procedure
  - Common issues & solutions
  - Maintenance
  - Warranty & support
         ↓
Knowledge Validator (checks citations, marks confidence)
         ↓
Ingestion Queue → ChromaDB (with metadata)
         ↓
RAG Ready (semantic search enabled)
```

### 2. Source Grounding

**Strategy**: Grounding prevents hallucination

| Scenario | Source | Confidence | Notes |
|----------|--------|-----------|-------|
| PDF found + OpenAI grounds | Official PDF + OpenAI synthesis | 0.90-0.95 | Best case: factual + enhanced |
| No PDF, OpenAI uses training data | OpenAI training data only | 0.60-0.70 | Unverified: labeled clearly |
| New device (post-cutoff) | OpenAI synthesis only | 0.40-0.60 | High hallucination risk |

### 3. Confidence Scoring

Each knowledge entry includes:

```python
{
  "manufacturer": "Aqara",
  "model": "SJCGQ11LM",
  "content": "...",
  "confidence": 0.90,
  "grounding_sources": ["official_pdf"],
  "generated_at": "2025-11-23T...",
  "grounded_in_pdf": True
}
```

---

## Task Queue System

### Problem: Resource Saturation

Without queuing:

- 50 devices onboarded → 50 PDF fetches (network/disk spike)
- 100 embeddings generated → CPU 100% (other requests blocked)
- 10 incident analyses → OpenAI API overwhelmed

### Solution: Adaptive Queuing with Resource Awareness

Three queue types, each with independent configuration:

```yaml
queues:
  discovery:          # PDF fetching
    max_concurrent: 2
    cpu_threshold: 0.80

  ingestion:          # Embedding generation
    max_concurrent: 2
    memory_threshold: 0.80

  analysis:           # OpenAI API calls
    max_concurrent: 4
    cpu_threshold: 0.90
```

### Backpressure Mechanism

```
New Task Arrives
        ↓
Check queue depth:
  If queue_size >= max_queue_depth → Reject (backpressure)
        ↓
Check system resources:
  If CPU > cpu_threshold → Throttle (wait for resources)
  If Memory > memory_threshold → Throttle
        ↓
Acquire semaphore (max_concurrent limit)
        ↓
Execute task
        ↓
Release semaphore
```

---

## Chat Service: Cloud vs Local

### Cloud Mode (Default)

```python
# config.yaml
chat_mode: "cloud"

# Flow:
User Query
    ↓
Semantic Search (RAG)
    ↓
Build system prompt with:
  - Device KB entry
  - Retrieved document snippets
  - Sources cited
    ↓
OpenAI gpt-4o-mini (with context)
    ↓
Response + Tool Calls
    ↓
Execute Tools (Go API)
    ↓
User + Sources
```

**Pros**: Quality, function calling, multi-turn
**Cons**: Data to OpenAI servers

### Local Mode

```python
# config.yaml
chat_mode: "local"

# Flow:
User Query
    ↓
Semantic Search (RAG)
    ↓
Build system prompt with:
  - Device KB entry
  - Retrieved document snippets
    ↓
Local Llama 3.2 (no external calls)
    ↓
Response (text only, no tools)
    ↓
User + Sources
```

**Pros**: 100% private, offline
**Cons**: Limited quality, no function calling

---

## Incident Analysis Integration

### Analysis with Knowledge Grounding

```
Incident Detected
    ↓
Analysis Queue (limited concurrency)
    ↓
Get Device KB from RAG
    ↓
OpenAI Analyzes:
  Input: {
    incident_data,
    device_specs,
    common_issues_from_kb,
    troubleshooting_steps
  }
    ↓
Output: {
  analysis,
  root_cause,
  recommended_actions,
  sources_cited: [KB entries]
}
    ↓
Store Analysis
    ↓
Chat Service retrieves analysis
    ↓
User gets:
  - Problem explanation (from KB)
  - Recommended actions (grounded)
  - Troubleshooting steps
  - Source links
```

---

## LLM Provider: Explicit Routing

### Old Approach (Confusing)

```
chat(messages, tools=None) {
  if openai && tools → OpenAI with tools
  if openai && len(msgs) > 2 → OpenAI
  if openai fails && local → Local fallback
  if local fails → Error
}
```

Hidden routing, unclear to user, unpredictable.

### New Approach (Explicit)

```python
class LLMProvider:
    def __init__(self, config):
        self.chat_mode = config.chat_mode  # "cloud" or "local"

    def chat(self, messages, tools=None):
        if self.chat_mode == "cloud":
            return self._chat_cloud(messages, tools)
        elif self.chat_mode == "local":
            return self._chat_local(messages)
        else:
            raise ValueError("Invalid chat_mode")
```

Clear, predictable, auditable.

---

## Document Service: Clean Pipeline

### Simple, Straightforward Flow

```python
async def discover_and_ingest_device_docs(device):
    # 1. Try fetch official PDF (best effort, cached)
    pdf_text = await fetcher.fetch_for_device(device)

    # 2. Generate structured knowledge with OpenAI
    #    (grounded in PDF if available)
    knowledge = await openai.generate(
        device_info=device,
        grounding_text=pdf_text  # May be None
    )

    # 3. Ingest into RAG
    await rag.ingest(knowledge)

    return {"status": "success"}
```

**No scraping**: No Reddit, forums, YouTube integration
**No hallucination**: Grounded where possible, marked unverified otherwise

---

## Configuration Overview

### Chat Mode (User-Facing)

```yaml
llm:
  chat_mode: "cloud"  # or "local"
```

### Queue Configuration (Resource Management)

```yaml
queues:
  discovery:
    max_concurrent: 2
    max_queue_depth: 10
    cpu_threshold: 0.80
    memory_threshold: 0.85

  ingestion:
    max_concurrent: 2
    max_queue_depth: 5
    cpu_threshold: 0.85
    memory_threshold: 0.80

  analysis:
    max_concurrent: 4
    max_queue_depth: 20
    cpu_threshold: 0.90
    memory_threshold: 0.90
```

### Knowledge Generation (Always OpenAI)

```yaml
llm:
  openai:
    model: "gpt-4o-mini"
```

### Local LLM (Fallback/Optional)

```yaml
llm:
  local:
    model_path: "./models/llama-3.2-3b-instruct.gguf"
    auto_download: true
    n_ctx: 4096
    n_threads: 4
    n_gpu_layers: 0
```

---

## API Endpoints

### Chat (User-Facing)

```
POST /chat
{
  "message": "How do I reset this device?",
  "device_id": "sensor-001",
  "session_id": "sess-123"
}
→ ChatResponse {
  "message": "...",
  "session_id": "sess-123",
  "sources_cited": [{type, url, confidence}]
}
```

**Important**: Uses LLM in configured `chat_mode`

### Analyze (Incident Analysis)

```
POST /analyze
{
  "type": "incident",
  "data": {...incident data...}
}
→ AnalyzeResponse {
  "analysis": "...",
  "recommended_actions": [...],
  "sources_cited": [...]
}
```

**Always uses OpenAI** for quality

### Device Events (Auto-Ingestion)

```
POST /events/device
{
  "type": "device.created",
  "data": {
    "manufacturer": "Aqara",
    "model": "SJCGQ11LM"
  }
}
→ Queued for discovery + ingestion
```

---

## Monitoring & Metrics

### Queue Metrics

```
queue_depth{queue_type="discovery"} = 3
queue_wait_time{queue_type="ingestion"} = 2.5s
queue_rejected_total{queue_type="analysis", reason="cpu_throttle"} = 2
```

### Knowledge Metrics

```
kb_generations_total{status="success", grounded="true"} = 42
kb_generation_cost_usd = 1.23
kb_cache_hit_rate = 0.95
```

### Chat Metrics

```
chat_requests_total{mode="cloud", status="success"} = 1523
chat_response_time_seconds{mode="cloud"} = 1.2s
chat_sources_cited{source_type="pdf"} = 847
```

---

## Privacy & Data Flow

### What Stays Local

- Chat session history (user questions/answers)
- Device metadata
- Session management
- Vector embeddings (FastEmbed)
- ChromaDB storage

### What Goes to OpenAI

- **Only when chat_mode="cloud"**: User chat messages + KB context
- Knowledge generation (one-time per device)
- Incident analysis

### What Stays Private (Local Mode)

- All user interactions (chat_mode="local")
- All embeddings
- All knowledge base retrieval

---

## Design Patterns Used

1. **Strategy Pattern**: Document sources, LLM providers
2. **Pipeline Pattern**: Document discovery → generation → validation → ingestion
3. **Queue Pattern**: Task deferral with backpressure
4. **Dependency Injection**: All services receive dependencies
5. **Decorator Pattern**: Async methods wrapping sync operations

---

## Performance Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| Chat response (cloud) | <2s | Includes KB retrieval + OpenAI inference |
| Chat response (local) | <5s | LLM inference, no network |
| KB generation | <10s | PDF fetch (optional) + OpenAI + ingestion |
| Device ingestion | <30s | Complete discovery + generation + storage |
| RAG query | <100ms | Vector similarity search |
| Health check | <10ms | Cached, never blocks |

---

## Maintenance Notes

### Updating Knowledge Manually

If official documentation changes:

```bash
# Current: No automated refresh
# Planned: Weekly PDF staleness check via HTTP HEAD
```

### Tuning Resource Limits

If system experiences saturation:

```yaml
# Reduce concurrent tasks or queue depth
queues:
  ingestion:
    max_concurrent: 1      # Lower from 2
    max_queue_depth: 3     # Lower from 5
    memory_threshold: 0.70 # More strict
```

### Monitoring Queue Health

```bash
curl http://localhost:8001/status | jq '.queues'
```

---

## Migration Notes

### From Previous Architecture

**Removed**:

- ThreadPoolExecutor complexity
- Hybrid LLM fallback logic
- Forum/Reddit scraping declarations
- `enable_forums`, `enable_reddit`, `enable_youtube` config flags
- `max_worker_threads` config

**Added**:

- Explicit `chat_mode` setting
- Task queue system with resource awareness
- Queue configuration per type
- `psutil` for system monitoring

**No Breaking Changes**: All endpoints work the same way
