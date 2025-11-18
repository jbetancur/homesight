#!/bin/bash
# Test auto-resolution of incidents

API_URL="http://localhost:8080/api"

echo "🧪 Testing Auto-Resolution Feature"
echo "==================================="
echo ""

# Step 1: Create a test device
echo "Step 1: Creating test leak sensor..."
curl -s -X POST $API_URL/devices \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test-leak-sensor",
    "name": "Test Leak Sensor",
    "type": "water_leak",
    "integration": "zigbee2mqtt",
    "enabled": true
  }' | python3 -m json.tool 2>/dev/null || cat
echo ""

# Step 2: Simulate leak detected - should create incident
echo ""
echo "Step 2: Simulating LEAK DETECTED (leak=true)..."
echo "Expected: New incident created"
curl -s -X POST $API_URL/events \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "test-leak-sensor",
    "sensor_id": "test-leak-sensor",
    "value": true,
    "value_type": "bool",
    "metadata": {
      "type": "leak_sensor"
    }
  }' 2>/dev/null

sleep 1
echo ""
echo "Current incidents:"
curl -s $API_URL/incidents | python3 -m json.tool 2>/dev/null || cat
echo ""

# Step 3: Simulate leak cleared - should auto-resolve
echo ""
echo "Step 3: Simulating LEAK CLEARED (leak=false)..."
echo "Expected: Incident auto-resolved"
curl -s -X POST $API_URL/events \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "test-leak-sensor",
    "sensor_id": "test-leak-sensor",
    "value": false,
    "value_type": "bool",
    "metadata": {
      "type": "leak_sensor"
    }
  }' 2>/dev/null

sleep 1
echo ""
echo "Incidents after resolution:"
curl -s $API_URL/incidents | python3 -m json.tool 2>/dev/null || cat
echo ""

# Cleanup
echo ""
echo "Cleaning up test device..."
curl -s -X DELETE $API_URL/devices/test-leak-sensor

# Clean up any test incidents
echo "Cleaning up test incidents..."
INCIDENT_IDS=$(curl -s $API_URL/incidents | python3 -c "import sys, json; [print(i['ID']) for i in json.load(sys.stdin) if 'test-leak-sensor' in i.get('DeviceID', '')]" 2>/dev/null)
for id in $INCIDENT_IDS; do
  curl -s -X DELETE $API_URL/incidents/$id
done

echo ""
echo "✅ Test complete!"
