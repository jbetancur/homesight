"""
Incident Generator - Automatic Incident Creation from Detected Scenarios

Creates incidents in the Go backend when scenarios are detected that warrant
user attention or historical tracking.

Features:
- Maps scenarios to incident types
- Deduplicates similar incidents
- Auto-resolves transient issues
- Tracks incident lifecycle
"""

import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from collections import defaultdict

from .hil_types import (
    ScenarioMatch, FusedContext, ReasoningResult,
    Severity, IncidentType
)

logger = logging.getLogger(__name__)


class IncidentGenerator:
    """
    Generates incidents from detected scenarios.

    Integrates with Go backend's /api/incidents endpoint.
    """

    # Scenario to incident type mapping
    SCENARIO_TO_INCIDENT: Dict[str, IncidentType] = {
        # Water/leak scenarios
        "water_leak_active": IncidentType.WATER_LEAK,
        "water_leak_flooding": IncidentType.WATER_LEAK,
        "humidity_high_mold_risk": IncidentType.HUMIDITY_ISSUE,
        "humidity_high_condensation": IncidentType.HUMIDITY_ISSUE,

        # HVAC scenarios
        "hvac_inefficiency_slow_response": IncidentType.HVAC_ISSUE,
        "hvac_inefficiency_cycling": IncidentType.HVAC_ISSUE,
        "hvac_inefficiency_temp_discrepancy": IncidentType.HVAC_ISSUE,

        # Comfort scenarios
        "comfort_room_cold": IncidentType.COMFORT_ISSUE,
        "comfort_room_hot": IncidentType.COMFORT_ISSUE,
        "temp_discrepancy_rooms": IncidentType.COMFORT_ISSUE,

        # Battery scenarios
        "battery_low_critical": IncidentType.BATTERY_LOW,
        "battery_low_warning": IncidentType.BATTERY_LOW,

        # Safety scenarios
        "security_motion_unusual": IncidentType.SECURITY_ALERT,
        "entry_door_left_open": IncidentType.SECURITY_ALERT,

        # Air quality
        "aqi_outdoor_poor": IncidentType.AIR_QUALITY,
        "aqi_indoor_poor": IncidentType.AIR_QUALITY,

        # Behavioral anomalies
        "behavioral_routine_anomaly": IncidentType.BEHAVIORAL_ANOMALY,
        "behavioral_occupancy_unusual": IncidentType.BEHAVIORAL_ANOMALY,

        # Sensor issues
        "sensor_inconsistency_conflict": IncidentType.SENSOR_ISSUE,
        "sensor_inconsistency_drift": IncidentType.SENSOR_ISSUE,
    }

    # Severity mapping
    SEVERITY_TO_PRIORITY: Dict[Severity, str] = {
        Severity.CRITICAL: "critical",
        Severity.HIGH: "high",
        Severity.MEDIUM: "medium",
        Severity.LOW: "low",
        Severity.INFO: "info",
    }

    # Auto-resolve thresholds (minutes)
    AUTO_RESOLVE_THRESHOLDS: Dict[IncidentType, int] = {
        IncidentType.COMFORT_ISSUE: 30,  # Comfort issues resolve if conditions normalize
        IncidentType.HUMIDITY_ISSUE: 60,  # Humidity takes longer
        IncidentType.AIR_QUALITY: 120,  # Air quality can take hours
        IncidentType.SECURITY_ALERT: 15,  # Quick resolve for transient alerts
    }

    # Deduplication windows (minutes)
    DEDUP_WINDOWS: Dict[IncidentType, int] = {
        IncidentType.WATER_LEAK: 5,  # Water leaks - short window, may reoccur
        IncidentType.BATTERY_LOW: 1440,  # Battery - 24h, don't spam
        IncidentType.HVAC_ISSUE: 60,  # HVAC - 1 hour
        IncidentType.COMFORT_ISSUE: 30,
        IncidentType.SENSOR_ISSUE: 60,
    }

    def __init__(
        self,
        backend_url: str = "http://localhost:8080",
        enable_auto_resolve: bool = True,
        dry_run: bool = False
    ):
        self.backend_url = backend_url.rstrip("/")
        self.enable_auto_resolve = enable_auto_resolve
        self.dry_run = dry_run

        # Track recent incidents for deduplication
        self.recent_incidents: Dict[str, datetime] = {}  # key -> timestamp

        # Track active incidents for auto-resolve
        self.active_incidents: Dict[str, Dict[str, Any]] = {}  # incident_id -> data

        # Metrics
        self.incidents_created = 0
        self.incidents_deduplicated = 0
        self.incidents_auto_resolved = 0

        logger.info(f"IncidentGenerator initialized (dry_run={dry_run})")

    async def process_scenarios(
        self,
        scenarios: List[ScenarioMatch],
        fused_context: FusedContext,
        reasoning_result: Optional[ReasoningResult] = None
    ) -> List[Dict[str, Any]]:
        """
        Process detected scenarios and create incidents as needed.

        Args:
            scenarios: List of matched scenarios
            fused_context: Current fused context
            reasoning_result: Optional reasoning result for description

        Returns:
            List of created incident data
        """
        created_incidents = []

        for scenario in scenarios:
            # Check if this scenario warrants an incident
            incident_type = self.SCENARIO_TO_INCIDENT.get(scenario.scenario_id)
            if not incident_type:
                continue

            # Check deduplication
            dedup_key = self._get_dedup_key(scenario, fused_context)
            if self._is_duplicate(dedup_key, incident_type):
                self.incidents_deduplicated += 1
                logger.debug(f"Deduplicated incident: {dedup_key}")
                continue

            # Create incident
            incident_data = self._build_incident(
                scenario, fused_context, reasoning_result, incident_type
            )

            if not self.dry_run:
                created = await self._create_incident(incident_data)
                if created:
                    created_incidents.append(created)
                    self.recent_incidents[dedup_key] = datetime.now()
                    self.active_incidents[created["id"]] = created
                    self.incidents_created += 1
            else:
                logger.info(f"DRY RUN: Would create incident: {incident_data['type']}")
                created_incidents.append(incident_data)

        return created_incidents

    async def check_auto_resolve(
        self,
        fused_context: FusedContext
    ) -> List[str]:
        """
        Check if any active incidents should be auto-resolved.

        Args:
            fused_context: Current fused context

        Returns:
            List of resolved incident IDs
        """
        if not self.enable_auto_resolve:
            return []

        resolved_ids = []
        now = datetime.now()

        for incident_id, incident_data in list(self.active_incidents.items()):
            incident_type = IncidentType(incident_data.get("type", "other"))
            threshold_minutes = self.AUTO_RESOLVE_THRESHOLDS.get(incident_type, 0)

            if threshold_minutes == 0:
                continue

            # Check if incident is old enough for auto-resolve consideration
            created_at = incident_data.get("created_at")
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

            age_minutes = (now - created_at).total_seconds() / 60

            if age_minutes < threshold_minutes:
                continue

            # Check if condition is resolved
            if await self._is_condition_resolved(incident_data, fused_context):
                if not self.dry_run:
                    await self._resolve_incident(incident_id)
                resolved_ids.append(incident_id)
                del self.active_incidents[incident_id]
                self.incidents_auto_resolved += 1
                logger.info(f"Auto-resolved incident {incident_id}")

        return resolved_ids

    def _get_dedup_key(
        self,
        scenario: ScenarioMatch,
        fused_context: FusedContext
    ) -> str:
        """Generate deduplication key for scenario"""
        # Key combines scenario type and location/device
        location = ""
        device_id = ""

        if fused_context.environmental:
            for env in fused_context.environmental:
                if env.location:
                    location = env.location
                    break

        if fused_context.sensor_signals:
            for signal in fused_context.sensor_signals:
                if signal.device_id:
                    device_id = signal.device_id
                    break

        return f"{scenario.scenario_id}:{location}:{device_id}"

    def _is_duplicate(
        self,
        dedup_key: str,
        incident_type: IncidentType
    ) -> bool:
        """Check if incident is duplicate within window"""
        if dedup_key not in self.recent_incidents:
            return False

        window_minutes = self.DEDUP_WINDOWS.get(incident_type, 30)
        last_created = self.recent_incidents[dedup_key]

        return (datetime.now() - last_created).total_seconds() < window_minutes * 60

    def _build_incident(
        self,
        scenario: ScenarioMatch,
        fused_context: FusedContext,
        reasoning_result: Optional[ReasoningResult],
        incident_type: IncidentType
    ) -> Dict[str, Any]:
        """Build incident data structure"""
        # Get device/location info
        device_id = ""
        location = ""
        value = None

        if fused_context.sensor_signals:
            for signal in fused_context.sensor_signals:
                device_id = signal.device_id or ""
                value = signal.value
                if signal.metadata:
                    location = signal.metadata.get("location", "")
                break

        if fused_context.environmental:
            for env in fused_context.environmental:
                location = env.location or location
                break

        # Build description
        description = scenario.scenario_name
        if reasoning_result:
            description = reasoning_result.primary_conclusion

        # Build incident
        return {
            "type": incident_type.value,
            "priority": self.SEVERITY_TO_PRIORITY.get(scenario.severity, "medium"),
            "device_id": device_id,
            "location": location,
            "description": description,
            "value": value,
            "metadata": {
                "scenario_id": scenario.scenario_id,
                "match_confidence": scenario.match_confidence,
                "context_values": scenario.context_values,
                "auto_generated": True,
                "source": "hil_incident_generator"
            }
        }

    async def _create_incident(self, incident_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create incident via backend API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.backend_url}/api/incidents",
                    json=incident_data,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status in (200, 201):
                        result = await response.json()
                        result["created_at"] = datetime.now().isoformat()
                        logger.info(f"Created incident: {result.get('id')} ({incident_data['type']})")
                        return result
                    else:
                        error = await response.text()
                        logger.error(f"Failed to create incident: {response.status} - {error}")
                        return None

        except Exception as e:
            logger.error(f"Incident creation error: {e}")
            return None

    async def _resolve_incident(self, incident_id: str) -> bool:
        """Resolve incident via backend API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.backend_url}/api/incidents/{incident_id}/resolve",
                    json={"resolution": "auto_resolved", "notes": "Condition normalized"},
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status in (200, 204):
                        logger.info(f"Resolved incident: {incident_id}")
                        return True
                    else:
                        error = await response.text()
                        logger.warning(f"Failed to resolve incident: {response.status} - {error}")
                        return False

        except Exception as e:
            logger.error(f"Incident resolution error: {e}")
            return False

    async def _is_condition_resolved(
        self,
        incident_data: Dict[str, Any],
        fused_context: FusedContext
    ) -> bool:
        """Check if incident condition is resolved based on current context"""
        incident_type = IncidentType(incident_data.get("type", "other"))

        # Comfort issues - check if temperature is now in range
        if incident_type == IncidentType.COMFORT_ISSUE:
            if fused_context.environmental:
                for env in fused_context.environmental:
                    if env.temperature is not None:
                        # Comfortable range
                        if 68 <= env.temperature <= 76:
                            return True
            return False

        # Humidity issues - check if humidity normalized
        if incident_type == IncidentType.HUMIDITY_ISSUE:
            if fused_context.environmental:
                for env in fused_context.environmental:
                    if env.humidity is not None:
                        # Normal range
                        if 35 <= env.humidity <= 55:
                            return True
            return False

        # Air quality - check if AQI improved
        if incident_type == IncidentType.AIR_QUALITY:
            if fused_context.external and fused_context.external.aqi is not None:
                if fused_context.external.aqi < 100:  # Good/Moderate
                    return True
            return False

        # Security alerts - time-based, no condition check
        if incident_type == IncidentType.SECURITY_ALERT:
            return True  # Resolve based on time threshold

        # Default - don't auto-resolve
        return False

    async def get_stats(self) -> Dict[str, Any]:
        """Get generator statistics"""
        return {
            "incidents_created": self.incidents_created,
            "incidents_deduplicated": self.incidents_deduplicated,
            "incidents_auto_resolved": self.incidents_auto_resolved,
            "active_incidents": len(self.active_incidents),
            "recent_incidents_tracked": len(self.recent_incidents)
        }

    def cleanup_old_tracking(self, max_age_hours: int = 24):
        """Clean up old tracking data"""
        cutoff = datetime.now() - timedelta(hours=max_age_hours)

        # Clean recent incidents
        old_keys = [
            key for key, timestamp in self.recent_incidents.items()
            if timestamp < cutoff
        ]
        for key in old_keys:
            del self.recent_incidents[key]

        logger.debug(f"Cleaned up {len(old_keys)} old tracking entries")


class IncidentCorrelator:
    """
    Correlates related incidents to identify patterns and root causes.
    """

    def __init__(self):
        self.correlation_window_minutes = 60  # Look for related incidents within 1 hour
        self.incident_history: List[Dict[str, Any]] = []
        self.max_history = 1000

    def add_incident(self, incident: Dict[str, Any]):
        """Add incident to correlation history"""
        self.incident_history.append({
            **incident,
            "tracked_at": datetime.now()
        })

        # Trim old entries
        if len(self.incident_history) > self.max_history:
            self.incident_history = self.incident_history[-self.max_history:]

    def find_correlations(self, incident: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find correlated incidents"""
        correlations = []
        cutoff = datetime.now() - timedelta(minutes=self.correlation_window_minutes)

        incident_type = incident.get("type")
        location = incident.get("location")

        for hist_incident in reversed(self.incident_history):
            tracked_at = hist_incident.get("tracked_at")
            if tracked_at and tracked_at < cutoff:
                break

            # Skip self
            if hist_incident.get("id") == incident.get("id"):
                continue

            # Check correlation rules
            correlated = False
            correlation_type = ""

            # Same location correlation
            if hist_incident.get("location") == location and location:
                correlated = True
                correlation_type = "same_location"

            # Type chain correlations
            type_chains = [
                ("humidity_issue", "water_leak"),  # Humidity might precede leak
                ("hvac_issue", "comfort_issue"),  # HVAC issues cause discomfort
                ("battery_low", "sensor_issue"),  # Dead battery = sensor issues
            ]

            hist_type = hist_incident.get("type")
            for type1, type2 in type_chains:
                if (incident_type == type2 and hist_type == type1) or \
                   (incident_type == type1 and hist_type == type2):
                    correlated = True
                    correlation_type = f"type_chain_{type1}_{type2}"
                    break

            if correlated:
                correlations.append({
                    "incident_id": hist_incident.get("id"),
                    "type": hist_incident.get("type"),
                    "correlation_type": correlation_type,
                    "time_delta_minutes": (
                        datetime.now() - hist_incident.get("tracked_at", datetime.now())
                    ).total_seconds() / 60
                })

        return correlations

    def identify_patterns(self) -> List[Dict[str, Any]]:
        """Identify recurring patterns in incident history"""
        patterns = []

        # Count incidents by type and location
        type_counts: Dict[str, int] = defaultdict(int)
        location_counts: Dict[str, int] = defaultdict(int)
        type_location_counts: Dict[str, int] = defaultdict(int)

        cutoff = datetime.now() - timedelta(hours=24)

        for incident in self.incident_history:
            tracked_at = incident.get("tracked_at")
            if tracked_at and tracked_at < cutoff:
                continue

            inc_type = incident.get("type", "unknown")
            location = incident.get("location", "unknown")

            type_counts[inc_type] += 1
            location_counts[location] += 1
            type_location_counts[f"{inc_type}:{location}"] += 1

        # Identify patterns (>= 3 occurrences)
        for key, count in type_location_counts.items():
            if count >= 3:
                inc_type, location = key.split(":", 1)
                patterns.append({
                    "pattern_type": "recurring_issue",
                    "incident_type": inc_type,
                    "location": location,
                    "occurrences_24h": count,
                    "recommendation": self._get_pattern_recommendation(inc_type, count)
                })

        return patterns

    def _get_pattern_recommendation(self, incident_type: str, count: int) -> str:
        """Get recommendation for recurring pattern"""
        recommendations = {
            "humidity_issue": "Check ventilation, consider a dehumidifier, or inspect for water sources",
            "hvac_issue": "Schedule HVAC maintenance or check thermostat settings",
            "comfort_issue": "Review temperature preferences or check for drafts",
            "battery_low": "Replace batteries in affected devices",
            "sensor_issue": "Inspect sensor placement and connections",
            "water_leak": "Urgent: inspect plumbing and appliances for leaks",
        }

        base = recommendations.get(incident_type, "Investigate recurring issue")

        if count >= 5:
            base = f"HIGH PRIORITY: {base} ({count} occurrences in 24h)"

        return base
