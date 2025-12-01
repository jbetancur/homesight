"""
Home Health Engine

Provides authoritative, single-source-of-truth home health status.
Prevents contradictions and hallucinations by querying backend incidents API.

NO DUPLICATE LOGIC - uses existing Go backend alarm detection.
"""

import logging
import httpx
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Home health status levels"""
    GOOD = "good"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class HealthDetail:
    """Individual health concern"""
    severity: str  # "info", "warning", "critical"
    category: str  # "leak", "temperature", "humidity", "smoke", etc.
    message: str
    device_id: Optional[str] = None
    location: Optional[str] = None


@dataclass
class HomeHealth:
    """Complete home health assessment"""
    health_score: int  # 0-100
    status: HealthStatus
    details: List[HealthDetail]
    critical_devices: List[str]

    # Specific flags
    has_leak: bool = False
    has_smoke: bool = False
    has_co: bool = False
    has_temp_anomaly: bool = False
    has_humidity_anomaly: bool = False

    # Counts
    total_devices: int = 0
    active_alarms: int = 0


class HomeHealthEngine:
    """
    Evaluates home sensor states and produces authoritative health status.

    Single source of truth - prevents LLM contradictions.
    """

    def __init__(
        self,
        backend_url: str = "http://localhost:8080",
        temp_range: tuple = (68, 75),  # Preferred temp range
        humidity_range: tuple = (35, 55)  # Preferred humidity range
    ):
        self.backend_url = backend_url
        self.preferred_temp_min = temp_range[0]
        self.preferred_temp_max = temp_range[1]
        self.preferred_humidity_min = humidity_range[0]
        self.preferred_humidity_max = humidity_range[1]

    async def evaluate(
        self,
        devices: Optional[Dict[str, Any]] = None,
        home_state: Optional[Dict[str, Any]] = None
    ) -> HomeHealth:
        """
        Evaluate current home health by querying backend incidents API.

        Uses Go backend's existing alarm detection - NO DUPLICATION.

        Args:
            devices: Device ontology (optional, for device count)
            home_state: Current home state (optional, for temp/humidity checks)

        Returns:
            HomeHealth assessment
        """
        details = []
        critical_devices = []

        # Flags
        has_leak = False
        has_smoke = False
        has_co = False
        has_temp_anomaly = False
        has_humidity_anomaly = False

        total_devices = 0
        active_alarms = 0

        # Query backend for active incidents (authoritative alarm source)
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.backend_url}/api/incidents?status=active")
                if resp.status_code == 200:
                    incidents = resp.json()

                    for incident in incidents:
                        incident_type = incident.get("type", "")
                        severity_str = incident.get("severity", "medium")
                        device_id = incident.get("device_id")
                        title = incident.get("title", "")
                        description = incident.get("description", "")

                        # Map severity
                        if severity_str == "critical":
                            severity = "critical"
                        elif severity_str in ("high", "medium"):
                            severity = "warning"
                        else:
                            severity = "info"

                        # Categorize and flag
                        category = incident_type.lower()

                        if "leak" in category or "water" in category:
                            has_leak = True
                            active_alarms += 1
                            critical_devices.append(device_id)
                        elif "smoke" in category:
                            has_smoke = True
                            active_alarms += 1
                            critical_devices.append(device_id)
                        elif "co" in category or "carbon" in category:
                            has_co = True
                            active_alarms += 1
                            critical_devices.append(device_id)

                        details.append(HealthDetail(
                            severity=severity,
                            category=category,
                            message=title or description,
                            device_id=device_id
                        ))

        except Exception as e:
            logger.warning(f"Failed to fetch incidents from backend: {e}")

        # Check temperature/humidity preferences (only if home_state provided)
        if home_state:
            # Handle both dict and HomeState object
            devices_list = []
            if isinstance(home_state, dict):
                devices_list = home_state.get("devices", [])
            elif hasattr(home_state, 'devices'):
                devices_list = home_state.devices

            total_devices = len(devices_list)

            for device in devices_list:
                # Handle both dict and DeviceState object
                if isinstance(device, dict):
                    device_id = device.get("device_id")
                    state = device.get("state", {})
                    location = device.get("location", "unknown")
                else:
                    device_id = device.device_id
                    state = device.state if hasattr(device, 'state') else {}
                    location = device.location if hasattr(device, 'location') else "unknown"

                # Temperature check
                if isinstance(state, dict) and "temperature" in state:
                    temp = state["temperature"]
                    if isinstance(temp, (int, float)):
                        if temp < self.preferred_temp_min:
                            has_temp_anomaly = True
                            details.append(HealthDetail(
                                severity="info",
                                category="temperature",
                                message=f"{location}: {temp}°F (prefer {self.preferred_temp_min}-{self.preferred_temp_max}°F)",
                                device_id=device_id,
                                location=location
                            ))
                        elif temp > self.preferred_temp_max:
                            has_temp_anomaly = True
                            details.append(HealthDetail(
                                severity="info",
                                category="temperature",
                                message=f"{location}: {temp}°F (prefer {self.preferred_temp_min}-{self.preferred_temp_max}°F)",
                                device_id=device_id,
                                location=location
                            ))

                # Humidity check
                if isinstance(state, dict) and "humidity" in state:
                    humidity = state["humidity"]
                    if isinstance(humidity, (int, float)):
                        if humidity < self.preferred_humidity_min or humidity > self.preferred_humidity_max:
                            has_humidity_anomaly = True
                            details.append(HealthDetail(
                                severity="info",
                                category="humidity",
                                message=f"{location}: {humidity}% (prefer {self.preferred_humidity_min}-{self.preferred_humidity_max}%)",
                                device_id=device_id,
                                location=location
                            ))

        # Determine overall status
        status = HealthStatus.GOOD
        health_score = 100

        if has_leak or has_smoke or has_co:
            status = HealthStatus.CRITICAL
            health_score = max(0, 100 - active_alarms * 50)
        elif has_temp_anomaly or has_humidity_anomaly:
            status = HealthStatus.WARNING
            health_score = 75
        elif len(details) > 0:
            status = HealthStatus.WARNING
            health_score = 85

        return HomeHealth(
            health_score=health_score,
            status=status,
            details=details,
            critical_devices=critical_devices,
            has_leak=has_leak,
            has_smoke=has_smoke,
            has_co=has_co,
            has_temp_anomaly=has_temp_anomaly,
            has_humidity_anomaly=has_humidity_anomaly,
            total_devices=total_devices,
            active_alarms=active_alarms
        )

    def format_for_llm(self, health: HomeHealth) -> str:
        """
        Format health assessment for LLM consumption.

        Returns concise, authoritative summary.
        """
        lines = [f"Home Health: {health.status.value.upper()} (score: {health.health_score}/100)"]

        if health.status == HealthStatus.CRITICAL:
            lines.append("⚠️ CRITICAL ISSUES:")
            for detail in health.details:
                if detail.severity == "critical":
                    lines.append(f"  - {detail.message}")

        elif health.status == HealthStatus.WARNING:
            lines.append("⚠️ Warnings:")
            for detail in health.details:
                lines.append(f"  - {detail.message}")

        else:
            lines.append("✓ All systems normal")

        # Add specific flags for LLM clarity
        flags = []
        if health.has_leak:
            flags.append("LEAK DETECTED")
        if health.has_smoke:
            flags.append("SMOKE DETECTED")
        if health.has_co:
            flags.append("CO DETECTED")

        if flags:
            lines.append(f"Active Alarms: {', '.join(flags)}")

        return "\n".join(lines)

    def update_preferences(
        self,
        temp_range: Optional[tuple] = None,
        humidity_range: Optional[tuple] = None
    ):
        """Update preferred ranges based on user learning"""
        if temp_range:
            self.preferred_temp_min, self.preferred_temp_max = temp_range
            logger.info(f"Updated temp preference: {temp_range}")

        if humidity_range:
            self.preferred_humidity_min, self.preferred_humidity_max = humidity_range
            logger.info(f"Updated humidity preference: {humidity_range}")
