#!/bin/bash
# Bootstrap default zones
# Creates minimal zone structure - users configure attributes separately

API_URL="http://localhost:8080"

echo "Bootstrapping default zones..."

# Living Room
curl -s -X POST "$API_URL/api/zones" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "living-room",
    "name": "Living Room",
    "type": "living_room",
    "home_id": "default"
  }'

# Kitchen
curl -s -X POST "$API_URL/api/zones" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "kitchen",
    "name": "Kitchen",
    "type": "kitchen",
    "home_id": "default"
  }'

# Bedroom
curl -s -X POST "$API_URL/api/zones" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "bedroom",
    "name": "Bedroom",
    "type": "bedroom",
    "home_id": "default"
  }'

# Bathroom
curl -s -X POST "$API_URL/api/zones" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "bathroom",
    "name": "Bathroom",
    "type": "bathroom",
    "home_id": "default"
  }'

# Basement
curl -s -X POST "$API_URL/api/zones" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "basement",
    "name": "Basement",
    "type": "basement",
    "home_id": "default"
  }'

# Garage
curl -s -X POST "$API_URL/api/zones" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "garage",
    "name": "Garage",
    "type": "garage",
    "home_id": "default"
  }'


echo "✅ Default zones bootstrapped!"

echo ""
echo "Fetching zones..."
curl -s "$API_URL/api/zones" | jq '.[] | {id: .id, name: .name, type: .type, attributes: (.attributes | length)}'
