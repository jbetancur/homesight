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
                ToolParameter("device_id", "string", "The device ID to check"),
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
                ToolParameter("location", "string", "The room/zone name"),
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
            description="Get incident history for a specific device, including timestamps of anomalies/leaks.",
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

    async def _check_erratic_behavior(self, device_id: str) -> Dict[str, Any]:
        """Check for erratic behavior"""
        if not self.learning_engine:
            return {"error": "Learning engine not available"}

        stats = await self.learning_engine.get_device_erratic_stats(device_id)

        if not stats:
            return {
                "is_erratic": False,
                "message": "No erratic behavior data available for this device"
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

    async def _get_comfort_preferences(self, location: str) -> Dict[str, Any]:
        """Get comfort preferences"""
        if not self.learning_engine:
            return {"error": "Learning engine not available"}

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
                    "incidents": formatted
                }
        except Exception as e:
            logger.error(f"Error fetching device incidents: {e}")
            return {"error": str(e)}

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
                devices_url = "http://api:8080/api/devices"
                resp = await client.get(devices_url, timeout=5.0)

                if resp.status_code != 200:
                    return {"error": f"Failed to fetch devices: {resp.status_code}"}

                all_devices = resp.json()

                # Filter by zone if specified
                if zone:
                    zone_normalized = zone.lower().strip()
                    devices = [
                        d for d in all_devices
                        if d.get("zone_id", "").lower() == zone_normalized
                    ]
                    
                    if not devices:
                        return {
                            "zone": zone,
                            "count": 0,
                            "devices": [],
                            "message": f"No devices found in {zone}"
                        }
                else:
                    devices = all_devices

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
                    
                    device_list.append(device_info)

                return {
                    "zone": zone or "all",
                    "count": len(device_list),
                    "devices": device_list
                }

        except Exception as e:
            logger.error(f"Error listing devices: {e}")
            return {"error": str(e)}

    async def _get_device_status(self, device_id: str) -> Dict[str, Any]:
        """Get current device status including battery, readings, and state"""
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
                    "state": device.get("state"),
                    "zone": device.get("zone_id"),
                    "last_seen": device.get("last_seen"),
                }

                # Battery info if available
                if "battery_level" in device:
                    result["battery_level"] = device["battery_level"]
                    result["battery_low"] = device.get("battery_low", False)

                # Current readings
                if device.get("readings"):
                    result["readings"] = device["readings"]

                # Metadata with useful info
                metadata = device.get("metadata", {})
                if metadata:
                    # Extract commonly needed metadata
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
        """List all zones/rooms in the home, optionally filtered by search term"""
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
                    attrs_url = f"http://api:8080/api/zones/{zone_id}/attributes"
                    attrs_resp = await client.get(attrs_url, timeout=2.0)
                    
                    zone_info = {
                        "id": zone_id,
                        "name": zone.get("name", ""),
                        "type": zone.get("type", ""),
                        "home_id": zone.get("home_id", ""),
                        "attributes": {}
                    }
                    
                    if attrs_resp.status_code == 200:
                        attrs = attrs_resp.json()
                        zone_info["attributes"] = attrs
                    
                    enriched_zones.append(zone_info)

                return {
                    "total_zones": len(enriched_zones),
                    "search_term": search if search else "none",
                    "zones": enriched_zones
                }
        except Exception as e:
            logger.error(f"Error listing zones: {e}")
            return {"error": str(e)}
