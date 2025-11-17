## Making HomeSight AI Actually Intelligent

### Current State: Rule-Based
Right now the AI uses **hardcoded if/else rules**:
```python
if "leak" in incident_type:
    actions.append("Shut off water")
```

### Future State: LLM + RAG

To make it truly intelligent, you need 3 components:

## 1. Local LLM (Language Model)

**What it does**: Understands context and generates human-like responses

**Setup**:
```bash
# Download a GGUF model (e.g., Llama 2, Mistral)
wget https://huggingface.co/TheBloke/Llama-2-7B-Chat-GGUF/resolve/main/llama-2-7b-chat.Q4_K_M.gguf

# Place in models directory
mkdir -p /var/lib/homesight/models
mv llama-2-7b-chat.Q4_K_M.gguf /var/lib/homesight/models/

# Restart AI sidecar - it will auto-load the model
```

**What changes**: 
- Chat responses become contextual and natural
- Can reason about complex situations
- Combines multiple data sources

## 2. RAG (Retrieval-Augmented Generation)

**What it does**: Retrieves relevant documentation before answering

**Setup**:
```bash
# 1. Collect documentation
mkdir -p /var/lib/homesight/docs
cd /var/lib/homesight/docs

# Add manufacturer manuals
docs/
├── aqara/
│   ├── SJCGQ11LM-manual.pdf      # Water leak sensor
│   ├── WSDCGQ11LM-manual.pdf     # Temp/humidity sensor
│   └── troubleshooting.md
├── shelly/
│   ├── plug-s-manual.pdf
│   └── api-guide.md
├── home-maintenance/
│   ├── plumbing-emergencies.md
│   ├── winterization.md
│   └── hvac-maintenance.md
└── building-codes/
    └── freeze-protection.pdf

# 2. Install RAG dependencies
cd ~/homesight/ai-sidecar
pip install sentence-transformers chromadb pypdf

# 3. Ingest documents (run once)
python ingest_docs.py /var/lib/homesight/docs
```

**What changes**:
- Answers cite specific manuals
- References manufacturer troubleshooting steps
- Pulls building codes and best practices

## 3. API Integration

**What it does**: Fetches real device data and history

See `intelligent_analysis.py` for implementation that:
1. Fetches incident from HomeSight API
2. Gets associated device details
3. Retrieves device history/metrics
4. Queries RAG for relevant docs
5. Builds comprehensive prompt with all context
6. Generates intelligent response

## Example Flow

### Without LLM (Current):
```
User: "What should I do about the leak?"
AI: [Rule-based] "Shut off water valve" (generic)
```

### With LLM + RAG:
```
User: "What should I do about the leak?"

AI fetches:
  - Incident: leak_basement_001
  - Device: Aqara SJCGQ11LM at "Basement near water heater"
  - History: No prior leaks, device installed 6 months ago
  - RAG docs: Aqara manual + Plumbing emergency guide

AI analyzes:
  "Based on your Aqara SJCGQ11LM sensor in the basement near the 
   water heater, a leak has been detected. Since this is the first 
   incident at this location and the sensor is functioning properly 
   (verified by recent battery report), this is likely an actual leak.
   
   Immediate steps:
   1. Shut off main water valve (usually in basement near meter)
   2. Turn off basement electrical breaker
   3. Check water heater T&P valve and supply lines
   4. According to your insurance docs, photograph damage within 24hrs
   
   The Aqara manual recommends monthly testing - last test was 3 weeks 
   ago, so sensor reliability is high.
   
   Long-term: Consider installing a drip pan under the water heater
   as recommended in the plumbing code for basement installations."
```

## Implementation Checklist

### Phase 1: LLM (Easy - 30 mins)
- [ ] Download GGUF model
- [ ] Place in `/var/lib/homesight/models/`
- [ ] Restart AI sidecar
- [ ] Test chat endpoint

### Phase 2: RAG (Medium - 2-4 hours)
- [ ] Collect manufacturer PDFs
- [ ] Install RAG dependencies
- [ ] Write document ingestion script
- [ ] Build vector database
- [ ] Test retrieval

### Phase 3: Integration (Medium - 2-3 hours)
- [ ] Modify `analyze_incident()` to fetch real device data
- [ ] Add RAG query to get relevant docs
- [ ] Build comprehensive prompt
- [ ] Parse structured LLM output
- [ ] Return enhanced response

### Phase 4: Advanced (Hard - days)
- [ ] Add device history analysis
- [ ] Trend detection across incidents
- [ ] Predictive maintenance suggestions
- [ ] Multi-device correlation
- [ ] Learning from resolutions

## File Structure

```
ai-sidecar/
├── main.py                      # Current FastAPI service
├── intelligent_analysis.py      # Reference implementation (new)
├── rag_engine.py               # TODO: Vector DB + retrieval
├── ingest_docs.py              # TODO: Document processor
└── models/                      # LLM models (GGUF files)

/var/lib/homesight/
├── models/
│   └── llama-2-7b-chat.gguf
├── docs/                        # Source documentation
│   ├── aqara/
│   ├── shelly/
│   └── home-maintenance/
└── rag-db/                      # Vector database
    └── chroma.sqlite3
```

## Cost & Performance

**LLM**: 
- 7B model: ~4GB RAM, 2-5 sec response
- 13B model: ~8GB RAM, 5-10 sec response
- Runs on CPU (or GPU for faster inference)

**RAG**:
- ~100-500MB for doc embeddings
- Sub-second retrieval
- One-time ingestion cost

**Total**: Can run on modest hardware (Raspberry Pi 4 8GB works!)

## Why This Matters

Right now HomeSight is **reactive**: "Leak detected → Generic advice"

With LLM+RAG it becomes **intelligent**: 
- Knows your specific devices
- References their manuals
- Considers your home's history
- Provides contextualized guidance
- Learns from patterns

This is the difference between a **rules engine** and an actual **AI assistant**.
