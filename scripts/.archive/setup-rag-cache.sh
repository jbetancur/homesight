#!/bin/bash

# Quick Start: Setting Up RAG with Your Devices
# This script helps you organize and ingest manufacturer docs for your actual devices

set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

CACHE_DIR="${HOME}/.homesight/manuals"

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  HomeSight RAG Setup - Manual Document Organization${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Create cache directory structure
echo -e "${YELLOW}📁 Creating manual cache directory structure${NC}"
mkdir -p "${CACHE_DIR}"/{aqara,shelly,sonoff,tuya,generic}

echo "Created:"
echo "  ${CACHE_DIR}/aqara/     - For Aqara device manuals"
echo "  ${CACHE_DIR}/shelly/    - For Shelly device manuals"
echo "  ${CACHE_DIR}/sonoff/    - For Sonoff device manuals"
echo "  ${CACHE_DIR}/tuya/      - For Tuya device manuals"
echo "  ${CACHE_DIR}/generic/   - For general guides (plumbing, HVAC, etc.)"
echo ""

# Create a README in the cache dir
cat > "${CACHE_DIR}/README.md" << 'EOF'
# HomeSight Manual Cache

Organize your device manuals here for automatic RAG ingestion.

## Directory Structure

```
aqara/      - Aqara device manuals (water leak sensors, temp sensors, etc.)
shelly/     - Shelly device manuals (relays, sensors, plugs)
sonoff/     - Sonoff device manuals (switches, sensors)
tuya/       - Tuya device manuals
generic/    - General home maintenance guides
```

## Where to Download Manuals

### Aqara
- Official site: https://www.aqara.com/us/support/download.html
- Look for your model (e.g., SJCGQ11LM for water leak sensor)
- Download PDF to `aqara/` folder

### Shelly
- Official site: https://kb.shelly.cloud/knowledge-base/
- Search for your device model
- Download user guide to `shelly/` folder

### Generic Guides
Free sources for home maintenance documentation:
- https://www.familyhandyman.com/
- https://www.thisoldhouse.com/
- https://www.homerepairtutor.com/
- Save as PDFs to `generic/` folder

## Ingesting Documents

After adding PDFs, run:

```bash
# Ingest all documents
python scripts/ingest-docs.py --docs-dir ~/.homesight/manuals

# Or ingest specific manufacturer
python scripts/ingest-docs.py --docs-dir ~/.homesight/manuals/aqara
```

## Naming Convention

Use descriptive filenames:
- `aqara-water-leak-sensor-SJCGQ11LM.pdf`
- `shelly-1pm-relay-manual.pdf`
- `plumbing-emergency-guide.pdf`
- `water-heater-maintenance.pdf`
EOF

echo -e "${GREEN}✅ Cache directory created at: ${CACHE_DIR}${NC}"
echo ""

# Provide download links for common devices
echo -e "${YELLOW}📚 Common Device Manual Downloads${NC}"
echo ""
echo "Aqara Water Leak Sensor (SJCGQ11LM):"
echo "  https://www.aqara.com/us/support/download.html"
echo ""
echo "Aqara Temperature & Humidity Sensor (WSDCGQ11LM):"
echo "  https://www.aqara.com/us/support/download.html"
echo ""
echo "Shelly 1PM Relay:"
echo "  https://kb.shelly.cloud/knowledge-base/shelly-1-1pm"
echo ""
echo "Shelly Door/Window Sensor:"
echo "  https://kb.shelly.cloud/knowledge-base/shelly-door-window"
echo ""

# Check if user wants to ingest sample docs
echo -e "${YELLOW}Would you like to ingest the sample documents now?${NC}"
echo "This includes:"
echo "  • Aqara Water Leak Sensor Manual"
echo "  • Plumbing Emergency Guide"
echo "  • Water Heater Maintenance"
echo "  • Home Winterization Guide"
echo "  • Building Code References"
echo ""
read -p "Ingest sample docs? (y/n) " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo -e "${BLUE}Ingesting sample documents...${NC}"
    cd "$(dirname "$0")/.."
    python scripts/ingest-docs.py --sample
    
    echo ""
    echo -e "${GREEN}✅ Sample documents ingested!${NC}"
    echo ""
    echo "Check RAG status:"
    echo "  curl http://localhost:8001/rag/status"
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Setup Complete!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "Next steps:"
echo ""
echo "1. Download manuals for YOUR devices:"
echo "   • Visit manufacturer support sites"
echo "   • Save PDFs to: ${CACHE_DIR}/<manufacturer>/"
echo ""
echo "2. Ingest your manuals:"
echo "   python scripts/ingest-docs.py --docs-dir ${CACHE_DIR}"
echo ""
echo "3. Test RAG with your device:"
echo "   curl -X POST http://localhost:8001/analyze \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"type\": \"incident\", \"data\": {...}}'"
echo ""
echo "4. Run the demo:"
echo "   ./scripts/demo-rag.sh"
echo ""
echo "📖 Full documentation: docs/RAG_AUTO_INGESTION.md"
echo ""
