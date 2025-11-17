#!/bin/bash
# MQTT Monitor - Listen for device messages and show what's on the broker

BROKER="localhost"
PORT="1883"
TIMEOUT=30

echo "🔍 MQTT Device Monitor"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Broker: $BROKER:$PORT"
echo "Listening for $TIMEOUT seconds..."
echo "Press Ctrl+C to stop early"
echo ""
echo "Common MQTT topics to look for:"
echo "  • zigbee2mqtt/#          - Zigbee2MQTT devices"
echo "  • tasmota/#              - Tasmota devices"
echo "  • homeassistant/#        - Home Assistant MQTT"
echo "  • shellies/#             - Shelly devices"
echo "  • esphome/#              - ESPHome devices"
echo ""
echo "Waiting for messages..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

timeout $TIMEOUT mosquitto_sub -h $BROKER -p $PORT -t '#' -v 2>&1 | while read -r line; do
    timestamp=$(date '+%H:%M:%S')
    echo "[$timestamp] $line"
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Monitoring complete."
echo ""
echo "If no messages appeared, your MQTT devices may:"
echo "  1. Not be configured to use this broker (tcp://$BROKER:$PORT)"
echo "  2. Be on a different network/VLAN"
echo "  3. Not be actively publishing messages"
echo ""
echo "To test manually, publish a test message:"
echo "  mosquitto_pub -h $BROKER -p $PORT -t 'test/device' -m '{\"status\":\"online\"}'"
