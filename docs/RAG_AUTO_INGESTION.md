# RAG Automatic Document Ingestion

## Status: ✅ IMPLEMENTED

This document describes HomeSight's automatic document ingestion system.

## Architecture Overview

### Event-Driven Zero-Config System

```
┌─────────────────────────────────────────────────────────────┐
│ Device Onboarding                                           │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ 1. Device Stored in SQLite                                  │
│    - Device ID: "zigbee-aqara-leak-001"                    │
│    - Type: "leak_sensor"                                    │
│    - Metadata: {"manufacturer": "Aqara",                   │
│                 "model": "SJCGQ11LM"}                      │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Webhook Event Sent to AI Sidecar                        │
│    POST /events/device                                      │
│    Payload: Device info + metadata                          │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. AI Sidecar Processes Event (Background Task)            │
│    - Extracts manufacturer + model                          │
│    - Calls DocumentAutoFetcher                              │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Document Fetcher Service                                 │
│    - Check if docs already in RAG                           │
│    - Check local cache (~/.homesight/manuals/)              │
│    - Try manufacturer-specific fetcher (Aqara, Shelly)      │
│    - Fall back to template-based generic fetcher            │
│      d) Community repository (GitHub/HomeSight-Docs)        │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. RAG Ingestion                                            │
│    - Parse PDF/HTML                                         │
│    - Extract text                                           │
│    - Generate embeddings                                    │
│    - Store in ChromaDB with metadata                        │
│    - Tag: manufacturer, model, device_type                  │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Confirmation                                             │
│    - Update device record: "docs_indexed": true             │
│    - Log: "Indexed Aqara SJCGQ11LM manual (12 pages)"      │
└─────────────────────────────────────────────────────────────┘
```

### Document Sources (Priority Order)

1. **Local Cache** (`/var/lib/homesight/manuals/`)
   - Pre-downloaded PDFs organized by manufacturer
   - Fast, always available
   - Admin can pre-populate common devices

2. **Manufacturer APIs** (if available)
   - Aqara API: Has documentation endpoints
   - Shelly API: Provides device specs via REST
   - SmartThings: Cloud API with device metadata

3. **Web Scraping** (fallback)
   - Manufacturer support sites
   - Extract from product pages
   - Download from support documentation links
   - Example: `https://www.aqara.com/us/support/download.html`

4. **Community Repository** (future)
   - GitHub: `homesight/device-docs`
   - Crowdsourced manuals for common devices
   - Pull request workflow for new devices

### Implementation Plan

#### Phase 1: Event System (Go Daemon)

```go
// internal/events/bus.go
type EventBus struct {
    subscribers map[string][]chan Event
}

type Event struct {
    Type      string                 // "device.created", "device.updated"
    Timestamp time.Time
    Data      map[string]interface{}
}

// Publish device events
func (eb *EventBus) PublishDeviceCreated(device Device) {
    event := Event{
        Type: "device.created",
        Data: map[string]interface{}{
            "device_id":    device.ID,
            "manufacturer": device.Metadata["manufacturer"],
            "model":        device.Metadata["model"],
            "type":         device.Type,
        },
    }
    eb.Publish(event)
}
```

#### Phase 2: Webhook to AI Sidecar

```go
// internal/api/webhooks.go
func (s *Server) notifyAIService(event Event) {
    if s.config.AIWebhookURL == "" {
        return // AI integration disabled
    }
    
    payload, _ := json.Marshal(event)
    resp, err := http.Post(
        s.config.AIWebhookURL + "/events/device",
        "application/json",
        bytes.NewBuffer(payload),
    )
    // Handle response...
}
```

#### Phase 3: Document Fetcher (Python AI Sidecar)

```python
# ai-sidecar/document_fetcher.py

class DocumentFetcher:
    def __init__(self, rag_engine: RAGEngine):
        self.rag = rag_engine
        self.cache_dir = Path("/var/lib/homesight/manuals")
        self.fetchers = {
            "aqara": AqaraFetcher(),
            "shelly": ShellyFetcher(),
            "generic": GenericWebFetcher(),
        }
    
    async def fetch_for_device(self, device: dict) -> bool:
        """Fetch and ingest documentation for a device"""
        manufacturer = device.get("manufacturer", "").lower()
        model = device.get("model", "")
        
        # Check if already indexed
        if self._is_indexed(manufacturer, model):
            logger.info(f"Docs already indexed for {manufacturer} {model}")
            return True
        
        # Try local cache first
        cached = self._check_cache(manufacturer, model)
        if cached:
            self._ingest_document(cached, device)
            return True
        
        # Try manufacturer-specific fetcher
        fetcher = self.fetchers.get(manufacturer, self.fetchers["generic"])
        docs = await fetcher.fetch(manufacturer, model)
        
        if docs:
            for doc in docs:
                self._ingest_document(doc, device)
            return True
        
        logger.warning(f"Could not find docs for {manufacturer} {model}")
        return False
    
    def _ingest_document(self, doc_path: Path, device: dict):
        """Ingest a document into RAG"""
        text = extract_text_from_pdf(doc_path)
        
        self.rag.add_document(
            text=text,
            metadata={
                "source": f"{device['manufacturer']} {device['model']} Manual",
                "manufacturer": device["manufacturer"],
                "model": device["model"],
                "device_type": device["type"],
                "category": "device_manual",
                "auto_ingested": True,
                "ingested_at": datetime.now().isoformat(),
            }
        )
```

#### Phase 4: Manufacturer-Specific Fetchers

```python
# ai-sidecar/fetchers/aqara.py

class AqaraFetcher:
    """Fetch Aqara device documentation"""
    
    SUPPORT_URL = "https://www.aqara.com/us/support/download.html"
    
    async def fetch(self, manufacturer: str, model: str) -> List[Path]:
        """Fetch manual for Aqara device"""
        
        # Map model to download URL
        model_urls = {
            "SJCGQ11LM": "https://www.aqara.com/.../water-leak-sensor-manual.pdf",
            "WSDCGQ11LM": "https://www.aqara.com/.../temp-humidity-manual.pdf",
            # ... more models
        }
        
        url = model_urls.get(model)
        if not url:
            # Try searching support site
            url = await self._search_support_site(model)
        
        if url:
            pdf_path = await self._download_pdf(url, model)
            return [pdf_path]
        
        return []
```

### API Endpoint (AI Sidecar)

```python
# ai-sidecar/main.py

@app.post("/events/device")
async def handle_device_event(event: dict):
    """Handle device lifecycle events"""
    
    if event["type"] == "device.created":
        device = event["data"]
        
        # Queue document fetch (don't block response)
        background_tasks.add_task(
            document_fetcher.fetch_for_device,
            device
        )
        
        return {"status": "queued"}
    
    return {"status": "ignored"}
```

### Configuration

```yaml
# config/homesight.yaml

ai:
  enabled: true
  webhook_url: "http://localhost:8001"
  auto_ingest_docs: true
  doc_sources:
    - local_cache
    - manufacturer_api
    - web_scraping
  cache_dir: "/var/lib/homesight/manuals"
```

### User Experience

#### Automatic (Zero Config)

```bash
# User adds Aqara leak sensor via Zigbee2MQTT
# HomeSight detects it automatically
# Behind the scenes:
# 1. Device saved to SQLite
# 2. Event published
# 3. AI fetches Aqara manual from web
# 4. Manual ingested into RAG
# 5. Future incidents get Aqara-specific advice
```

#### Manual Override (Advanced Users)

```bash
# Pre-populate cache with PDFs
mkdir -p /var/lib/homesight/manuals/aqara
cp *.pdf /var/lib/homesight/manuals/aqara/

# Manually trigger ingestion
curl -X POST http://localhost:8001/ingest/device \
  -d '{"manufacturer": "Aqara", "model": "SJCGQ11LM"}'

# Check ingestion status
curl http://localhost:8001/rag/status
```

## Benefits

1. **Zero User Effort**: Docs automatically indexed on device onboarding
2. **Always Current**: RAG knowledge grows with device inventory
3. **Smart Queries**: Can filter RAG by manufacturer/model
4. **Graceful Fallback**: If docs not found, still uses generic rules
5. **Community-Driven**: Users can contribute docs to shared repository

## Challenges & Solutions

### Challenge 1: Not All Manufacturers Have APIs
**Solution**: Multi-tier approach (local → API → web scrape → community)

### Challenge 2: PDFs Behind Login Walls
**Solution**: 
- Local cache as primary source
- Community repository for common devices
- Graceful degradation to generic advice

### Challenge 3: Large PDFs (Bandwidth/Storage)
**Solution**:
- Only fetch once per model (not per device)
- Cache locally after first fetch
- Extract only relevant sections (installation, troubleshooting)

### Challenge 4: Rate Limiting from Manufacturer Sites
**Solution**:
- Respect robots.txt
- Cache aggressively
- Queue requests with exponential backoff
- Community repository reduces need for live fetching

## Next Steps

### MVP (1-2 days)
1. Add device event publishing in Go daemon
2. Create webhook endpoint in AI sidecar
3. Implement local cache checking
4. Test with manually downloaded PDFs

### Phase 2 (1 week)
1. Implement Aqara fetcher (web scraping)
2. Implement Shelly fetcher (API-based)
3. Add ingestion queue/background tasks
4. Test with real device onboarding

### Phase 3 (Future)
1. Create community docs repository on GitHub
2. Add support for 10+ manufacturers
3. Implement automatic update checking
4. Build admin UI for doc management

## Alternative: Community Repository

Instead of fetching from manufacturers, maintain a curated repository:

```
homesight/device-docs/
├── aqara/
│   ├── SJCGQ11LM-leak-sensor.pdf
│   ├── WSDCGQ11LM-temp-humidity.pdf
│   └── metadata.json
├── shelly/
│   ├── shelly-1pm-manual.pdf
│   └── metadata.json
└── index.json  # Maps manufacturer+model to files
```

HomeSight checks GitHub releases on startup, downloads new docs in background.

**Advantages:**
- Reliable, always available
- No web scraping needed
- Community can contribute
- Version controlled

**Disadvantages:**
- Requires maintenance
- May lag behind new device releases
- Copyright considerations
