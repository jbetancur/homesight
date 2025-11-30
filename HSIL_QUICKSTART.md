# HSIL Quick Start Guide

**Get your HomeSight Intelligence Layer running in 5 minutes!**

---

## 🚀 Step 1: Start the System

```bash
cd /home/homesight/homesight
docker-compose up -d
```

Wait ~30 seconds for services to initialize.

---

## ✅ Step 2: Verify HSIL is Running

```bash
curl http://localhost:8001/health
```

Expected output:
```json
{
  "status": "healthy",
  "llm": {"available": true},
  "rag": {"available": true}
}
```

---

## 🧪 Step 3: Run Tests

```bash
./test_hsil.sh
```

This will:
- Test all HSIL endpoints
- Send sample sensor events
- Build initial baselines
- Verify learning is working

Expected: `All HSIL tests passed! 🎉`

---

## 📊 Step 4: Open Dashboard

Navigate to: **http://localhost:3000/hsil**

You should see:
- Device tiles (will populate as you send events)
- Learning statistics
- Chat interface (brain icon in top right)

---

## 💬 Step 5: Chat with Your Home

Try these commands in the dashboard chat or via curl:

```bash
# Ask about temperature
curl -X POST http://localhost:8001/hsil/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the temperature?"}'

# Express discomfort
curl -X POST http://localhost:8001/hsil/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I am cold"}'

# Check system status
curl -X POST http://localhost:8001/hsil/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How is my home?"}'
```

---

## 📈 Step 6: Send Real Sensor Data

### Option A: From Your Go Backend

Add this to your event processor:

```go
import (
    "bytes"
    "encoding/json"
    "net/http"
)

func forwardToHSIL(deviceID, eventType string, value interface{}, location string) {
    payload := map[string]interface{}{
        "device_id":   deviceID,
        "sensor_id":   deviceID,
        "event_type":  eventType,
        "value":       value,
        "location":    location,
        "device_type": determineDeviceType(eventType),
    }

    jsonData, _ := json.Marshal(payload)

    go func() {
        http.Post(
            "http://localhost:8001/hsil/events",
            "application/json",
            bytes.NewBuffer(jsonData),
        )
    }()
}
```

### Option B: Manual Test

```bash
# Send temperature reading
curl -X POST http://localhost:8001/hsil/events \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "sensor-living-room",
    "sensor_id": "temp",
    "event_type": "temperature",
    "value": 70.5,
    "location": "Living Room",
    "device_type": "temp_sensor"
  }'

# Send humidity reading
curl -X POST http://localhost:8001/hsil/events \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "sensor-living-room",
    "sensor_id": "humidity",
    "event_type": "humidity",
    "value": 45,
    "location": "Living Room",
    "device_type": "humidity_sensor"
  }'

# Send leak detection
curl -X POST http://localhost:8001/hsil/events \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "sensor-basement",
    "sensor_id": "leak",
    "event_type": "leak",
    "value": false,
    "location": "Basement",
    "device_type": "leak_sensor"
  }'
```

---

## 📊 Step 7: Monitor Learning

```bash
# Check statistics
curl http://localhost:8001/hsil/stats

# Check learned preferences
curl http://localhost:8001/hsil/preferences

# Check home state
curl http://localhost:8001/hsil/state
```

---

## 🎓 What Happens Next?

### First 24 Hours
- HSIL observes sensor patterns
- Builds statistical baselines
- No automated actions yet

### Days 2-7
- User preferences recorded
- Comfort ranges established
- Low-confidence suggestions

### Week 2+
- Proactive adjustments begin
- High-confidence actions
- Continuous improvement

---

## 🐛 Troubleshooting

### Problem: Health check fails

```bash
docker logs homesight-ai-sidecar | tail -50
```

Check for:
- Port 8001 already in use
- OpenAI API key missing/invalid
- ChromaDB initialization errors

### Problem: No learning happening

```bash
curl http://localhost:8001/hsil/stats
```

If `device_baselines_learned` is 0:
- Events not being sent
- Check event format
- Verify `device_id` and `value` fields present

### Problem: Chat not working

Check:
- OpenAI API key in `.env`
- LLM provider initialized: `curl http://localhost:8001/health`
- Logs: `docker logs homesight-ai-sidecar | grep LLM`

---

## 📖 Next Steps

1. **Read Full Docs**: [docs/HSIL_README.md](docs/HSIL_README.md)
2. **Implementation Details**: [docs/HSIL_IMPLEMENTATION_SUMMARY.md](docs/HSIL_IMPLEMENTATION_SUMMARY.md)
3. **Integration Guide**: See "From Your Go Backend" section above
4. **API Reference**: See HSIL_README.md

---

## 🎯 Quick Reference

| Task | Command |
|------|---------|
| Start system | `docker-compose up -d` |
| Run tests | `./test_hsil.sh` |
| Check health | `curl http://localhost:8001/health` |
| Send event | `curl -X POST http://localhost:8001/hsil/events -d '{...}'` |
| Chat | `curl -X POST http://localhost:8001/hsil/chat -d '{"message":"..."}'` |
| View stats | `curl http://localhost:8001/hsil/stats` |
| Dashboard | http://localhost:3000/hsil |
| Logs | `docker logs homesight-ai-sidecar` |

---

## ✅ Success Criteria

You're ready when:
- [ ] Health check returns `"status": "healthy"`
- [ ] Test script passes all tests
- [ ] Dashboard loads at /hsil
- [ ] Can send sensor events successfully
- [ ] Chat responds to queries
- [ ] Stats show baselines increasing

---

**Need Help?** Check the logs first:
```bash
docker logs homesight-ai-sidecar --tail 100
```

**Everything working?** Start sending real sensor data and watch HSIL learn! 🎉
