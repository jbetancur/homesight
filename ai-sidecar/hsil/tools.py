"""
HSIL Tool Registry

Defines tools that the LLM can orchestrate.
Each tool is a deterministic function the LLM can invoke.
"""

from typing import Any, Dict, List, Callable, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class ToolParameter:
    """Definition of a tool parameter"""
    name: str
    type: str  # "string", "number", "boolean", "array"
    description: str
    required: bool = True
    enum: Optional[List[str]] = None


@dataclass
class Tool:
    """Definition of a callable tool"""
    name: str
    description: str
    parameters: List[ToolParameter]
    function: Callable


class ToolRegistry:
    """
    Registry of tools available to the LLM orchestrator.

    Architecture:
    - LLM selects which tools to invoke based on user query
    - Tools execute deterministically
    - Results returned to LLM for synthesis
    """

    def __init__(self, learning_engine=None, memory=None, db_path=None, ontology=None):
        self.learning_engine = learning_engine
        self.memory = memory
        self.db_path = db_path
        self.ontology = ontology
        self.tools: Dict[str, Tool] = {}

        # Register all tools
        self._register_tools()
        logger.info(f"✅ Tool registry initialized with {len(self.tools)} tools")

    def _register_tools(self):
        """Register all available tools"""

        # Anomaly detection tool
        self.register_tool(Tool(
            name="check_anomaly",
            description="Check if a device's current value is anomalous. Returns anomaly score and explanation.",
            parameters=[
                ToolParameter("device_id", "string", "The device ID to check"),
                ToolParameter("metric", "string", "The metric to check (e.g., 'temperature', 'humidity')"),
                ToolParameter("value", "number", "The current value to evaluate"),
            ],
            function=self._check_anomaly
        ))

        # Erratic behavior tool
        self.register_tool(Tool(
            name="check_erratic_behavior",
            description="Check if a device is exhibiting erratic behavior (rapid-fire events, unusual frequency).",
            parameters=[
                ToolParameter("device_id", "string", "The device ID to check", required=False),
            ],
            function=self._check_erratic_behavior
        ))

        # Get all erratic devices
        self.register_tool(Tool(
            name="get_erratic_devices",
            description="Get all devices currently exhibiting erratic behavior.",
            parameters=[],
            function=self._get_erratic_devices
        ))

        # Historical query tool
        self.register_tool(Tool(
            name="query_device_history",
            description="Query historical data for a device over a time period.",
            parameters=[
                ToolParameter("device_id", "string", "The device ID to query"),
                ToolParameter("hours_back", "number", "How many hours of history to retrieve", required=False),
            ],
            function=self._query_device_history
        ))

        # Comfort preferences
        self.register_tool(Tool(
            name="get_comfort_preferences",
            description="Get learned comfort preferences for a location (temperature, humidity).",
            parameters=[
                ToolParameter("location", "string", "The room/zone name", required=False),
            ],
            function=self._get_comfort_preferences
        ))

        # ML stats
        self.register_tool(Tool(
            name="get_ml_stats",
            description="Get machine learning model statistics and training progress.",
            parameters=[],
            function=self._get_ml_stats
        ))

        # Recent incidents
        self.register_tool(Tool(
            name="get_recent_incidents",
            description="Get recent incidents/alerts from the system.",
            parameters=[
                ToolParameter("limit", "number", "Maximum number of incidents to return", required=False),
                ToolParameter("severity", "string", "Filter by severity (critical, warning, info)", required=False),
            ],
            function=self._get_recent_incidents
        ))

        # Device-specific incidents
        self.register_tool(Tool(
            name="get_device_incidents",
            description="Get incident history for a specific device, including timestamps of anomalies/leaks. CRITICAL: Use this to detect FALSE POSITIVES or SENSOR MALFUNCTIONS by checking if multiple incidents occurred within seconds of each other (indicating sensor problems, not real events). This is more reliable than check_erratic_behavior for recent activity.",
            parameters=[
                ToolParameter("device_id", "string", "The device ID to query"),
                ToolParameter("limit", "number", "Maximum number of incidents to return", required=False),
            ],
            function=self._get_device_incidents
        ))

        # Device baseline
        self.register_tool(Tool(
            name="get_device_baseline",
            description="Get HISTORICAL learned baseline statistics (mean and variance) for a device metric from machine learning models. Use this for trend analysis, not current values. For current battery levels or sensor readings, use get_device_status instead.",
            parameters=[
                ToolParameter("device_id", "string", "The device ID"),
                ToolParameter("metric", "string", "The metric name (e.g., 'temperature')"),
            ],
            function=self._get_device_baseline
        ))

        # List devices by location/zone
        self.register_tool(Tool(
            name="list_devices",
            description="List ALL devices in a specific location/zone or list ALL devices in the entire home. Use this when users ask 'which sensors', 'what devices', 'list sensors', or 'show me devices' in a location. Returns device names, IDs, types, and zones.",
            parameters=[
                ToolParameter("zone", "string", "The zone/location name (e.g., 'basement', 'kitchen'). Leave empty to list ALL devices.", required=False),
            ],
            function=self._list_devices
        ))

        # Device status (current readings, battery, etc.)
        self.register_tool(Tool(
            name="get_device_status",
            description="Get CURRENT live status of a device including BATTERY LEVEL, sensor readings, state, and metadata. Use this when users ask about current battery levels, current readings, or device status. Returns real-time data from the device API, not historical baselines.",
            parameters=[
                ToolParameter("device_id", "string", "The device ID (e.g., 'zwave-31' for leak sensor)"),
            ],
            function=self._get_device_status
        ))

        # Device documentation / knowledge base
        self.register_tool(Tool(
            name="get_device_documentation",
            description="Get the FULL documentation, manual, specs, installation guide, and troubleshooting info for a device. ALWAYS use this when users ask about: 'documentation', 'manual', 'how to use', 'how does X work', 'help with device', 'instructions', 'specs', 'features', 'troubleshooting', or any device-related questions. Returns comprehensive manufacturer documentation.",
            parameters=[
                ToolParameter("device_id", "string", "The device ID (e.g., 'zwave-31' for leak sensor, 'zwave-1' for controller)"),
            ],
            function=self._get_device_documentation
        ))

        # List zones / rooms
        self.register_tool(Tool(
            name="list_zones",
            description="List ALL zones/rooms in the home with their IDs, names, types, and attributes. ALWAYS use this when users ask about rooms, zones, or use room names that might not exactly match (e.g., 'primary bedroom' vs 'master bedroom'). Returns all zone information including square footage and other attributes. Use this to find the correct zone ID before answering questions about specific rooms.",
            parameters=[
                ToolParameter("search", "string", "Optional search term to filter zones by name (e.g., 'bedroom', 'bath'). Leave empty to list all zones.", required=False),
            ],
            function=self._list_zones
        ))

        # Get sensor readings (time-series data)
        self.register_tool(Tool(
            name="get_sensor_readings",
            description="Get time-series sensor readings for any sensor type. Use this to see historical trends or recent values over time. Returns readings with timestamps for charting and analysis. Supports: temperature, humidity, water/leak, motion, contact, power, energy.",
            parameters=[
                ToolParameter("device_id", "string", "The device ID (e.g., 'zwave-31')"),
                ToolParameter("reading_type", "string", "The type of reading: 'temperature', 'humidity', 'water', 'motion', 'contact', 'power', 'energy' (default: 'temperature')", required=False),
                ToolParameter("hours_back", "number", "How many hours of history to retrieve (default: 24)", required=False),
            ],
            function=self._get_sensor_readings
        ))

        # Control devices
        self.register_tool(Tool(
            name="set_device_value",
            description="Control a device by setting an entity value (turn on/off lights, adjust thermostats, etc.). Use this when the user asks to control or change a device. Check device entities first to see which are settable.",
            parameters=[
                ToolParameter("device_id", "string", "The device ID (e.g., 'zwave-31')"),
                ToolParameter("entity_id", "string", "The entity ID to set (e.g., 'switch', 'targetValue')"),
                # OpenAI doesn't support "any" - use string to represent all value types
                # The API will handle type coercion (e.g., "true" -> boolean, "75" -> number)
                ToolParameter("value", "string", "The value to set. For switches: 'true' or 'false'. For numbers: '75', '68', etc. For strings: pass as-is."),
            ],
            function=self._set_device_value
        ))

        # List controllable devices
        self.register_tool(Tool(
            name="list_controllable_devices",
            description="List all devices that can be controlled (lights, switches, thermostats, valves). Use this to see what devices the user can control.",
            parameters=[],
            function=self._list_controllable_devices
        ))

        # Get device controls - shows what can be controlled on a specific device
        self.register_tool(Tool(
            name="get_device_controls",
            description="Get all controllable entities for a specific device (switches, valves, thermostats). ALWAYS use this before set_device_value to find the correct entity_id to control. Returns entity IDs, current values, and what they control.",
            parameters=[
                ToolParameter("device_id", "string", "The device ID (e.g., 'zwave-44')"),
            ],
            function=self._get_device_controls
        ))

    def register_tool(self, tool: Tool):
        """Register a tool in the registry"""
        self.tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        Get tool schemas in OpenAI function calling format.
        Used to tell the LLM what tools are available.
        """
        schemas = []
        for tool in self.tools.values():
            schema = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }

            for param in tool.parameters:
                schema["function"]["parameters"]["properties"][param.name] = {
                    "type": param.type,
                    "description": param.description
                }
                if param.enum:
                    schema["function"]["parameters"]["properties"][param.name]["enum"] = param.enum

                if param.required:
                    schema["function"]["parameters"]["required"].append(param.name)

            schemas.append(schema)

        return schemas

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool with given arguments.

        Returns:
            Dict with 'success', 'result', and optional 'error' keys
        """
        if tool_name not in self.tools:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}"
            }

        tool = self.tools[tool_name]

        try:
            logger.info(f"Executing tool: {tool_name} with args: {arguments}")
            result = await tool.function(**arguments)
            return {
                "success": True,
                "result": result
            }
        except Exception as e:
            logger.error(f"Tool execution error ({tool_name}): {e}")
            return {
                "success": False,
                "error": str(e)
            }

    # ==================== Tool Implementations ====================

    async def _check_anomaly(self, device_id: str, metric: str, value: float) -> Dict[str, Any]:
        """Check if a value is anomalous"""
        if not self.learning_engine:
            return {"error": "Learning engine not available"}

        is_anomalous, score = await self.learning_engine.is_anomalous(device_id, metric, value)

        # Get baseline for context
        baseline = await self._get_device_baseline(device_id, metric)

        return {
            "is_anomalous": is_anomalous,
            "anomaly_score": round(score, 3),
            "baseline": baseline,
            "interpretation": self._interpret_anomaly_score(score, is_anomalous)
        }

    async def _check_erratic_behavior(self, device_id: Optional[str] = None) -> Dict[str, Any]:
        """Check for erratic behavior.

        If `device_id` is provided, return stats for that device.
        If `device_id` is omitted (None), return a list/count of all erratic devices.
        """
        if not self.learning_engine:
            return {"error": "Learning engine not available"}

        # If no device_id supplied, return the global erratic devices list
        if not device_id:
            erratic = await self.learning_engine.get_all_erratic_devices()
            return {
                "count": len(erratic),
                "devices": erratic,
                "message": "Returned all erratic devices (no device_id supplied)"
            }

        # device_id supplied: return device-specific stats
        stats = await self.learning_engine.get_device_erratic_stats(device_id)

        if not stats:
            return {
                "is_erratic": False,
                "message": "No erratic behavior data available for this device",
                "device_id": device_id
            }

        return stats

    async def _get_erratic_devices(self) -> Dict[str, Any]:
        """Get all erratic devices"""
        if not self.learning_engine:
            return {"error": "Learning engine not available"}

        erratic = await self.learning_engine.get_all_erratic_devices()

        return {
            "count": len(erratic),
            "devices": erratic
        }

    async def _query_device_history(self, device_id: str, hours_back: int = 24) -> Dict[str, Any]:
        """Query device history"""
        if not self.memory:
            return {"error": "Memory service not available"}

        # This would query your memory/database for historical readings
        # Placeholder implementation
        return {
            "device_id": device_id,
            "hours_back": hours_back,
            "message": "Historical query not yet implemented"
        }

    async def _get_comfort_preferences(self, location: str = None) -> Dict[str, Any]:
        """Get comfort preferences"""
        if not self.learning_engine:
            return {"error": "Learning engine not available"}

        if not location:
            # Option 1: Return a user-friendly error
            return {"success": False, "error": "Missing required parameter: location. Please specify a room or zone name."}
            # Option 2: Or return global/default preferences if available
            # prefs = await self.learning_engine.get_comfort_preference(None)
            # if not prefs:
            #     return {"message": "No global comfort preferences learned yet."}
            # return prefs

        prefs = await self.learning_engine.get_comfort_preference(location)

        if not prefs:
            return {
                "location": location,
                "message": "No comfort preferences learned yet for this location"
            }

        return prefs

    async def _get_ml_stats(self) -> Dict[str, Any]:
        """Get ML statistics"""
        if not self.learning_engine:
            return {"error": "Learning engine not available"}

        stats = await self.learning_engine.get_stats()
        return stats

    async def _get_recent_incidents(self, limit: int = 10, severity: Optional[str] = None) -> Dict[str, Any]:
        """Get recent incidents"""
        import httpx
        from datetime import datetime

        try:
            async with httpx.AsyncClient() as client:
                # Query backend incidents API
                url = f"http://api:8080/api/incidents"
                resp = await client.get(url, timeout=5.0)

                if resp.status_code != 200:
                    return {"error": f"Failed to fetch incidents: {resp.status_code}"}

                all_incidents = resp.json()

                # Filter by severity if provided
                if severity:
                    all_incidents = [inc for inc in all_incidents if inc.get("severity") == severity.lower()]

                # Limit results
                incidents = all_incidents[:limit]

                # Format for LLM
                formatted = []
                for inc in incidents:
                    created_at = inc.get("created_at", "")
                    if created_at:
                        # Calculate time ago
                        try:
                            created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                            now = datetime.now(created_dt.tzinfo)
                            delta = now - created_dt

                            if delta.days > 0:
                                time_ago = f"{delta.days} days ago"
                            elif delta.seconds > 3600:
                                time_ago = f"{delta.seconds // 3600} hours ago"
                            elif delta.seconds > 60:
                                time_ago = f"{delta.seconds // 60} minutes ago"
                            else:
                                time_ago = f"{delta.seconds} seconds ago"
                        except Exception:
                            time_ago = "unknown"
                    else:
                        time_ago = "unknown"

                    formatted.append({
                        "id": inc.get("id"),
                        "device_id": inc.get("device_id"),
                        "title": inc.get("title"),
                        "description": inc.get("description"),
                        "severity": inc.get("severity"),
                        "status": inc.get("status"),
                        "zone_id": inc.get("zone_id"),
                        "created_at": created_at,
                        "time_ago": time_ago
                    })

                return {
                    "total_count": len(all_incidents),
                    "returned_count": len(formatted),
                    "incidents": formatted
                }
        except Exception as e:
            logger.error(f"Error fetching incidents: {e}")
            return {"error": str(e)}

    async def _get_device_incidents(self, device_id: str, limit: int = 10) -> Dict[str, Any]:
        """Get incident history for a specific device"""
        import httpx
        from datetime import datetime

        try:
            async with httpx.AsyncClient() as client:
                # Query backend incidents API
                url = f"http://api:8080/api/incidents"
                resp = await client.get(url, timeout=5.0)

                if resp.status_code != 200:
                    return {"error": f"Failed to fetch incidents: {resp.status_code}"}

                all_incidents = resp.json()

                # Filter by device_id
                device_incidents = [inc for inc in all_incidents if inc.get("device_id") == device_id]

                if not device_incidents:
                    return {
                        "device_id": device_id,
                        "count": 0,
                        "message": f"No incidents found for device {device_id}"
                    }

                # Limit results
                incidents = device_incidents[:limit]

                # Format for LLM
                formatted = []
                for inc in incidents:
                    created_at = inc.get("created_at", "")
                    if created_at:
                        # Calculate time ago
                        try:
                            created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                            now = datetime.now(created_dt.tzinfo)
                            delta = now - created_dt

                            if delta.days > 0:
                                time_ago = f"{delta.days} days ago"
                            elif delta.seconds > 3600:
                                time_ago = f"{delta.seconds // 3600} hours ago"
                            elif delta.seconds > 60:
                                time_ago = f"{delta.seconds // 60} minutes ago"
                            else:
                                time_ago = f"{delta.seconds} seconds ago"
                        except Exception:
                            time_ago = "unknown"
                    else:
                        time_ago = "unknown"

                    formatted.append({
                        "id": inc.get("id"),
                        "device_id": inc.get("device_id"),
                        "title": inc.get("title"),
                        "description": inc.get("description"),
                        "severity": inc.get("severity"),
                        "status": inc.get("status"),
                        "zone_id": inc.get("zone_id"),
                        "created_at": created_at,
                        "time_ago": time_ago
                    })

                return {
                    "device_id": device_id,
                    "total_count": len(device_incidents),
                    "returned_count": len(formatted),
                    "incidents": formatted,
                    **self._analyze_incident_pattern(formatted)
                }
        except Exception as e:
            logger.error(f"Error fetching device incidents: {e}")
            return {"error": str(e)}

    def _analyze_incident_pattern(self, incidents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze incident pattern to detect false positives or sensor malfunctions"""
        from datetime import datetime
        
        if len(incidents) < 2:
            return {
                "pattern_analysis": "Not enough incidents to detect pattern",
                "likely_false_positive": False
            }
        
        # Parse timestamps and calculate intervals
        timestamps = []
        for inc in incidents:
            created_at = inc.get("created_at", "")
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    timestamps.append(dt)
                except Exception:
                    pass
        
        if len(timestamps) < 2:
            return {
                "pattern_analysis": "Could not parse timestamps",
                "likely_false_positive": False
            }
        
        # Sort by time (most recent first)
        timestamps.sort(reverse=True)
        
        # Check for false positive pattern: multiple incidents within 10 seconds
        # This suggests sensor malfunction or interference, not real events
        consecutive_quick_triggers = 0
        for i in range(len(timestamps) - 1):
            delta = timestamps[i] - timestamps[i + 1]
            if delta.total_seconds() < 10:
                consecutive_quick_triggers += 1
        
        likely_false_positive = consecutive_quick_triggers >= 3  # 3+ incidents within 10 seconds each
        
        # Calculate average interval for recent incidents
        recent_intervals = []
        for i in range(min(5, len(timestamps) - 1)):
            delta = timestamps[i] - timestamps[i + 1]
            recent_intervals.append(delta.total_seconds())
        
        avg_interval = sum(recent_intervals) / len(recent_intervals) if recent_intervals else 0
        
        analysis = {
            "likely_false_positive": likely_false_positive,
            "suspicious_trigger_count": consecutive_quick_triggers,
            "average_interval_seconds": round(avg_interval, 1),
            "pattern_analysis": ""
        }
        
        if likely_false_positive:
            analysis["pattern_analysis"] = f"⚠️ LIKELY FALSE POSITIVE: {consecutive_quick_triggers} incidents triggered within seconds of each other (avg {avg_interval:.1f}s apart). This pattern suggests sensor malfunction or interference, not real events. Consider checking sensor battery, placement, or replacing the sensor."
        elif avg_interval < 60:
            analysis["pattern_analysis"] = f"⚠️ Frequent triggers: Incidents occurring every {avg_interval:.1f} seconds on average. May indicate high sensor sensitivity or need for adjustment."
        else:
            analysis["pattern_analysis"] = f"✅ Normal pattern: Incidents spaced reasonably apart ({avg_interval:.1f}s average). Sensor appears to be functioning correctly."
        
        return analysis

    async def _get_device_baseline(self, device_id: str, metric: str) -> Dict[str, Any]:
        """Get device baseline statistics"""
        if not self.learning_engine:
            return {"error": "Learning engine not available"}

        if device_id not in self.learning_engine.baseline_models:
            return {
                "device_id": device_id,
                "metric": metric,
                "message": "No baseline data available"
            }

        if metric not in self.learning_engine.baseline_models[device_id]:
            return {
                "device_id": device_id,
                "metric": metric,
                "message": f"No baseline for metric '{metric}'"
            }

        mean_model, var_model = self.learning_engine.baseline_models[device_id][metric]
        mean_val = mean_model.get()
        var_val = var_model.get()

        import math
        stddev = math.sqrt(var_val) if var_val and var_val > 0 else 0

        return {
            "device_id": device_id,
            "metric": metric,
            "mean": round(mean_val, 2) if mean_val else None,
            "stddev": round(stddev, 2),
            "variance": round(var_val, 2) if var_val else None,
            "samples": self.learning_engine.model_update_counts.get(f"baseline_{device_id}_{metric}", 0)
        }

    async def _list_devices(self, zone: Optional[str] = None) -> Dict[str, Any]:
        """List devices in a zone or all devices"""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                # Fetch zones first to build ID -> name mapping
                zones_url = "http://api:8080/api/zones"
                zones_resp = await client.get(zones_url, timeout=5.0)
                zone_map = {}  # zone_id -> zone_name
                if zones_resp.status_code == 200:
                    zones_data = zones_resp.json()
                    zone_map = {z.get("id"): z.get("name") for z in zones_data if z.get("id")}
                    logger.debug(f"Loaded {len(zone_map)} zones for name mapping")

                # Fetch devices
                devices_url = "http://api:8080/api/devices"
                resp = await client.get(devices_url, timeout=5.0)

                if resp.status_code != 200:
                    logger.error(f"Failed to fetch devices: {resp.status_code}")
                    return {"error": f"Failed to fetch devices: {resp.status_code}"}

                all_devices = resp.json()
                logger.info(f"Fetched {len(all_devices)} total devices from API")

                # Filter by zone if specified
                if zone:
                    zone_normalized = zone.lower().strip()

                    # Match against both zone_id and zone display name (fuzzy matching)
                    # Examples:
                    #   User: "basement" matches zone_id="basement" or name="Basement"
                    #   User: "attic office" matches zone_id="attic-office" or name="Attic Office"
                    devices = []
                    for d in all_devices:
                        zone_id = d.get("zone_id", "")
                        zone_name = zone_map.get(zone_id, "")

                        # Normalize with hyphens replaced by spaces for fuzzy matching
                        zone_id_normalized = zone_id.lower().replace("-", " ")
                        zone_name_normalized = zone_name.lower().replace("-", " ")

                        if zone_id_normalized == zone_normalized or zone_name_normalized == zone_normalized:
                            devices.append(d)

                    logger.info(f"Filtered to {len(devices)} devices in zone '{zone}' (normalized: '{zone_normalized}')")

                    if not devices:
                        # Log all available zones for debugging
                        available_zones = [f"{zid} ({zone_map.get(zid, zid)})" for zid in zone_map.keys()]
                        logger.warning(f"No devices found in zone '{zone}'. Available zones: {available_zones}")
                        return {
                            "zone": zone,
                            "count": 0,
                            "devices": [],
                            "message": f"No devices found in {zone}",
                            "available_zones": available_zones
                        }
                else:
                    devices = all_devices
                    logger.info(f"Returning all {len(devices)} devices (no zone filter)")

                # Format device list
                device_list = []
                for d in devices:
                    device_info = {
                        "device_id": d.get("id"),
                        "name": d.get("display_name") or d.get("name"),
                        "type": d.get("type"),
                        "zone": d.get("zone_id"),
                        "integration": d.get("integration"),
                    }

                    # Add manufacturer/model if available
                    metadata = d.get("metadata", {})
                    if metadata.get("manufacturer"):
                        device_info["manufacturer"] = metadata["manufacturer"]
                    if metadata.get("model"):
                        device_info["model"] = metadata["model"]

                    # Add battery level if available
                    if "battery_level" in d:
                        device_info["battery_level"] = d["battery_level"]

                    # CRITICAL: Add sensor capabilities so LLM knows what protection this provides
                    # Detect capabilities from readings/entities
                    capabilities = []
                    readings = d.get("readings", {})
                    entities = d.get("entities", [])

                    # Water/leak detection
                    if "water" in readings or any(e.get("id") == "Water Alarm" for e in entities):
                        capabilities.append("water_leak_detector")

                    # Temperature sensing
                    if "temperature" in readings or "temperature_f" in readings:
                        capabilities.append("temperature_sensor")

                    # Humidity sensing
                    if "humidity" in readings:
                        capabilities.append("humidity_sensor")

                    # Motion detection
                    if "motion" in readings or any(e.get("id") == "Motion" for e in entities):
                        capabilities.append("motion_sensor")

                    # Door/window sensors
                    if "door" in readings or "window" in readings:
                        capabilities.append("contact_sensor")

                    # Smoke/CO detection
                    if "smoke" in readings or any(e.get("id") == "Smoke" for e in entities):
                        capabilities.append("smoke_detector")
                    if "co" in readings or "carbon_monoxide" in readings:
                        capabilities.append("co_detector")

                    # Valve control
                    if any("valve" in e.get("id", "").lower() for e in entities):
                        capabilities.append("water_valve")

                    if capabilities:
                        device_info["capabilities"] = capabilities

                    device_list.append(device_info)

                result = {
                    "zone": zone or "all",
                    "count": len(device_list),
                    "devices": device_list
                }
                
                logger.info(f"list_devices returning {len(device_list)} devices for zone '{zone or 'all'}'")
                return result

        except Exception as e:
            logger.error(f"Error listing devices: {e}", exc_info=True)
            return {"error": str(e)}

    async def _get_device_status(self, device_id: str) -> Dict[str, Any]:
        """Get current device status including battery, sensor readings, and entity states"""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                device_url = f"http://api:8080/api/devices/{device_id}"
                resp = await client.get(device_url, timeout=5.0)

                if resp.status_code != 200:
                    return {
                        "error": f"Failed to fetch device: {resp.status_code}",
                        "device_id": device_id
                    }

                device = resp.json()

                # Extract key information
                result = {
                    "device_id": device_id,
                    "name": device.get("display_name") or device.get("name", device_id),
                    "type": device.get("type"),
                    "zone": device.get("zone_id"),
                    "last_seen": device.get("last_seen"),
                    "integration": device.get("integration"),
                }

                # Extract battery info from battery object (current model)
                battery_obj = device.get("battery")
                if battery_obj and isinstance(battery_obj, dict):
                    result["battery_level"] = battery_obj.get("level")
                    result["battery_low"] = battery_obj.get("is_low", False)
                    result["battery_charging"] = battery_obj.get("is_charging", False)

                # Current readings from root level
                readings = device.get("readings")
                if readings and isinstance(readings, dict):
                    result["readings"] = readings
                    # Extract key readings to root level for easier access
                    if "temperature_f" in readings:
                        result["temperature"] = readings["temperature_f"]
                    elif "temperature" in readings:
                        result["temperature"] = readings["temperature"]
                    if "humidity" in readings:
                        result["humidity"] = readings["humidity"]

                # Extract from entities (alternative location)
                # IMPORTANT: Only include sensor entities, not configuration parameters
                entities = device.get("entities", [])
                if entities:
                    # Filter to only useful entity types (sensors, not config params)
                    useful_types = {"sensor", "battery", "switch", "binary_sensor", "light", "climate"}
                    result["entities"] = {}
                    for entity in entities:
                        entity_id = entity.get("id", "")
                        entity_type = entity.get("type") or entity.get("entity_type", "")
                        value = entity.get("value")

                        # Skip configuration parameters (cc112 = config params, cc113 = alarms, etc)
                        if entity_type not in useful_types or "cc112-" in entity_id or "cc132-" in entity_id or "cc134-" in entity_id:
                            continue

                        # Add to entities dict (filtered)
                        result["entities"][entity_id] = {
                            "type": entity_type,
                            "value": value,
                            "unit": entity.get("unit"),
                            "settable": entity.get("settable", False)
                        }

                        # Extract key sensor types to root level if not already set
                        if entity_type == "battery" and "battery_level" not in result:
                            result["battery_level"] = value
                            result["battery_unit"] = entity.get("unit", "%")
                        elif "temperature" in entity_type.lower() and "temperature" not in result:
                            result["temperature"] = value
                            result["temperature_unit"] = entity.get("unit", "°F")
                        elif "humidity" in entity_type.lower() and "humidity" not in result:
                            result["humidity"] = value
                            result["humidity_unit"] = entity.get("unit", "%")

                # Legacy: Check for battery_level field for backward compatibility
                if "battery_level" in device and "battery_level" not in result:
                    result["battery_level"] = device["battery_level"]

                # Metadata with useful info
                metadata = device.get("metadata", {})
                if metadata:
                    useful_metadata = {}
                    for key in ["manufacturer", "model", "firmware", "location"]:
                        if key in metadata:
                            useful_metadata[key] = metadata[key]
                    if useful_metadata:
                        result["metadata"] = useful_metadata

                return result

        except Exception as e:
            logger.error(f"Error fetching device status: {e}")
            return {"error": str(e), "device_id": device_id}

    # ==================== Helper Methods ====================

    def _interpret_anomaly_score(self, score: float, is_anomalous: bool) -> str:
        """Interpret anomaly score for humans"""
        if not is_anomalous:
            return "Normal - within expected range"

        if score > 0.9:
            return "Highly anomalous - far outside normal range"
        elif score > 0.7:
            return "Anomalous - outside normal range"
        elif score > 0.5:
            return "Borderline - approaching anomaly threshold"
        else:
            return "Slightly elevated but acceptable"

    async def _get_device_documentation(self, device_id: str) -> Dict[str, Any]:
        """Get documentation/knowledge base for a device"""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                # First get device info
                device_url = f"http://api:8080/api/devices/{device_id}"
                device_resp = await client.get(device_url, timeout=5.0)
                
                device_info = {}
                if device_resp.status_code == 200:
                    device_info = device_resp.json()
                
                # Get knowledge base
                kb_url = f"http://api:8080/api/devices/{device_id}/knowledge-base"
                kb_resp = await client.get(kb_url, timeout=5.0)

                if kb_resp.status_code != 200:
                    return {
                        "device_id": device_id,
                        "device_name": device_info.get("name", device_id),
                        "has_documentation": False,
                        "message": "No documentation available for this device"
                    }

                kb_data = kb_resp.json()
                content = kb_data.get("content", "")

                if not content:
                    return {
                        "device_id": device_id,
                        "device_name": device_info.get("name", device_id),
                        "has_documentation": False,
                        "message": "Documentation not yet ingested for this device"
                    }

                return {
                    "device_id": device_id,
                    "device_name": device_info.get("name", device_id),
                    "manufacturer": kb_data.get("manufacturer", ""),
                    "model": kb_data.get("model", ""),
                    "has_documentation": True,
                    "documentation": content,
                    "source": kb_data.get("source", ""),
                    "ingested_at": kb_data.get("ingested_at", "")
                }
        except Exception as e:
            logger.error(f"Error fetching device documentation: {e}")
            return {"error": str(e)}

    async def _list_zones(self, search: Optional[str] = None) -> Dict[str, Any]:
        """List all zones/rooms in the home with attributes and device counts"""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                # Get all zones
                zones_url = f"http://api:8080/api/zones"
                zones_resp = await client.get(zones_url, timeout=5.0)

                if zones_resp.status_code != 200:
                    return {"error": f"Failed to fetch zones: {zones_resp.status_code}"}

                zones = zones_resp.json()

                # Filter by search term if provided
                if search:
                    search_lower = search.lower()
                    zones = [z for z in zones if search_lower in z.get("name", "").lower() or search_lower in z.get("id", "").lower()]

                # Get attributes for each zone
                enriched_zones = []
                for zone in zones:
                    zone_id = zone.get("id", "")

                    # Fetch zone attributes from dedicated endpoint
                    attrs_url = f"http://api:8080/api/zones/{zone_id}/attributes"
                    attrs_resp = await client.get(attrs_url, timeout=2.0)

                    zone_info = {
                        "id": zone_id,
                        "name": zone.get("name", ""),
                        "type": zone.get("type", ""),
                        "home_id": zone.get("home_id", ""),
                        "attributes": {}
                    }

                    # Parse attributes response
                    if attrs_resp.status_code == 200:
                        try:
                            attrs_data = attrs_resp.json()
                            # Convert attribute values to simple dict
                            zone_info["attributes"] = {
                                attr.get("name"): attr.get("value")
                                for attr in attrs_data
                                if attr.get("value") is not None
                            }
                        except Exception as e:
                            logger.warning(f"Failed to parse attributes for zone {zone_id}: {e}")

                    # Count devices in this zone using ontology
                    if self.ontology:
                        devices_in_zone = self.ontology.devices_by_zone.get(zone_id, [])
                        zone_info["device_count"] = len(devices_in_zone)
                        zone_info["devices"] = [d.display_name for d in devices_in_zone]

                    enriched_zones.append(zone_info)

                return {
                    "total_zones": len(enriched_zones),
                    "search_term": search if search else "none",
                    "zones": enriched_zones
                }
        except Exception as e:
            logger.error(f"Error listing zones: {e}")
            return {"error": str(e)}

    async def _get_sensor_readings(self, device_id: str, reading_type: str = "temperature", hours_back: int = 24) -> Dict[str, Any]:
        """Get time-series sensor readings from the database"""
        import httpx
        from datetime import datetime, timedelta

        try:
            async with httpx.AsyncClient() as client:
                # Calculate since timestamp
                since = datetime.now() - timedelta(hours=hours_back)
                since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")

                # Query sensor readings API
                readings_url = f"http://api:8080/api/sensors/{device_id}/readings"
                params = {
                    "type": reading_type,
                    "since": since_str,
                    "limit": 1000
                }

                resp = await client.get(readings_url, params=params, timeout=5.0)

                if resp.status_code != 200:
                    return {
                        "error": f"Failed to fetch sensor readings: {resp.status_code}",
                        "device_id": device_id
                    }

                readings = resp.json()

                # Handle null response
                if readings is None:
                    readings = []

                # Calculate summary statistics if we have readings
                summary = {
                    "device_id": device_id,
                    "reading_type": reading_type,
                    "hours_back": hours_back,
                    "total_readings": len(readings),
                    "readings": readings
                }

                if readings and len(readings) > 0:
                    values = [r.get("value") for r in readings if r.get("value") is not None]
                    if values:
                        summary["min"] = round(min(values), 2)
                        summary["max"] = round(max(values), 2)
                        summary["avg"] = round(sum(values) / len(values), 2)
                        summary["latest"] = values[-1] if values else None
                        summary["oldest"] = values[0] if values else None

                return summary

        except Exception as e:
            logger.error(f"Error fetching sensor readings: {e}")
            return {"error": str(e), "device_id": device_id}

    async def _set_device_value(self, device_id: str, entity_id: str, value: str) -> Dict[str, Any]:
        """Set a device entity value (control a device)"""
        import httpx
        import json

        try:
            # Convert string value to appropriate type
            # OpenAI passes everything as string due to tool schema limitation
            parsed_value = value
            if value.lower() == "true":
                parsed_value = True
            elif value.lower() == "false":
                parsed_value = False
            else:
                # Try to parse as number
                try:
                    if '.' in value:
                        parsed_value = float(value)
                    else:
                        parsed_value = int(value)
                except ValueError:
                    # Keep as string
                    pass

            async with httpx.AsyncClient() as client:
                # Call the set entity API endpoint
                set_url = f"http://api:8080/api/devices/{device_id}/set-entity"
                payload = {
                    "entity_id": entity_id,
                    "value": parsed_value
                }

                resp = await client.post(set_url, json=payload, timeout=5.0)

                if resp.status_code == 202:  # Accepted (queued)
                    result = resp.json()
                    return {
                        "success": True,
                        "device_id": device_id,
                        "entity_id": entity_id,
                        "value": value,
                        "status": "queued",
                        "message": f"Command sent to {device_id}: set {entity_id} to {value}"
                    }
                else:
                    error_detail = resp.text
                    return {
                        "success": False,
                        "error": f"Failed to set device value: {resp.status_code} - {error_detail}",
                        "device_id": device_id
                    }

        except Exception as e:
            logger.error(f"Error setting device value: {e}")
            return {"success": False, "error": str(e), "device_id": device_id}

    async def _list_controllable_devices(self) -> Dict[str, Any]:
        """List all controllable devices with their settable entities"""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                # Get all devices
                devices_url = f"http://api:8080/api/devices"
                resp = await client.get(devices_url, timeout=5.0)

                if resp.status_code != 200:
                    return {"error": f"Failed to fetch devices: {resp.status_code}"}

                devices_data = resp.json()
                devices_list = devices_data.get("devices", []) if isinstance(devices_data, dict) else devices_data

                # Filter for devices with settable entities
                controllable = []
                for device in devices_list:
                    entities = device.get("entities", [])
                    settable_entities = [
                        {
                            "id": entity.get("id"),
                            "type": entity.get("type") or entity.get("entity_type"),
                            "value": entity.get("value"),
                            "unit": entity.get("unit"),
                        }
                        for entity in entities
                        if entity.get("settable", False)
                    ]

                    if settable_entities:
                        controllable.append({
                            "device_id": device.get("id"),
                            "name": device.get("display_name") or device.get("name"),
                            "type": device.get("type"),
                            "zone": device.get("zone_id"),
                            "settable_entities": settable_entities
                        })

                return {
                    "total_controllable": len(controllable),
                    "devices": controllable
                }

        except Exception as e:
            logger.error(f"Error listing controllable devices: {e}")
            return {"error": str(e)}

    async def _get_device_controls(self, device_id: str) -> Dict[str, Any]:
        """Get all controllable entities for a specific device"""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                # Get device details
                device_url = f"http://api:8080/api/devices/{device_id}"
                resp = await client.get(device_url, timeout=5.0)

                if resp.status_code != 200:
                    return {"error": f"Device not found: {device_id}"}

                device = resp.json()

                # Extract controllable entities with detailed info
                entities = device.get("entities", [])
                controls = []

                for entity in entities:
                    if entity.get("settable", False):
                        entity_info = {
                            "entity_id": entity.get("id"),
                            "name": entity.get("name"),
                            "type": entity.get("entity_type") or entity.get("type"),
                            "category": entity.get("category"),
                            "current_value": entity.get("value"),
                            "unit": entity.get("unit"),
                            "metadata": entity.get("metadata", {})
                        }

                        # Add helpful label from metadata if available
                        metadata = entity.get("metadata", {})
                        if "label" in metadata:
                            entity_info["label"] = metadata["label"]

                        controls.append(entity_info)

                # Also check for simplified controls object
                device_controls = device.get("controls", {})
                for control_key, control_val in device_controls.items():
                    if isinstance(control_val, dict) and control_val.get("settable"):
                        controls.append({
                            "entity_id": control_key,
                            "name": control_key,
                            "type": control_key,
                            "category": "control",
                            "current_value": control_val.get("value"),
                            "settable": True,
                            "simplified_control": True
                        })

                return {
                    "device_id": device_id,
                    "device_name": device.get("display_name") or device.get("name"),
                    "controllable": device.get("controllable", False),
                    "controls": controls,
                    "total_controls": len(controls)
                }

        except Exception as e:
            logger.error(f"Error getting device controls for {device_id}: {e}")
            return {"error": str(e)}
