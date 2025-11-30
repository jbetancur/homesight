# HomeSight

Local-only home monitoring system. Detects leaks, freeze risks, battery issues, and more.

## Quick Start

```bash
make build
./scripts/homesight.sh start
./scripts/homesight.sh dashboard
```

**Services**: `http://localhost:8080` (main) | `http://localhost:8001` (AI, optional)

## Device Discovery

**MQTT-based Discovery:** All integrations publish device discovery messages to MQTT topics.

**Supported Integrations:**
- **Z-Wave** - Z-Wave JS devices via WebSocket bridge
- **Zigbee2MQTT** - Zigbee devices via MQTT (native support)
- **Custom** - Any device via MQTT topic: `homesight/{integration}/{id}/discovery`

**Discovery Flow:**
1. Integration publishes device discovery to MQTT
2. MQTT Consumer receives message
3. Device automatically registered in database
4. Appears in dashboard

**Configuration:** Edit `config.yaml` to enable integrations (currently Z-Wave and Zigbee2MQTT)

**Documentation:** See [docs/INTEGRATIONS_MQTT.md](docs/INTEGRATIONS_MQTT.md) for complete MQTT topic schema and integration guide.

## Demos

```bash
# Interactive demo (sensor lifecycle, incidents)
./scripts/demo-interactive.sh

# AI + RAG demo (if AI service running)
./scripts/demo-ai-intelligence.sh

# Cleanup
./scripts/cleanup-demo.sh
```

## AI Service (Optional)

Retrieval-Augmented Generation (RAG) for incident analysis.

**Flow:**

1. Device onboarded → AI service fetches manufacturer docs
2. PDFs cached locally and indexed into ChromaDB
3. Incidents query vector DB for relevant docs → LLM generates recommendations

**Auto-Fetch**: Uses OpenAI GPT-4o-mini to find manuals (~$0.001 per device, one-time)

**Offline**: All analysis runs locally. Cloud only used for initial doc discovery.

**Check status:**

```bash
curl http://localhost:8001/health
curl http://localhost:8001/rag/status
```

## API

Main service on `http://localhost:8080`:

```bash
# Health check
curl http://localhost:8080/health

# Devices
curl http://localhost:8080/devices
curl http://localhost:8080/devices/{id}

# Incidents
curl http://localhost:8080/incidents?status=open
curl http://localhost:8080/incidents/{id}
curl -X POST http://localhost:8080/incidents/{id}/resolve
```

## Architecture

**MQTT-based Event-Driven Architecture** - All integrations communicate via MQTT message bus.

```mermaid
graph TB
    subgraph "Integrations (Any Language)"
        ZWAVE[Z-Wave Bridge<br/>Go + WebSocket]
        ZIGBEE[Zigbee2MQTT<br/>Node.js]
        CUSTOM[Custom Integrations<br/>Python/Node/etc]
    end

    subgraph "MQTT Message Bus :1883"
        MOSQUITTO["Mosquitto Broker"]
        TOPICS["Topics:<br/>homesight/{int}/{id}/discovery<br/>homesight/{int}/{id}/state<br/>homesight/{int}/{id}/metadata<br/>homesight/cmd/{device-id}<br/>homesight/incidents/{id}/{iid}"]
    end

    subgraph "HomeSight Core :8080"
        CONSUMER[MQTT Consumer<br/>Device Registry]
        PUBLISHER[MQTT Publisher<br/>Device Commands]
        API[REST API]
        EVENTS[Event Bus]
        RULES[Rules Engine]
        INCIDENTS[Incident Service]
        DB[(SQLite DB)]
    end

    subgraph "AI Sidecar :8001"
        MQTT_SVC[MQTT Service<br/>Real-time Monitor]
        RAG[RAG Engine<br/>ChromaDB]
        CHAT[Chat/Analysis]
        DOC_FETCH[Doc Fetcher]
    end

    subgraph "Cloud (Setup Only)"
        OPENAI[OpenAI API<br/>Doc Discovery]
    end

    %% Integration → MQTT
    ZWAVE -->|Publish| MOSQUITTO
    ZIGBEE -->|Publish| MOSQUITTO
    CUSTOM -->|Publish| MOSQUITTO

    %% MQTT → Core
    MOSQUITTO -->|Subscribe| CONSUMER
    CONSUMER -->|Discovery| DB
    CONSUMER -->|State| EVENTS
    CONSUMER -->|Incidents| INCIDENTS

    %% Core → MQTT
    API --> PUBLISHER
    PUBLISHER -->|Commands| MOSQUITTO

    %% MQTT → Integrations
    MOSQUITTO -->|Commands| ZWAVE
    MOSQUITTO -->|Commands| ZIGBEE

    %% Event Processing
    EVENTS --> RULES
    RULES --> INCIDENTS
    INCIDENTS --> DB

    %% API
    API --> DB
    API --> INCIDENTS

    %% AI Real-time
    MOSQUITTO -->|Subscribe| MQTT_SVC
    MQTT_SVC -->|Incidents| CHAT
    CHAT --> RAG
    DOC_FETCH --> RAG
    DOC_FETCH -.->|Discovery| OPENAI

    %% Styling
    classDef core fill:#4a9eff,stroke:#2d5f9f,stroke-width:2px,color:#fff
    classDef ai fill:#ff9800,stroke:#e65100,stroke-width:2px,color:#fff
    classDef integration fill:#9e9e9e,stroke:#616161,stroke-width:2px,color:#fff
    classDef bus fill:#ab47bc,stroke:#6a1b9a,stroke-width:2px,color:#fff
    classDef cloud fill:#03a9f4,stroke:#0277bd,stroke-width:2px,stroke-dasharray:5,5,color:#fff

    class API,CONSUMER,PUBLISHER,EVENTS,RULES,INCIDENTS,DB core
    class MQTT_SVC,CHAT,RAG,DOC_FETCH ai
    class ZWAVE,ZIGBEE,CUSTOM integration
    class MOSQUITTO,TOPICS bus
    class OPENAI cloud
```

**HIL Home Intelligence Layer**

```mermaid
flowchart TD

%% -------------------------------------
%% CORE LAYER (EXISTING HOMESIGHT CORE)
%% -------------------------------------

subgraph Core["HomeSight Core"]
    MQTT["MQTT Event Bus"]
    DeviceMgr["Device Manager (Z-Wave, WiFi, Zigbee, Thread)"]
    Incidents["Incident Engine (Anomaly Detection)"]
    Summaries["Device Summaries & Documents"]
    Storage["Device State DB"]
end

MQTT --> DeviceMgr
DeviceMgr --> Incidents
DeviceMgr --> Storage
Incidents --> Summaries

%% -------------------------------------
%% INTELLIGENCE LAYER (HSIL)
%% -------------------------------------

subgraph HSIL["HomeSight Intelligence Layer"]
    EventIngest["Event Ingestion & Context Builder"]
    FeatureExtract["Feature Extraction (Trends, Patterns, Context)"]
    Memory["Home Memory Graph (Preferences, History)"]
    BehaviorModel["Behavior Model (Comfort, Water, HVAC, Solar)"]
    PolicyEngine["Policy Engine (Safety & Comfort Rules)"]
    LLM["Conversational Agent (LLM Wrapper)"]
end

Storage --> EventIngest
Incidents --> EventIngest
Summaries --> EventIngest

EventIngest --> FeatureExtract
FeatureExtract --> Memory
FeatureExtract --> BehaviorModel

Memory --> BehaviorModel
BehaviorModel --> PolicyEngine

Memory --> LLM
BehaviorModel --> LLM
PolicyEngine --> LLM

%% -------------------------------------
%% USER INTERFACE LAYER (CHAT + DASHBOARD)
%% -------------------------------------

subgraph UI["User Interaction Layer"]
    SMS["SMS / iMessage / WhatsApp"]
    Dashboard["Web Dashboard (Tile Grid UI)"]
end

LLM --> SMS
LLM --> Dashboard

%% -------------------------------------
%% ACTION OUTPUT BACK TO HOME
%% -------------------------------------

PolicyEngine --> Actions["Action Dispatcher (MQTT Commands)"]
Actions --> MQTT

```

### Core Components

**MQTT Message Bus:**
- **Mosquitto Broker** (:1883) - Central message bus for all integrations
- **MQTT Consumer** - Subscribes to integration messages, updates device registry
- **MQTT Publisher** - Publishes device commands to integrations

**Core Services:**
- **REST API** (:8080) - Device management, incident tracking, commands
- **Event Bus** - Internal event processing pipeline
- **Rules Engine** - Leak, freeze, battery, offline, pump cycle detection
- **Incident Service** - Creates and manages incidents
- **SQLite DB** - Stores devices, sensors, incidents, metadata

**Integrations** (Language-Agnostic):
- **Z-Wave Bridge** (Go) - Bridges Z-Wave JS WebSocket to MQTT
- **Zigbee2MQTT** (Node.js) - Already MQTT-native
- **Custom Integrations** - Any language (Python, Node, Rust) via MQTT topics

### AI Service

**Real-time MQTT Integration:**
- **MQTT Service** - Subscribes to device state and incident topics
- **In-memory Cache** - Maintains current device state for instant chat responses
- **Real-time Analysis** - 50x faster incident analysis (milliseconds vs HTTP polling)

**RAG Pipeline:**
- **Local:** FastEmbed embeddings + ChromaDB vector DB (offline analysis)
- **Cloud:** OpenAI GPT-4o-mini for doc discovery only (~$0.001 per device, one-time)
- **Workflow:** Device onboarded → fetch docs → index locally → use for incident analysis

## Rules Engine

Auto-creates incidents for:

- **Leak Detection** - Water detected
- **Freeze Risk** - Temp < 35°F
- **Low Battery** - Level < 20%
- **Device Offline** - No updates
- **Sump Pump Cycles** - Excessive cycling

Auto-resolves when conditions clear.

## Installation

### Production (Recommended)

```bash
sudo bash scripts/install.sh
```

This downloads pre-built binaries from GitHub releases and sets up systemd services for production deployment.

To install a specific version:

```bash
HOMESIGHT_VERSION=v1.0.0 sudo bash scripts/install.sh
```

See [Installation Guide](INSTALL.md) for detailed instructions.

## Development

```bash
make build        # Build daemon and dashboard
make clean        # Clean artifacts
./scripts/homesight.sh start       # Start all services
./scripts/homesight.sh dashboard   # Open TUI dashboard
./scripts/homesight.sh logs daemon # View daemon logs
```

## CI/CD Pipeline

Automated build, test, and release process using GitHub Actions:

- **Binaries** built for Linux (amd64, arm64)
- **Tests** run with race condition detection
- **Code quality** verified with golangci-lint
- **Docker images** pushed to GitHub Container Registry
- **Releases** automatically created with binaries attached

See [CI/CD Documentation](CI-CD.md) for complete details.

## Configuration

Edit `config.yaml` for MQTT broker, database path, and integrations.

See `config.yaml.example` for defaults.

## Requirements

- Go 1.25+
- Python 3.10+ (for AI sidecar, optional)
- Docker (for containers)
- SQLite3
