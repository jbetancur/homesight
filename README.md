# HomeSight

Local-only home monitoring system. Detects leaks, freeze risks, battery issues, and more.

## What It Does

- Monitors sensors via MQTT, Zigbee2MQTT, or LAN devices
- Auto-creates incidents when problems are detected
- Auto-resolves incidents when conditions clear
- Stores everything locally in SQLite
- Optional AI analysis for recommendations

## Quick Start

```bash
# Build
make build

# Start everything
./scripts/homesight.sh start

# Run AI intelligence demo (RAG + auto-ingestion)
./scripts/demo-ai-intelligence.sh

# Open dashboard
./scripts/homesight.sh dashboard

# Check status
./scripts/homesight.sh status
```

## Device Auto-Discovery

HomeSight is **truly zero-config** - it automatically discovers and connects to ALL devices/brokers on your network:

| Protocol | Auto-Discovery | Behavior |
|----------|----------------|----------|
| **MQTT Broker** | ✅ Yes | Connects to ALL discovered brokers (_mqtt._tcp) |
| **Zigbee2MQTT** | ✅ Via MQTT | Enabled on each discovered MQTT broker |
| **Z-Wave JS** | ✅ Yes | Discovers Z-Wave gateways (_z-wave-js._tcp) |
| **Matter** | ✅ Yes | Discovers ALL Matter devices (_matter._tcp) |
| **Shelly** | ✅ Yes | Finds ALL Shelly smart plugs/relays (_http._tcp) |
| **Tasmota** | ✅ Yes | Discovers ALL Tasmota devices (_http._tcp) |
| **ESPHome** | ✅ Yes | Finds ALL ESPHome devices (_esphomelib._tcp) |

### MQTT Device Discovery (Generic)

HomeSight includes a **generic MQTT discovery listener** that automatically detects devices from:

- **Home Assistant** MQTT discovery (`homeassistant/+/+/config`)
- **Homie Convention** devices (`homie/+/$homie`)
- **Tasmota** discovery (`tasmota/discovery/+/config`)
- **Generic** MQTT patterns (`+/discovery`)

**View discovered devices** in the dashboard:

```bash
./scripts/homesight.sh dashboard
# Press TAB to switch to Discovery view
```

**Or via API**:

```bash
# See all discovered but not yet onboarded devices
curl http://localhost:8080/api/discovery

# Discover ALL mDNS services on network (not just known types)
curl http://localhost:8080/api/discovery?generic=true

# Onboard a specific device
curl -X POST http://localhost:8080/api/onboard/device \
  -H "Content-Type: application/json" \
  -d '{"id":"govee_light_1", "name":"Living Room Light", ...}'
```

**Zero Configuration Required**:

- Just leave `mqtt.broker_url` empty in `config.yaml`
- HomeSight automatically finds and connects to ALL brokers/devices
- No manual selection needed - aggregates everything
- Devices appear in Discovery view when they announce themselves

Example startup logs:

```log
Zero-config mode: Auto-discovering MQTT brokers...
Found 3 MQTT broker(s), connecting to all...
  → Connecting to: homeassistant (tcp://10.0.60.46:1883)
    ✓ Connected to homeassistant
    ✓ Zigbee2MQTT enabled on homeassistant
    ✓ MQTT discovery listener enabled (Home Assistant, Homie, Tasmota, etc.)
  → Connecting to: local-mosquitto (tcp://192.168.1.10:1883)
    ✓ Connected to local-mosquitto
```

**Requirements**:

- Devices must support mDNS/Bonjour
- Must be on the same network/VLAN
- mDNS must be enabled (usually default)

**Manual Configuration**: If auto-discovery doesn't find your devices, you can still configure them manually in `config.yaml`.

## Running the Demo

### Sensor & Incident Demo

```bash
# Run interactive demo (simulates sensor lifecycle)
./scripts/demo-interactive.sh

# Clean up demo data
./scripts/cleanup-demo.sh
```

The demo creates:

- 6 test devices (leak sensor, sump pump, temperature sensors, door sensors)
- 2 incidents (water leak, low battery)

### AI Intelligence Demo

```bash
# Comprehensive AI demo (RAG + auto-ingestion)
./scripts/demo-ai-intelligence.sh
```

This interactive demo showcases:

**Part 1: RAG-Powered Analysis**

- Document retrieval from vector database
- Semantic search with relevance scoring
- Context-aware incident recommendations
- Transparent sourcing (shows which docs were used)
- Real examples: Water leak, freeze risk, device issues

**Part 2: Zero-Config Auto-Ingestion**

- Simulates device onboarding
- Automatic doc fetching via webhook
- Background processing (non-blocking)
- Verification that docs were indexed
- Incident analysis using auto-fetched docs

## Intelligent AI with RAG

HomeSight uses Retrieval-Augmented Generation (RAG) to provide context-aware incident analysis with **zero-configuration auto-ingestion**.

### How It Works

1. **Device Discovery**: When a new device is onboarded (Zigbee2MQTT, MQTT, etc.)
2. **Auto-Fetch**: AI service automatically fetches manufacturer documentation
3. **RAG Ingestion**: Documents are embedded into vector database (ChromaDB)
4. **Smart Analysis**: Incidents query RAG for relevant docs before providing recommendations

**Zero Config**: No manual doc downloads required! The system automatically:

- Detects device manufacturer and model from metadata
- Fetches manuals from manufacturer websites or templates
- Caches locally for offline use
- Ingests into RAG in the background

### Supported Manufacturers (Auto-Fetch)

The AI service uses OpenAI's GPT-4o-mini to intelligently search and fetch manufacturer documentation for any device. The system:

- Automatically identifies device manufacturer and model from discovery metadata
- Uses LLM-powered search to find official manuals and documentation
- Downloads and caches PDFs locally for offline use
- Indexes documents into the RAG vector database
- Falls back to generic templates if specific docs aren't found

**Dynamic Knowledge Base**: The RAG system builds its knowledge base automatically as you onboard devices. Each device onboarding triggers:

1. **Smart Document Discovery**: LLM searches for official manufacturer docs
2. **Automatic Download**: PDFs cached to `~/.homesight/manuals/`
3. **Background Indexing**: Documents embedded into ChromaDB
4. **Instant Availability**: New docs immediately available for incident analysis

Check what's currently indexed:

```bash
curl http://localhost:8001/rag/status
```

### Manual Override (Optional)

For offline use or custom docs, you can pre-populate the cache:

```bash
# Add PDFs to cache
mkdir -p ~/.homesight/manuals/aqara
cp your-manual.pdf ~/.homesight/manuals/aqara/

# Check what's in RAG
curl http://localhost:8001/rag/status
```

The auto-fetcher checks cache first, so pre-downloaded docs are used immediately.

### Example RAG Response

```json
{
  "analysis": "Incident Analysis: Water Leak Detected (Severity: high) [Enhanced with 3 document(s)]",
  "insights": [
    "Water leak detected - potential for property damage",
    "Found 3 relevant maintenance guides",
    "📖 Plumbing Emergency Guide: Emergency actions for water leaks...",
    "📖 Aqara Water Leak Sensor Manual: Troubleshooting and maintenance..."
  ],
  "actions": [
    "Locate and shut off water source immediately",
    "Check for visible damage and call plumber if needed"
  ],
  "metadata": {
    "rag_sources": [
      {
        "source": "Plumbing Emergency Guide",
        "relevance": 0.654
      },
      {
        "source": "Aqara Water Leak Sensor Manual",
        "relevance": 0.369
      }
    ]
  }
}
```

## API Endpoints

### Health

```bash
curl http://localhost:8080/health
```

### Devices

```bash
# List all devices
curl http://localhost:8080/devices

# Get specific device
curl http://localhost:8080/devices/{id}
```

### Incidents

```bash
# List all incidents
curl http://localhost:8080/incidents

# List only open incidents
curl http://localhost:8080/incidents?status=open

# Get specific incident
curl http://localhost:8080/incidents/{id}

# Manually resolve incident
curl -X POST http://localhost:8080/incidents/{id}/resolve
```

## Architecture

```mermaid
graph TB
    subgraph "Devices & Sensors"
        MQTT_DEV[MQTT Devices]
        ZIGBEE[Zigbee/Thread Devices]
        LAN_DEV[LAN REST Devices]
        MATTER[Matter Devices]
    end

    subgraph "Message Bus"
        MOSQUITTO[MQTT Broker<br/>:1883]
    end

    subgraph "HomeSight Core Daemon :8080"
        direction TB
        API[REST API Server]
        EVENTS[Event Bus]
        DISCOVERY[MQTT Discovery Listener<br/>- Home Assistant Format<br/>- Homie Convention<br/>- Tasmota Format]
        
        subgraph "Integrations"
            INT_MQTT[MQTT Integration<br/>MQTT Client]
            INT_ZIGBEE[Zigbee2MQTT Wrapper]
            INT_LAN[LAN Integration<br/>HTTP/REST Polling]
            INT_MATTER[Matter Integration<br/>Discovery Only]
        end
        
        subgraph "Processing"
            RULES[Rules Engine<br/>- Leak Detection<br/>- Freeze Risk<br/>- Battery Low<br/>- Device Offline<br/>- Sump Pump Cycles]
            INCIDENTS[Incident Service]
        end
        
        subgraph "Storage"
            DB[(SQLite DB<br/>- Devices<br/>- Sensors<br/>- Incidents<br/>- Tasks<br/>- Homes/Zones/Assets)]
            METRICS[Metrics Sink]
        end
        
        AI_CLIENT[AI Client]
    end

    subgraph "AI Sidecar :8001"
        AI_API[FastAPI Server<br/>- Incident Analysis<br/>- Chat Interface]
        DOC_FETCH[Document Fetcher<br/>- LLM-Powered Search<br/>- Auto-Download PDFs]
        RAG[RAG Engine<br/>- FastEmbed Embeddings<br/>- ChromaDB Vector DB<br/>- Semantic Search]
    end

    subgraph "Cloud Services (Setup Only)"
        OPENAI[OpenAI API<br/>- GPT-4o-mini<br/>- Doc Discovery Only<br/>~$0.001 per device]
    end

    subgraph "Monitoring"
        PROM[Prometheus<br/>:9090]
    end

    %% Device connections
    MQTT_DEV --> MOSQUITTO
    ZIGBEE --> MOSQUITTO
    LAN_DEV --> INT_LAN
    MATTER --> INT_MATTER
    
    %% Integration connections
    MOSQUITTO --> INT_MQTT
    MOSQUITTO --> INT_ZIGBEE
    DISCOVERY --> INT_MQTT
    INT_MQTT --> EVENTS
    INT_ZIGBEE --> EVENTS
    INT_LAN --> EVENTS
    INT_MATTER --> EVENTS
    
    %% Event processing
    EVENTS --> RULES
    RULES --> INCIDENTS
    INCIDENTS --> DB
    EVENTS --> METRICS
    
    %% API connections
    API --> INCIDENTS
    API --> DB
    API --> AI_CLIENT
    API --> METRICS
    
    %% AI connections
    AI_CLIENT -->|HTTP| AI_API
    AI_API -->|Incident Analysis| RAG
    API -->|Device Onboarded Event| DOC_FETCH
    DOC_FETCH -.->|Find Docs| OPENAI
    DOC_FETCH -->|Index PDFs| RAG
    
    %% Metrics
    METRICS -->|Scrape| PROM
    
    %% Styling
    classDef core fill:#4a9eff,stroke:#2d5f9f,stroke-width:2px,color:#fff
    classDef storage fill:#66bb6a,stroke:#388e3c,stroke-width:2px,color:#fff
    classDef ai fill:#ff9800,stroke:#e65100,stroke-width:2px,color:#fff
    classDef device fill:#9e9e9e,stroke:#616161,stroke-width:2px,color:#fff
    classDef bus fill:#ab47bc,stroke:#6a1b9a,stroke-width:2px,color:#fff
    classDef cloud fill:#03a9f4,stroke:#0277bd,stroke-width:2px,stroke-dasharray: 5 5,color:#fff
    
    class API,EVENTS,RULES,INCIDENTS,DISCOVERY core
    class DB,METRICS storage
    class AI_API,RAG,DOC_FETCH,AI_CLIENT ai
    class MQTT_DEV,ZIGBEE,LAN_DEV,MATTER device
    class MOSQUITTO,PROM bus
    class OPENAI cloud
```

### Key Architecture Notes

**MQTT Client, Not Server:**

- HomeSight connects to external Mosquitto as MQTT client
- Does not embed/bundle MQTT broker
- Supports multiple broker connections simultaneously
- Auto-discovers brokers via mDNS (`_mqtt._tcp`)

**Discovery Architecture:**

- **mDNS Discovery**: Finds brokers, Matter devices, LAN devices, Z-Wave JS gateways
- **MQTT Discovery Listener**: Parses Home Assistant, Homie, and Tasmota discovery messages
- **Zero-config**: No manual device entry required

**Integration Types:**

- **MQTT Integration**: Generic MQTT client for device state and control
- **Zigbee2MQTT**: Wrapper around MQTT client using `zigbee2mqtt` base topic
- **LAN Integration**: HTTP/REST polling for Shelly, Tasmota, ESPHome
- **Matter Integration**: Discovery only (control not yet implemented)

### AI Architecture Details

**Hybrid Architecture (Local + Cloud):**

**Local Components (Always Running):**

- **Embeddings**: FastEmbed (BAAI/bge-small-en-v1.5) runs locally - ~50MB model
- **Vector Storage**: ChromaDB persists all embeddings locally
- **RAG Queries**: 100% offline semantic search and retrieval
- **Incident Analysis**: All AI recommendations generated locally using RAG context

**Cloud Services (Device Onboarding Only):**

- **OpenAI GPT-4o-mini**: Used when onboarding devices to find manufacturer documentation
- **Trigger**: Automatic webhook from main daemon when device is discovered
- **Process**: LLM searches web for device manuals → downloads PDF → indexes locally
- **Cost**: ~$0.001 per device (one-time)
- **Fallback**: Generic templates if no API key provided

**Workflow:**

1. **Discovery**: Device found via MQTT/mDNS
2. **Onboarding**: User adds device through UI
3. **Auto-Fetch**: AI service receives webhook, uses OpenAI to find manual
4. **Index**: PDF downloaded and embedded into local ChromaDB
5. **Analysis**: Future incidents use local RAG (no cloud calls)

**Benefits:**

- ✅ Privacy: Incident data never leaves your network
- ✅ Fast: Local embeddings, no API latency for analysis
- ✅ Reliable: Works offline after initial device setup
- ✅ Cost-effective: ~$0.001 per device, zero ongoing costs
- ✅ Dynamic: Knowledge base grows automatically with your home

## Auto-Resolution

Incidents automatically resolve when:

- **Leak sensors**: `leak=false` reported
- **Temperature**: Rises above freeze threshold (35°F)
- **Battery**: Level recovers above 20%

No manual intervention needed in production.

## Rules Engine

Built-in rules:

- **Leak Detection** - Creates critical incident when water detected
- **Freeze Risk** - High severity when temp < 35°F
- **Low Battery** - Medium severity when < 20%
- **Sump Pump Cycles** - Excessive cycling detection
- **Device Offline** - Alerts when device stops reporting

## Configuration

Edit `config.yaml`:

```yaml
server:
  port: 8080
  
database:
  path: "./data/homesight.db"
  
mqtt:
  enabled: true
  broker: "tcp://localhost:1883"
  
integrations:
  zigbee: false
  lan: false
```

## Control Script

```bash
./scripts/homesight.sh <command>

Commands:
  start              Start all services
  stop               Stop all services  
  restart [service]  Restart service(s)
  status             Show service status
  dashboard          Open TUI dashboard
  logs <service>     View service logs
```

## Dashboard

Interactive TUI with:

- Real-time device list
- Active incidents with severity colors
- Auto-refresh every 5 seconds
- Keyboard: `r` to refresh, `q` to quit

## Project Structure

```sh
homesight/
├── cmd/
│   ├── homesightd/      # Main daemon
│   └── dashboard/       # TUI dashboard
├── internal/
│   ├── api/             # REST API server
│   ├── db/              # SQLite repositories
│   ├── events/          # Event bus
│   ├── incidents/       # Incident service
│   ├── integrations/    # Device integrations
│   ├── metrics/         # Prometheus metrics
│   ├── model/           # Domain models
│   └── rules/           # Rules engine
├── ai-sidecar/          # Python AI service (optional)
├── scripts/             # Control scripts
├── data/                # SQLite database
└── config.yaml          # Configuration
```

## Requirements

- Go 1.25+
- Python 3.10+ (for AI sidecar)
- Docker (for MQTT broker)
- SQLite3

## Services

- **homesightd** - Main daemon (port 8080)
- **AI Sidecar** - Optional AI service (port 8001)
- **MQTT Broker** - Mosquitto (port 1883)
- **Prometheus** - Metrics (port 9090)

## Development

```bash
# Build daemon and dashboard
make build

# Clean build artifacts
make clean
```

## Adding Devices

Devices are auto-discovered via integrations. For manual testing:

```bash
# Create test device (demo only)
curl -X POST http://localhost:8080/devices \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test-sensor-001",
    "name": "Test Sensor",
    "type": "water_leak",
    "integration": "mqtt",
    "enabled": true
  }'

# Delete test device
curl -X DELETE http://localhost:8080/devices/test-sensor-001
```

**Note**: In production, use auto-discovery instead of manual device creation.

## Troubleshooting

**Services won't start:**

```bash
./scripts/homesight.sh status
tail -f .logs/daemon.log
```

**Database issues:**

```bash
sqlite3 data/homesight.db
.tables
SELECT * FROM incidents WHERE status='open';
```

**MQTT connection failed:**

```bash
docker ps  # Check if mosquitto is running
docker logs homesight-mosquitto
```

## License

TBD
