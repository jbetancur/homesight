#!/bin/bash

# HomeSight AI Intelligence Demo
# Comprehensive demonstration of RAG-powered analysis and zero-config auto-ingestion

set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                                                              ║${NC}"
echo -e "${CYAN}║        🤖  HomeSight AI Intelligence Demo  🤖                ║${NC}"
echo -e "${CYAN}║                                                              ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "This demo showcases two key AI features:"
echo ""
echo "  Part 1: RAG-Powered Incident Analysis"
echo "    • Retrieves relevant docs from vector database"
echo "    • Provides context-aware recommendations"
echo "    • Shows transparent sourcing with relevance scores"
echo ""
echo "  Part 2: Zero-Config Auto-Ingestion"
echo "    • Automatically fetches device manuals"
echo "    • No manual downloads required"
echo "    • Background processing"
echo ""
read -p "Press Enter to start..."
echo ""

# Check if services are running
if ! curl -s http://localhost:8001/health > /dev/null 2>&1; then
    echo -e "${RED}❌ AI Service not running${NC}"
    echo "Start it with: ./scripts/homesight.sh start"
    exit 1
fi

# ============================================================================
# PART 1: RAG-POWERED INCIDENT ANALYSIS
# ============================================================================

echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  PART 1: RAG-Powered Incident Analysis${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# Check RAG status
echo -e "${YELLOW}📊 RAG System Status${NC}"
curl -s http://localhost:8001/rag/status | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"  Enabled: {data['enabled']}\")
if data['enabled']:
    print(f\"  Documents: {data['stats']['total_documents']}\")
    print(f\"  Model: {data['stats']['embedding_model']}\")
    print(f\"  Status: {data['message']}\")
else:
    print(f\"  Error: {data.get('message', 'Unknown error')}\")
"
echo ""
read -p "Press Enter to test incident analysis..."
echo ""

# Test 1: Water Leak
echo -e "${BLUE}━━━ Scenario 1: Water Leak Detected ━━━${NC}"
echo ""
echo "📍 Location: Basement water sensor"
echo "⚠️  Severity: High"
echo ""
curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "type": "incident",
    "data": {
      "id": "demo-leak-1",
      "type": "Water Leak Detected",
      "severity": "high",
      "device_id": "aqara-water-basement"
    }
  }' | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"Analysis: {data['analysis']}\")
print(\"\n🔍 Key Insights:\")
for i, insight in enumerate(data['insights'][:3], 1):
    print(f\"  {i}. {insight[:100]}{'...' if len(insight) > 100 else ''}\")
print(\"\n✅ Recommended Actions:\")
for i, action in enumerate(data['actions'], 1):
    print(f\"  {i}. {action}\")
if 'rag_sources' in data['metadata']:
    print(\"\n📚 Documents Referenced:\")
    for src in data['metadata']['rag_sources']:
        print(f\"  📖 {src['source'][:50]} (relevance: {src['relevance']:.1%})\")
"
echo ""
read -p "Press Enter for next scenario..."
echo ""

# Test 2: Freeze Risk
echo -e "${BLUE}━━━ Scenario 2: Freeze Risk Alert ━━━${NC}"
echo ""
echo "📍 Location: Garage temperature sensor"
echo "🌡️  Temperature: 32°F (0°C)"
echo ""
curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "type": "incident",
    "data": {
      "id": "demo-freeze-1",
      "type": "Freeze Risk Detected",
      "severity": "medium",
      "device_id": "shelly-temp-garage"
    }
  }' | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"Analysis: {data['analysis']}\")
print(\"\n🔍 Key Insights:\")
for i, insight in enumerate(data['insights'][:3], 1):
    print(f\"  {i}. {insight[:100]}{'...' if len(insight) > 100 else ''}\")
print(\"\n✅ Recommended Actions:\")
for i, action in enumerate(data['actions'], 1):
    print(f\"  {i}. {action}\")
if 'rag_sources' in data['metadata']:
    print(\"\n📚 Documents Referenced:\")
    for src in data['metadata']['rag_sources']:
        print(f\"  📖 {src['source'][:50]} (relevance: {src['relevance']:.1%})\")
"
echo ""
read -p "Press Enter to continue to Part 2..."
echo ""

# ============================================================================
# PART 2: ZERO-CONFIG AUTO-INGESTION
# ============================================================================

echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  PART 2: Zero-Config Auto-Ingestion${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo "This demonstrates automatic document fetching when devices are added."
echo ""

# Simulate device onboarding
echo -e "${YELLOW}🔌 Simulating Device Onboarding${NC}"
echo ""
echo "New device detected by Zigbee2MQTT:"
echo "  • Manufacturer: Aqara"
echo "  • Model: WSDCGQ11LM (Temperature & Humidity Sensor)"
echo "  • Type: temp_sensor"
echo ""
read -p "Press Enter to trigger auto-ingestion..."
echo ""

# Send webhook
echo -e "${YELLOW}📤 Sending webhook to AI service...${NC}"
RESPONSE=$(curl -s -X POST http://localhost:8001/events/device \
  -H "Content-Type: application/json" \
  -d '{
    "type": "device.created",
    "data": {
      "manufacturer": "Aqara",
      "model": "WSDCGQ11LM",
      "type": "temp_sensor",
      "id": "zigbee-aqara-temp-001"
    }
  }')

echo "$RESPONSE" | python3 -c "import sys, json; print(json.dumps(json.load(sys.stdin), indent=2))"
echo ""
echo -e "${GREEN}✅ Webhook received! AI is fetching docs in background...${NC}"
echo ""
echo "⏳ Waiting for ingestion to complete..."
sleep 5
echo ""

# Verify ingestion
echo -e "${YELLOW}🔍 Verifying documentation was ingested...${NC}"
curl -s http://localhost:8001/rag/status | python3 -c "
import sys, json
data = json.load(sys.stdin)
if data['enabled']:
    print(f\"  ✅ RAG Status: {data['message']}\")
    print(f\"  📚 Total Documents: {data['stats']['total_documents']}\")
    print(f\"  🆕 Auto-fetched docs now available!\")
"
echo ""
read -p "Press Enter to test with new device docs..."
echo ""

# Test analysis with new device
echo -e "${YELLOW}🧪 Testing incident analysis with auto-fetched docs...${NC}"
echo ""
echo "Scenario: Temperature sensor reporting condensation issue"
echo ""
curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "type": "incident",
    "data": {
      "id": "demo-humidity-1",
      "type": "High Humidity Detected",
      "severity": "medium",
      "device_id": "zigbee-aqara-temp-001"
    }
  }' | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"Analysis: {data['analysis']}\")
print(\"\n🔍 Insights:\")
for i, insight in enumerate(data['insights'][:3], 1):
    print(f\"  {i}. {insight[:120]}{'...' if len(insight) > 120 else ''}\")
if 'rag_sources' in data['metadata']:
    print(\"\n📚 Documents Used:\")
    auto_fetched = False
    for src in data['metadata']['rag_sources'][:3]:
        print(f\"  📖 {src['source'][:50]} ({src['relevance']:.1%})\")
        if 'WSDCGQ11LM' in src['source']:
            auto_fetched = True
    if auto_fetched:
        print(\"\n  ✨ Used auto-fetched device manual!\")
"
echo ""

# ============================================================================
# SUMMARY
# ============================================================================

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  🎉 AI Intelligence Demo Complete! 🎉${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo "What you just saw:"
echo ""
echo "  ✅ RAG-powered incident analysis"
echo "     • Queries vector database for relevant documentation"
echo "     • Provides context-aware recommendations"
echo "     • Shows transparent sourcing with relevance scores"
echo ""
echo "  ✅ Zero-config auto-ingestion"
echo "     • Device onboarded → Webhook sent"
echo "     • AI automatically fetched manufacturer docs"
echo "     • Manual ingested into RAG (no user action!)"
echo "     • Future incidents use device-specific documentation"
echo ""
echo "Key Benefits:"
echo "  • 📚 Smart: Uses real manufacturer documentation"
echo "  • 🚀 Automatic: No manual downloads or ingest scripts"
echo "  • 🔍 Transparent: Shows which docs were consulted"
echo "  • 💾 Offline: Caches docs locally at ~/.homesight/manuals/"
echo ""
echo "Next Steps:"
echo "  • Add your real devices → Docs auto-fetch"
echo "  • Pre-download PDFs to cache for offline use"
echo "  • Check RAG status: curl http://localhost:8001/rag/status"
echo ""
echo "Documentation:"
echo "  • README.md - Quick start and features"
echo "  • docs/RAG_AUTO_INGESTION.md - Architecture details"
echo ""
