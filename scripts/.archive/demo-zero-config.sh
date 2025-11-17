#!/bin/bash

# Demo: Zero-Config Auto-Ingestion
# Shows how HomeSight automatically fetches device docs

set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  HomeSight Zero-Config Auto-Ingestion Demo${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "This demo shows how HomeSight automatically:"
echo "  1. Detects new devices being added"
echo "  2. Fetches manufacturer documentation"
echo "  3. Ingests into RAG database"
echo "  4. Uses docs for intelligent incident analysis"
echo ""
echo "✨ ZERO CONFIGURATION REQUIRED! ✨"
echo ""
read -p "Press Enter to start..."
echo ""

# Step 1: Simulate device discovery
echo -e "${YELLOW}Step 1: Device Discovered (Aqara Water Leak Sensor)${NC}"
echo ""
echo "Zigbee2MQTT detects new device:"
echo "  Manufacturer: Aqara"
echo "  Model: SJCGQ11LM"
echo "  Type: water_leak"
echo ""
read -p "Press Enter to send webhook to AI service..."
echo ""

# Step 2: Send webhook
echo -e "${YELLOW}Step 2: Webhook Sent to AI Service${NC}"
echo ""
curl -s -X POST http://localhost:8001/events/device \
  -H "Content-Type: application/json" \
  -d '{
    "type": "device.created",
    "data": {
      "manufacturer": "Aqara",
      "model": "SJCGQ11LM",
      "type": "water_leak",
      "id": "zigbee-aqara-leak-001"
    }
  }' | python3 -c "import sys, json; print(json.dumps(json.load(sys.stdin), indent=2))"

echo ""
echo "⏳ AI service is fetching documentation in background..."
sleep 5
echo ""

# Step 3: Check RAG status
echo -e "${YELLOW}Step 3: Verify Documentation in RAG${NC}"
echo ""
curl -s http://localhost:8001/rag/status | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"RAG Status: {data['message']}\")
print(f\"Total Documents: {data['stats']['total_documents']}\")
print(f\"Embedding Model: {data['stats']['embedding_model']}\")
"
echo ""
read -p "Press Enter to test intelligent analysis..."
echo ""

# Step 4: Test incident analysis
echo -e "${YELLOW}Step 4: Incident Analysis (Using Auto-Fetched Docs!)${NC}"
echo ""
echo "Simulating water leak incident..."
echo ""
curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "type": "incident",
    "data": {
      "id": "incident-001",
      "type": "Water Leak Detected",
      "severity": "high",
      "device_id": "zigbee-aqara-leak-001"
    }
  }' | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"Analysis: {data['analysis']}\")
print(\"\nInsights:\")
for insight in data['insights'][:4]:  # First 4 insights
    print(f\"  • {insight}\")
print(\"\nActions:\")
for action in data['actions']:
    print(f\"  → {action}\")
if 'rag_sources' in data['metadata']:
    print(\"\n📚 Documents Consulted:\")
    for src in data['metadata']['rag_sources']:
        print(f\"  📖 {src['source']} (relevance: {src['relevance']:.1%})\")
"

echo ""
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Zero-Config Demo Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "What just happened:"
echo "  ✅ Device detected → Webhook sent"
echo "  ✅ AI auto-fetched manufacturer manual"
echo "  ✅ Manual ingested into RAG (ZERO user action!)"
echo "  ✅ Incident analysis used device-specific docs"
echo ""
echo "Try it with YOUR devices:"
echo "  1. Add device to HomeSight"
echo "  2. HomeSight sends webhook with manufacturer/model"
echo "  3. AI automatically fetches and indexes docs"
echo "  4. Future incidents get device-specific advice"
echo ""
echo "Cache location: ~/.homesight/manuals/"
echo "  • Pre-download PDFs here for offline use"
echo "  • Auto-fetcher checks cache first"
echo ""
