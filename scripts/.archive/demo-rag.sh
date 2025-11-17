#!/bin/bash

# HomeSight RAG Intelligence Demo
# Demonstrates how the AI uses manufacturer docs and maintenance guides

set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  HomeSight AI Intelligence Demo - RAG System${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "This demo shows how HomeSight's AI system uses:"
echo "  • Manufacturer device manuals (Aqara, Shelly, etc.)"
echo "  • Home maintenance guides"
echo "  • Building codes (IRC)"
echo "  • Emergency procedures"
echo ""
echo "...to provide intelligent, context-aware incident analysis."
echo ""

# Check if services are running
if ! curl -s http://localhost:8001/health > /dev/null 2>&1; then
    echo -e "${RED}❌ AI Service not running${NC}"
    echo "Start it with: cd ai-sidecar && ./start.sh"
    exit 1
fi

# Check RAG status
echo -e "${YELLOW}📊 RAG System Status${NC}"
curl -s http://localhost:8001/rag/status | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"  Enabled: {data['enabled']}\")
print(f\"  Documents: {data['stats']['total_documents']}\")
print(f\"  Model: {data['stats']['embedding_model']}\")
print(f\"  Status: {data['message']}\")
"
echo ""

# Test 1: Water Leak
echo -e "${BLUE}═══ Test 1: Water Leak Incident ═══${NC}"
echo ""
echo "Scenario: Water leak detected by basement sensor"
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
print(\"\nInsights:\")
for insight in data['insights']:
    print(f\"  • {insight}\")
print(\"\nActions:\")
for action in data['actions']:
    print(f\"  → {action}\")
if 'rag_sources' in data['metadata']:
    print(\"\nDocuments Consulted:\")
    for src in data['metadata']['rag_sources']:
        print(f\"  📖 {src['source']} (relevance: {src['relevance']:.1%})\")
"
echo ""
read -p "Press Enter to continue..."
echo ""

# Test 2: Freeze Risk
echo -e "${BLUE}═══ Test 2: Freeze Risk Incident ═══${NC}"
echo ""
echo "Scenario: Temperature dropping below 35°F, pipe freeze risk"
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
print(\"\nInsights:\")
for insight in data['insights']:
    print(f\"  • {insight}\")
print(\"\nActions:\")
for action in data['actions']:
    print(f\"  → {action}\")
if 'rag_sources' in data['metadata']:
    print(\"\nDocuments Consulted:\")
    for src in data['metadata']['rag_sources']:
        print(f\"  📖 {src['source']} (relevance: {src['relevance']:.1%})\")
"
echo ""
read -p "Press Enter to continue..."
echo ""

# Test 3: Water Heater Issue
echo -e "${BLUE}═══ Test 3: Water Heater Alert ═══${NC}"
echo ""
echo "Scenario: Water heater sensor detects unusual activity"
echo ""
curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "type": "incident",
    "data": {
      "id": "demo-heater-1",
      "type": "Water Heater Dripping",
      "severity": "medium",
      "device_id": "aqara-water-heater"
    }
  }' | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"Analysis: {data['analysis']}\")
print(\"\nInsights:\")
for insight in data['insights']:
    print(f\"  • {insight}\")
if 'actions' in data and data['actions']:
    print(\"\nActions:\")
    for action in data['actions']:
        print(f\"  → {action}\")
if 'rag_sources' in data['metadata']:
    print(\"\nDocuments Consulted:\")
    for src in data['metadata']['rag_sources']:
        print(f\"  📖 {src['source']} (relevance: {src['relevance']:.1%})\")
"
echo ""

echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  RAG Intelligence Demo Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "Key Takeaways:"
echo "  ✅ AI analyzes incidents using RAG-retrieved documentation"
echo "  ✅ Relevance scores ensure best documents are used"
echo "  ✅ Context-aware recommendations based on real manuals"
echo "  ✅ Transparent sourcing - shows which docs were consulted"
echo ""
echo "To add more documents:"
echo "  python scripts/ingest-docs.py --docs-dir /path/to/pdfs"
echo ""
echo "Current documents in RAG:"
echo "  • Aqara Water Leak Sensor Manual"
echo "  • Plumbing Emergency Guide"
echo "  • Water Heater Maintenance Manual"
echo "  • International Residential Code (IRC) - Plumbing"
echo "  • Home Winterization Guide"
echo ""
