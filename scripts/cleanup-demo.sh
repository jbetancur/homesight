#!/bin/bash
# Cleanup demo data

API_URL="http://localhost:8080"

echo "🧹 Cleaning up demo data..."
echo ""

# Delete all demo devices
echo "Removing devices..."
curl -s -X DELETE $API_URL/devices/basement-leak-sensor-001
curl -s -X DELETE $API_URL/devices/sump-pump-monitor-001
curl -s -X DELETE $API_URL/devices/basement-temp-sensor-001
curl -s -X DELETE $API_URL/devices/attic-temp-sensor-001
curl -s -X DELETE $API_URL/devices/front-door-sensor-001
curl -s -X DELETE $API_URL/devices/garage-door-sensor-001

echo ""
echo "Deleting incidents..."
curl -s -X DELETE $API_URL/incidents/incident-water-001
curl -s -X DELETE $API_URL/incidents/incident-battery-001

echo ""
echo "✅ Demo cleanup complete!"
echo ""
echo "Remaining devices:"
curl -s $API_URL/devices | python3 -m json.tool 2>/dev/null || cat
echo ""
echo "Remaining incidents:"
curl -s $API_URL/incidents | python3 -m json.tool 2>/dev/null || cat
echo ""
