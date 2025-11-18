#!/bin/bash
# Demo script to populate test data

echo "🏠 Creating demo data for HomeSight..."

API_URL="http://localhost:8080/api"

# Note: The current API only has GET endpoints for devices and incidents
# In a real scenario, we'd add POST endpoints to create devices
# For now, let's show what the dashboard would look like with mock data

echo ""
echo "The dashboard will show:"
echo "  ✅ System status (healthy)"
echo "  📱 Connected devices (when discovered via integrations)"
echo "  🚨 Active incidents (when detected by rules)"
echo ""
echo "To see devices and incidents:"
echo "  1. Connect MQTT devices to tcp://localhost:1883"
echo "  2. Configure Zigbee2MQTT to use the MQTT broker"
echo "  3. Add LAN devices with REST endpoints"
echo ""
echo "Try the dashboard now:"
echo "  ./scripts/homesight.sh dashboard"
echo ""
echo "Or check the current status:"
echo "  ./scripts/homesight.sh status"
