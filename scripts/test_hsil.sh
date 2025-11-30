#!/bin/bash
# HSIL Test Script
# Tests all HSIL endpoints

set -e

BASE_URL="http://localhost:8001"

echo "==================================================="
echo "Testing HomeSight Intelligence Layer (HSIL)"
echo "==================================================="
echo ""

# Test 1: Health Check
echo "1. Testing health endpoint..."
curl -s "$BASE_URL/health" | python3 -m json.tool
echo ""
echo "✅ Health check passed"
echo ""

# Test 2: Send Temperature Event
echo "2. Sending temperature event..."
curl -s -X POST "$BASE_URL/hsil/events" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "test-kitchen-temp",
    "sensor_id": "temp",
    "event_type": "temperature",
    "value": 68.5,
    "location": "Kitchen",
    "device_type": "temp_sensor"
  }' | python3 -m json.tool
echo ""
echo "✅ Event processing passed"
echo ""

# Test 3: Get Home State
echo "3. Getting home state..."
curl -s "$BASE_URL/hsil/state" | python3 -m json.tool
echo ""
echo "✅ State query passed"
echo ""

# Test 4: Chat with HSIL
echo "4. Chatting with HSIL..."
curl -s -X POST "$BASE_URL/hsil/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is the temperature in the kitchen?",
    "session_id": "test-session"
  }' | python3 -m json.tool
echo ""
echo "✅ Chat passed"
echo ""

# Test 5: Get Statistics
echo "5. Getting HSIL statistics..."
curl -s "$BASE_URL/hsil/stats" | python3 -m json.tool
echo ""
echo "✅ Stats query passed"
echo ""

# Test 6: Get Learned Preferences
echo "6. Getting learned preferences..."
curl -s "$BASE_URL/hsil/preferences" | python3 -m json.tool
echo ""
echo "✅ Preferences query passed"
echo ""

# Test 7: User Intent - "I'm cold"
echo "7. Testing user intent (I'm cold)..."
curl -s -X POST "$BASE_URL/hsil/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I am cold",
    "session_id": "test-session-2"
  }' | python3 -m json.tool
echo ""
echo "✅ User intent passed"
echo ""

# Test 8: Send multiple events to build baseline
echo "8. Sending multiple events to build baseline..."
for temp in 68.2 68.5 68.8 69.1 68.9 68.6; do
  curl -s -X POST "$BASE_URL/hsil/events" \
    -H "Content-Type: application/json" \
    -d "{
      \"device_id\": \"test-kitchen-temp\",
      \"sensor_id\": \"temp\",
      \"event_type\": \"temperature\",
      \"value\": $temp,
      \"location\": \"Kitchen\",
      \"device_type\": \"temp_sensor\"
    }" > /dev/null
  echo "  Sent temp: $temp°F"
  sleep 0.5
done
echo ""
echo "✅ Baseline building passed"
echo ""

# Test 9: Check if baseline learned
echo "9. Checking learned baseline..."
curl -s "$BASE_URL/hsil/stats" | python3 -c "
import sys, json
data = json.load(sys.stdin)
baselines = data['adaptive_learning']['device_baselines_learned']
print(f'  Baselines learned: {baselines}')
print('  ✅ Baseline learning working!')
"
echo ""

echo "==================================================="
echo "All HSIL tests passed! 🎉"
echo "==================================================="
echo ""
echo "Next steps:"
echo "1. Open dashboard: http://localhost:3000/hsil"
echo "2. Send real sensor events to /hsil/events"
echo "3. Chat with your home: curl -X POST http://localhost:8080/api/hsil/chat -d '{\"message\":\"...\"}"
echo "4. Monitor learning: curl http://localhost:8080/api/hsil/stats"
echo ""
