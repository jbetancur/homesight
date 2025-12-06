#!/bin/bash
# Bootstrap default zone attribute definitions
# This converts hardcoded ZoneAttributes to dynamic schema

API_URL="http://localhost:8080"

echo "Bootstrapping zone attribute definitions..."

# Floor-related attributes
curl -s -X POST "$API_URL/api/zone-attributes/definitions" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "floor_type",
    "label": "Floor Type",
    "type": "select",
    "scope": "zone",
    "category": "Construction",
    "description": "Type of flooring material",
    "options": ["hardwood", "tile", "carpet", "concrete", "laminate", "vinyl"]
  }'

curl -s -X POST "$API_URL/api/zone-attributes/definitions" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "square_feet",
    "label": "Square Feet",
    "type": "number",
    "scope": "zone",
    "category": "Dimensions",
    "description": "Total square footage of the zone"
  }'

# Features
curl -s -X POST "$API_URL/api/zone-attributes/definitions" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "has_windows",
    "label": "Has Windows",
    "type": "boolean",
    "scope": "zone",
    "category": "Features",
    "description": "Whether the zone has windows"
  }'

curl -s -X POST "$API_URL/api/zone-attributes/definitions" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "has_hvac_return",
    "label": "Has HVAC Return",
    "type": "boolean",
    "scope": "zone",
    "category": "HVAC",
    "description": "Whether the zone has HVAC return vent"
  }'

curl -s -X POST "$API_URL/api/zone-attributes/definitions" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "has_plumbing",
    "label": "Has Plumbing",
    "type": "boolean",
    "scope": "zone",
    "category": "Infrastructure",
    "description": "Whether the zone has plumbing fixtures"
  }'

curl -s -X POST "$API_URL/api/zone-attributes/definitions" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "has_fireplace",
    "label": "Has Fireplace",
    "type": "boolean",
    "scope": "zone",
    "category": "Features",
    "description": "Whether the zone has a fireplace"
  }'

curl -s -X POST "$API_URL/api/zone-attributes/definitions" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "has_valuables",
    "label": "Has Valuables",
    "type": "boolean",
    "scope": "zone",
    "category": "Security",
    "description": "Whether the zone contains valuable items"
  }'

curl -s -X POST "$API_URL/api/zone-attributes/definitions" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "has_pets",
    "label": "Has Pets",
    "type": "boolean",
    "scope": "zone",
    "category": "Occupancy",
    "description": "Whether pets frequently use this zone"
  }'

curl -s -X POST "$API_URL/api/zone-attributes/definitions" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "access_frequency",
    "label": "Access Frequency",
    "type": "select",
    "scope": "zone",
    "category": "Usage",
    "description": "How often the zone is accessed",
    "options": ["rarely", "occasional", "frequent", "constant"]
  }'

curl -s -X POST "$API_URL/api/zone-attributes/definitions" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "moisture_prone",
    "label": "Moisture Prone",
    "type": "boolean",
    "scope": "zone",
    "category": "Environment",
    "description": "Whether the zone is prone to moisture issues"
  }'

echo "✅ Zone attribute definitions bootstrapped!"

echo ""
echo "Fetching attribute definitions..."
curl -s "$API_URL/api/zone-attributes/definitions?scope=zone" | jq '.[] | {name: .name, label: .label, type: .type, category: .category}'
