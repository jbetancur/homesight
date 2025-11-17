# HomeSight API Reference

## Base URL

```
http://localhost:8000
```

## Authentication

Currently no authentication (local-only deployment). Authentication can be added via middleware in `internal/api/server.go`.

---

## Endpoints

### Health Check

#### `GET /health`

Returns service health status.

**Response:**
```json
{
  "status": "healthy",
  "time": "2024-01-01T12:00:00Z"
}
```

---

### Incidents

#### `GET /incidents`

List all incidents with optional filtering.

**Query Parameters:**
- `status` (optional): Filter by status (`open`, `acknowledged`, `resolved`)

**Response:**
```json
[
  {
    "id": "leak_sensor_1_1234567890",
    "title": "Water Leak Detected",
    "description": "Leak sensor detected water in basement",
    "severity": "critical",
    "status": "open",
    "device_id": "sensor_1",
    "sensor_id": "sensor_1",
    "zone_id": "basement",
    "asset_id": "",
    "rule_name": "leak_detection",
    "data": {
      "detected_at": "2024-01-01T12:00:00Z"
    },
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:00:00Z",
    "resolved_at": null
  }
]
```

#### `GET /incidents/{id}`

Get a specific incident by ID.

**Response:**
```json
{
  "id": "leak_sensor_1_1234567890",
  "title": "Water Leak Detected",
  ...
}
```

#### `POST /incidents/{id}/resolve`

Mark an incident as resolved.

**Response:**
```json
{
  "status": "resolved"
}
```

---

### Devices

#### `GET /devices`

List all registered devices.

**Response:**
```json
[
  {
    "id": "device_1",
    "name": "Basement Leak Sensor",
    "type": "leak_sensor",
    "integration": "zigbee",
    "zone_id": "basement",
    "asset_id": "",
    "enabled": true,
    "last_seen": "2024-01-01T12:00:00Z",
    "metadata": {},
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T12:00:00Z"
  }
]
```

#### `GET /devices/{id}`

Get a specific device by ID.

**Response:**
```json
{
  "id": "device_1",
  "name": "Basement Leak Sensor",
  ...
}
```

---

### Metrics

#### `GET /metrics/{sensorID}`

Query time-series metrics for a sensor.

**Query Parameters:**
- `from` (optional): Start time in RFC3339 format (default: 24h ago)
- `to` (optional): End time in RFC3339 format (default: now)

**Example:**
```
GET /metrics/sensor_1?from=2024-01-01T00:00:00Z&to=2024-01-01T12:00:00Z
```

**Response:**
```json
[
  {
    "timestamp": "2024-01-01T10:00:00Z",
    "value": 23.5,
    "labels": {
      "sensor_id": "sensor_1",
      "type": "temperature"
    }
  },
  {
    "timestamp": "2024-01-01T11:00:00Z",
    "value": 24.1,
    "labels": {
      "sensor_id": "sensor_1",
      "type": "temperature"
    }
  }
]
```

---

### AI Services

#### `POST /ai/chat`

Send a message to the AI assistant.

**Request:**
```json
{
  "message": "How do I winterize my pipes?",
  "context": {
    "zone": "basement",
    "temperature": 35
  }
}
```

**Response:**
```json
{
  "response": "To winterize your pipes, especially in areas where the temperature is near freezing (like your basement at 35°F), follow these steps:\n\n1. Insulate exposed pipes with foam pipe insulation\n2. Keep cabinet doors open to allow warm air circulation\n3. Let faucets drip slightly during extreme cold\n4. Maintain thermostat at minimum 55°F\n5. Seal any air leaks near pipes"
}
```

#### `POST /ai/analyze`

Request AI analysis of metrics or incidents.

**Request (Incident Analysis):**
```json
{
  "type": "incident",
  "data": {
    "type": "leak_detected",
    "severity": "critical",
    "location": "basement"
  },
  "context": {
    "recent_weather": "heavy_rain"
  }
}
```

**Response:**
```json
{
  "analysis": "Incident Analysis: leak_detected (Severity: critical)",
  "insights": [
    "Water leak detected - potential for property damage",
    "Recent heavy rain may have contributed to the issue"
  ],
  "actions": [
    "Locate and shut off water source immediately",
    "Check for visible damage and call plumber if needed",
    "Document damage for insurance purposes",
    "Inspect drainage systems after rain events"
  ],
  "metadata": {
    "type": "leak_detected",
    "severity": "critical"
  }
}
```

**Request (Metrics Analysis):**
```json
{
  "type": "metrics",
  "data": {
    "sensor_id": "temp_sensor_1",
    "values": [65.2, 64.8, 64.5, 45.2, 44.8, 44.5]
  }
}
```

**Response:**
```json
{
  "analysis": "Analyzed 6 readings from sensor temp_sensor_1.",
  "insights": [
    "Detected drop in readings (min: 44.50, avg: 54.83)"
  ],
  "actions": [
    "Investigate sensor for potential issues"
  ],
  "metadata": {
    "sensor_id": "temp_sensor_1",
    "samples": 6
  }
}
```

---

## Error Responses

All endpoints return standard HTTP error codes:

**400 Bad Request:**
```json
{
  "error": "Invalid request format"
}
```

**404 Not Found:**
```json
{
  "error": "Resource not found"
}
```

**500 Internal Server Error:**
```json
{
  "error": "Internal server error: details"
}
```

---

## Rate Limiting

Currently no rate limiting implemented. For production use, add rate limiting middleware.

## WebSocket Support

WebSocket support for real-time events can be added in future versions.
