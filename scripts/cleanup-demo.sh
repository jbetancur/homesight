#!/bin/bash
# Cleanup demo data - deletes all devices and incidents

API_URL="http://localhost:8080/api"

echo "🧹 Cleaning up all demo data..."
echo ""

# Get all devices and delete them
echo "Fetching all devices..."
DEVICES=$(curl -s $API_URL/devices)
DEVICE_IDS=$(echo "$DEVICES" | python3 -c "import sys, json; data = json.load(sys.stdin); print(' '.join([d['id'] for d in data]))" 2>/dev/null)

if [ -n "$DEVICE_IDS" ]; then
    echo "Removing $(echo $DEVICE_IDS | wc -w) devices..."
    for device_id in $DEVICE_IDS; do
        echo "  - Deleting device: $device_id"
        curl -s -X DELETE "$API_URL/devices/$device_id" > /dev/null
    done
else
    echo "No devices to delete"
fi

echo ""
echo "Fetching all incidents..."
INCIDENTS=$(curl -s $API_URL/incidents)
INCIDENT_IDS=$(echo "$INCIDENTS" | python3 -c "import sys, json; data = json.load(sys.stdin); print(' '.join([i['id'] for i in data]))" 2>/dev/null)

if [ -n "$INCIDENT_IDS" ]; then
    echo "Removing $(echo $INCIDENT_IDS | wc -w) incidents..."
    for incident_id in $INCIDENT_IDS; do
        echo "  - Deleting incident: $incident_id"
        curl -s -X DELETE "$API_URL/incidents/$incident_id" > /dev/null
    done
else
    echo "No incidents to delete"
fi

echo ""
echo "✅ Demo cleanup complete!"
echo ""
echo "Verifying cleanup..."
echo "Remaining devices: $(curl -s $API_URL/devices | python3 -c 'import sys, json; print(len(json.load(sys.stdin)))' 2>/dev/null || echo 'unknown')"
echo "Remaining incidents: $(curl -s $API_URL/incidents | python3 -c 'import sys, json; print(len(json.load(sys.stdin)))' 2>/dev/null || echo 'unknown')"
echo ""
