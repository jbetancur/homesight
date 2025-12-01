"""
Reasoning Templates - Structured Chain-of-Thought for Home Intelligence

Provides scenario-specific reasoning templates for:
- Humidity issues (low/high)
- Water leaks
- HVAC efficiency
- Comfort optimization
- Battery/maintenance issues
- Behavioral patterns
- Air quality
- Security

Each template includes:
- Detection signature
- Chain-of-thought steps
- Intent routing
- Recommended actions
- User-facing phrasing
- Escalation logic
- Safety rules
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from .hil_types import (
    ScenarioSignature, ScenarioMatch, ReasoningTemplate,
    ReasoningChain, ReasoningStep, Insight, ReasoningResult,
    FusedContext, Severity, ScenarioCategory, ActionMode
)

logger = logging.getLogger(__name__)


# =============================================================================
# SCENARIO SIGNATURES (Detection Patterns)
# =============================================================================

SCENARIO_SIGNATURES: Dict[str, ScenarioSignature] = {
    # Humidity Scenarios
    "humidity_low_wood_floors": ScenarioSignature(
        scenario_id="humidity_low_wood_floors",
        category=ScenarioCategory.HUMIDITY,
        name="Low Humidity - Wood Floor Risk",
        description="Low indoor humidity may damage hardwood floors",
        required_signals=["humidity"],
        threshold_conditions={
            "indoor_humidity": {"max": 35},
            "has_wood_floors": True  # From home profile
        },
        temporal_conditions={"season": ["winter", "fall"]},
        base_severity=Severity.MEDIUM,
        urgency_factors=["humidity_below_25", "sustained_3_days"]
    ),
    "humidity_low_health": ScenarioSignature(
        scenario_id="humidity_low_health",
        category=ScenarioCategory.HUMIDITY,
        name="Low Humidity - Health Impact",
        description="Low humidity affecting airways and comfort",
        required_signals=["humidity"],
        threshold_conditions={"indoor_humidity": {"max": 30}},
        temporal_conditions=None,
        base_severity=Severity.MEDIUM,
        urgency_factors=["elderly_present", "respiratory_condition"]
    ),
    "humidity_high_mold": ScenarioSignature(
        scenario_id="humidity_high_mold",
        category=ScenarioCategory.HUMIDITY,
        name="High Humidity - Mold Risk",
        description="High humidity increasing mold risk",
        required_signals=["humidity"],
        threshold_conditions={"indoor_humidity": {"min": 65}},
        temporal_conditions={"season": ["summer", "spring"]},
        base_severity=Severity.HIGH,
        urgency_factors=["humidity_above_70", "basement_location", "sustained_2_days"]
    ),
    "humidity_rapid_basement": ScenarioSignature(
        scenario_id="humidity_rapid_basement",
        category=ScenarioCategory.HUMIDITY,
        name="Rapid Basement Humidity Increase",
        description="Sudden humidity spike in basement",
        required_signals=["humidity"],
        threshold_conditions={
            "humidity_trend_1h": {"min": 10},  # >10% increase in 1 hour
            "location": "basement"
        },
        base_severity=Severity.HIGH,
        urgency_factors=["above_ground_water_table", "recent_rain"]
    ),

    # Water Safety Scenarios
    "leak_detected": ScenarioSignature(
        scenario_id="leak_detected",
        category=ScenarioCategory.WATER_SAFETY,
        name="Water Leak Detected",
        description="Water leak sensor triggered",
        required_signals=["leak"],
        threshold_conditions={"leak_active": True},
        base_severity=Severity.CRITICAL,
        urgency_factors=["near_electrical", "finished_basement"]
    ),
    "water_usage_spike": ScenarioSignature(
        scenario_id="water_usage_spike",
        category=ScenarioCategory.WATER_SAFETY,
        name="Unusual Water Usage",
        description="Water usage significantly higher than last week",
        required_signals=["water_flow"],
        threshold_conditions={"week_delta_percent": {"min": 50}},
        base_severity=Severity.MEDIUM,
        urgency_factors=["no_guests", "unoccupied"]
    ),

    # HVAC Scenarios
    "hvac_slow_cooling": ScenarioSignature(
        scenario_id="hvac_slow_cooling",
        category=ScenarioCategory.HVAC_EFFICIENCY,
        name="AC Taking Longer to Cool",
        description="Air conditioning taking longer than usual to reach setpoint",
        required_signals=["temperature", "hvac_runtime"],
        threshold_conditions={
            "cooling_time_increase_percent": {"min": 30}
        },
        temporal_conditions={"weather_hot": True},
        base_severity=Severity.MEDIUM,
        urgency_factors=["filter_age_90_days", "refrigerant_low"]
    ),
    "hvac_cycle_frequency": ScenarioSignature(
        scenario_id="hvac_cycle_frequency",
        category=ScenarioCategory.HVAC_EFFICIENCY,
        name="Boiler/Furnace Cycling Too Frequently",
        description="Heating system cycling more than expected",
        required_signals=["hvac_cycles"],
        threshold_conditions={"cycles_per_hour": {"min": 6}},
        base_severity=Severity.MEDIUM,
        urgency_factors=["outdoor_temp_moderate"]
    ),

    # Comfort Scenarios
    "comfort_room_cold": ScenarioSignature(
        scenario_id="comfort_room_cold",
        category=ScenarioCategory.COMFORT,
        name="Room Temperature Too Cold",
        description="Room temperature below comfort threshold",
        required_signals=["temperature"],
        threshold_conditions={"indoor_temp": {"max": 66}},
        temporal_conditions={"is_occupied": True},
        base_severity=Severity.LOW,
        urgency_factors=["elderly_present", "infant_present"]
    ),
    "comfort_room_hot": ScenarioSignature(
        scenario_id="comfort_room_hot",
        category=ScenarioCategory.COMFORT,
        name="Room Temperature Too Hot",
        description="Room temperature above comfort threshold",
        required_signals=["temperature"],
        threshold_conditions={"indoor_temp": {"min": 78}},
        temporal_conditions={"is_occupied": True},
        base_severity=Severity.LOW,
        urgency_factors=["high_outdoor_temp", "humidity_high"]
    ),
    "comfort_open_window": ScenarioSignature(
        scenario_id="comfort_open_window",
        category=ScenarioCategory.COMFORT,
        name="Possible Open Window",
        description="Temperature discrepancy suggesting open window",
        required_signals=["temperature"],
        threshold_conditions={
            "room_temp_deviation": {"min": 5},  # >5°F from other rooms
            "hvac_running": True
        },
        base_severity=Severity.LOW,
        urgency_factors=["weather_extreme", "security_mode_active"]
    ),

    # Air Quality Scenarios
    "co2_high_bedroom": ScenarioSignature(
        scenario_id="co2_high_bedroom",
        category=ScenarioCategory.AIR_QUALITY,
        name="High CO2 in Bedroom",
        description="CO2 levels elevated in bedroom during sleep",
        required_signals=["co2"],
        threshold_conditions={
            "co2_ppm": {"min": 1000},
            "location": "bedroom"
        },
        temporal_conditions={"is_nighttime": True},
        base_severity=Severity.MEDIUM,
        urgency_factors=["sustained_2_hours"]
    ),
    "aqi_outdoor_poor": ScenarioSignature(
        scenario_id="aqi_outdoor_poor",
        category=ScenarioCategory.AIR_QUALITY,
        name="Poor Outdoor Air Quality",
        description="Outdoor AQI suggests recirculation mode",
        required_signals=[],
        threshold_conditions={"outdoor_aqi": {"min": 3}},  # 3+ = moderate or worse
        base_severity=Severity.MEDIUM,
        urgency_factors=["respiratory_condition", "windows_open"]
    ),

    # Maintenance Scenarios
    "battery_low": ScenarioSignature(
        scenario_id="battery_low",
        category=ScenarioCategory.MAINTENANCE,
        name="Sensor Battery Low",
        description="Sensor reporting low battery",
        required_signals=["battery"],
        threshold_conditions={"battery_percent": {"max": 20}},
        base_severity=Severity.LOW,
        urgency_factors=["critical_sensor", "battery_below_10"]
    ),
    "sensor_inconsistent": ScenarioSignature(
        scenario_id="sensor_inconsistent",
        category=ScenarioCategory.MAINTENANCE,
        name="Sensor Inconsistency",
        description="Sensor readings inconsistent with neighbors",
        required_signals=["temperature", "humidity"],
        threshold_conditions={"neighbor_deviation": {"min": 10}},
        base_severity=Severity.LOW,
        urgency_factors=["sustained_1_day"]
    ),

    # Behavioral Scenarios
    "routine_deviation": ScenarioSignature(
        scenario_id="routine_deviation",
        category=ScenarioCategory.BEHAVIORAL,
        name="Unusual Activity Pattern",
        description="Activity deviates from learned routine",
        required_signals=["motion"],
        threshold_conditions={"routine_deviation_score": {"min": 0.7}},
        base_severity=Severity.INFO,
        urgency_factors=["security_mode_active"]
    ),
    "expected_activity": ScenarioSignature(
        scenario_id="expected_activity",
        category=ScenarioCategory.BEHAVIORAL,
        name="Expected Activity Prediction",
        description="Based on patterns, user typically does X now",
        required_signals=["motion", "time"],
        threshold_conditions={"pattern_confidence": {"min": 0.8}},
        base_severity=Severity.INFO,
        urgency_factors=[]
    ),
}


# =============================================================================
# REASONING TEMPLATES
# =============================================================================

REASONING_TEMPLATES: Dict[str, ReasoningTemplate] = {
    "humidity_low_wood_floors": ReasoningTemplate(
        scenario_id="humidity_low_wood_floors",
        category=ScenarioCategory.HUMIDITY,
        name="Low Humidity - Wood Floor Protection",
        reasoning_steps=[
            "1. OBSERVE: Indoor humidity is {humidity}%, below 35% threshold",
            "2. CONTEXT: Season is {season}, outdoor humidity is {outdoor_humidity}%",
            "3. RISK: Low humidity can cause hardwood floor cracking and gaps",
            "4. TREND: Humidity has been {trend} over the past {trend_period}",
            "5. RECOMMENDATION: Consider running humidifier to target 40-45%",
        ],
        recommended_actions=[
            {"action": "set_humidity", "target": 42, "device_type": "humidifier"},
            {"action": "notify", "message": "Low humidity may affect wood floors"}
        ],
        user_message_template="Indoor humidity is low at {humidity}%. This could affect your hardwood floors during {season}.",
        detail_template="I recommend running your humidifier to bring humidity up to 40-45%. Current outdoor humidity is {outdoor_humidity}%, so the dry air is coming from outside.",
        safety_rules=["humidity_change_gradual"],
        escalation_conditions={"humidity_below": 25, "sustained_days": 3},
        min_confidence_for_action=0.7,
        min_confidence_for_auto_action=0.9
    ),

    "humidity_high_mold": ReasoningTemplate(
        scenario_id="humidity_high_mold",
        category=ScenarioCategory.HUMIDITY,
        name="High Humidity - Mold Prevention",
        reasoning_steps=[
            "1. OBSERVE: Indoor humidity is {humidity}%, above 65% threshold",
            "2. CONTEXT: Location is {location}, {weather_context}",
            "3. RISK: High humidity >60% promotes mold growth",
            "4. CHECK: Is there adequate ventilation? Are there moisture sources?",
            "5. RECOMMENDATION: Run dehumidifier or increase ventilation",
        ],
        recommended_actions=[
            {"action": "set_humidity", "target": 50, "device_type": "dehumidifier"},
            {"action": "notify", "message": "High humidity detected - mold risk"}
        ],
        user_message_template="Humidity in {location} is {humidity}%, which could promote mold growth.",
        detail_template="I recommend reducing humidity to 50-55%. Check for any moisture sources like leaks or poor ventilation. {weather_note}",
        safety_rules=["humidity_change_gradual"],
        escalation_conditions={"humidity_above": 70, "sustained_days": 2},
        min_confidence_for_action=0.7,
        min_confidence_for_auto_action=0.85
    ),

    "leak_detected": ReasoningTemplate(
        scenario_id="leak_detected",
        category=ScenarioCategory.WATER_SAFETY,
        name="Water Leak Response",
        reasoning_steps=[
            "1. ALERT: Water leak detected by sensor {sensor_id}",
            "2. LOCATION: {location} - assess potential damage scope",
            "3. URGENCY: Water damage can occur within minutes",
            "4. ACTION: Close main water valve immediately",
            "5. NOTIFY: Alert homeowner with location and recommended actions",
        ],
        recommended_actions=[
            {"action": "close_valve", "device_type": "water_main", "priority": "critical"},
            {"action": "notify", "message": "WATER LEAK DETECTED", "priority": "critical"},
            {"action": "schedule_reopen", "delay_minutes": 60}
        ],
        user_message_template="⚠️ WATER LEAK detected in {location}! I've closed the main water valve.",
        detail_template="Sensor {sensor_id} triggered at {time}. The main valve will remain closed. Check the area for active water and the source of the leak. Reply 'reopen valve' when safe.",
        safety_rules=["water_valve_close_leak", "water_valve_open"],
        escalation_conditions={"always": True},
        min_confidence_for_action=0.5,  # Act fast on leaks
        min_confidence_for_auto_action=0.7
    ),

    "water_usage_spike": ReasoningTemplate(
        scenario_id="water_usage_spike",
        category=ScenarioCategory.WATER_SAFETY,
        name="Unusual Water Usage Investigation",
        reasoning_steps=[
            "1. OBSERVE: Water usage is {percent_increase}% higher than last week",
            "2. COMPARE: Same day last week used {last_week_gallons} gallons",
            "3. CHECK: Are there guests? Running irrigation? Known reasons?",
            "4. POSSIBLE CAUSES: Running toilet, irrigation issue, slow leak",
            "5. RECOMMENDATION: Monitor and investigate if unexplained",
        ],
        recommended_actions=[
            {"action": "notify", "message": "Unusual water usage detected"},
            {"action": "flag_for_monitoring", "duration_hours": 24}
        ],
        user_message_template="Water usage today is {percent_increase}% higher than the same day last week.",
        detail_template="You've used approximately {current_gallons} gallons compared to {last_week_gallons} last {day_of_week}. This could indicate a running toilet, irrigation issue, or slow leak. Would you like me to monitor this?",
        safety_rules=[],
        escalation_conditions={"percent_increase": 100, "sustained_hours": 24},
        min_confidence_for_action=0.6,
        min_confidence_for_auto_action=0.95  # High bar for auto-action
    ),

    "hvac_slow_cooling": ReasoningTemplate(
        scenario_id="hvac_slow_cooling",
        category=ScenarioCategory.HVAC_EFFICIENCY,
        name="AC Efficiency Degradation",
        reasoning_steps=[
            "1. OBSERVE: AC taking {percent_longer}% longer to reach setpoint",
            "2. CONTEXT: Outdoor temp is {outdoor_temp}°F, {comparison_note}",
            "3. CHECK: When was filter last changed? Any obstructions?",
            "4. POSSIBLE CAUSES: Dirty filter, low refrigerant, duct issues",
            "5. RECOMMENDATION: Check filter, schedule maintenance if persists",
        ],
        recommended_actions=[
            {"action": "notify", "message": "AC efficiency may be degraded"},
            {"action": "create_maintenance_task", "type": "hvac_check"}
        ],
        user_message_template="Your AC is taking {percent_longer}% longer than usual to cool the house.",
        detail_template="This could be due to a dirty air filter, low refrigerant, or duct issues. When did you last change the filter? If it's been over 90 days, I recommend replacing it.",
        safety_rules=[],
        escalation_conditions={"percent_longer": 50, "outdoor_temp_above": 95},
        min_confidence_for_action=0.7,
        min_confidence_for_auto_action=0.95
    ),

    "comfort_room_cold": ReasoningTemplate(
        scenario_id="comfort_room_cold",
        category=ScenarioCategory.COMFORT,
        name="Room Too Cold",
        reasoning_steps=[
            "1. OBSERVE: {location} is {temp}°F, below comfort threshold",
            "2. COMPARE: Other rooms are {other_room_temp}°F",
            "3. CHECK: Is there a draft? Open window? Vent blocked?",
            "4. LEARN: User preference history suggests {preferred_temp}°F",
            "5. RECOMMENDATION: Adjust thermostat or investigate draft",
        ],
        recommended_actions=[
            {"action": "set_temperature", "delta": 2, "device_type": "thermostat"},
        ],
        user_message_template="{location} is a bit cold at {temp}°F.",
        detail_template="Based on your preferences, you typically like it around {preferred_temp}°F. Would you like me to increase the temperature by 2 degrees?",
        safety_rules=["hvac_temp_change_small"],
        escalation_conditions={},
        min_confidence_for_action=0.7,
        min_confidence_for_auto_action=0.85
    ),

    "co2_high_bedroom": ReasoningTemplate(
        scenario_id="co2_high_bedroom",
        category=ScenarioCategory.AIR_QUALITY,
        name="Bedroom CO2 High",
        reasoning_steps=[
            "1. OBSERVE: CO2 in bedroom is {co2_ppm} ppm, above 1000 ppm",
            "2. CONTEXT: It's {time}, door is {door_status}",
            "3. IMPACT: High CO2 affects sleep quality and alertness",
            "4. SOLUTION: Improve ventilation - open door or window",
            "5. RECOMMENDATION: Consider opening bedroom door",
        ],
        recommended_actions=[
            {"action": "notify", "message": "Bedroom CO2 is elevated"},
            {"action": "suggest", "message": "Consider opening the bedroom door"}
        ],
        user_message_template="CO2 levels in the bedroom are elevated at {co2_ppm} ppm.",
        detail_template="This can affect sleep quality. Try opening the bedroom door or cracking a window to improve air circulation. The fresh air will help you sleep better.",
        safety_rules=[],
        escalation_conditions={"co2_above": 1500},
        min_confidence_for_action=0.6,
        min_confidence_for_auto_action=0.95
    ),

    "battery_low": ReasoningTemplate(
        scenario_id="battery_low",
        category=ScenarioCategory.MAINTENANCE,
        name="Sensor Battery Low",
        reasoning_steps=[
            "1. OBSERVE: {sensor_name} battery is at {battery_percent}%",
            "2. ESTIMATE: Based on drain rate, ~{days_remaining} days remaining",
            "3. IMPORTANCE: This sensor monitors {sensor_purpose}",
            "4. RECOMMENDATION: Replace battery soon",
        ],
        recommended_actions=[
            {"action": "notify", "message": "Sensor battery low"},
            {"action": "create_maintenance_task", "type": "battery_replacement"}
        ],
        user_message_template="{sensor_name} battery is low ({battery_percent}%).",
        detail_template="I estimate about {days_remaining} days of battery life remaining. This is your {sensor_purpose} sensor, so I recommend replacing the battery soon to avoid gaps in monitoring.",
        safety_rules=[],
        escalation_conditions={"battery_below": 10},
        min_confidence_for_action=0.8,
        min_confidence_for_auto_action=0.99  # Don't auto-act on maintenance
    ),

    "routine_deviation": ReasoningTemplate(
        scenario_id="routine_deviation",
        category=ScenarioCategory.BEHAVIORAL,
        name="Unusual Activity Pattern",
        reasoning_steps=[
            "1. OBSERVE: Activity pattern differs from typical {day_of_week}",
            "2. NORMAL: Usually {normal_pattern} at this time",
            "3. CURRENT: Detected {current_pattern}",
            "4. CONTEXT: {contextual_factors}",
            "5. NOTE: This may be normal variation or worth noting",
        ],
        recommended_actions=[
            {"action": "log", "message": "Routine deviation noted"}
        ],
        user_message_template="I noticed something different from your usual {day_of_week} routine.",
        detail_template="You typically {normal_pattern} around this time, but today {current_pattern}. Just wanted to let you know in case this wasn't intentional.",
        safety_rules=[],
        escalation_conditions={"security_mode": "away"},
        min_confidence_for_action=0.8,
        min_confidence_for_auto_action=0.99
    ),
}


class ScenarioDetector:
    """Detects scenarios from fused context using signatures"""

    def __init__(
        self,
        signatures: Optional[Dict[str, ScenarioSignature]] = None,
        device_ontology = None  # DeviceOntology for zone attributes
    ):
        self.signatures = signatures or SCENARIO_SIGNATURES
        self.ontology = device_ontology

    def set_ontology(self, ontology):
        """Set or update the device ontology (for zone attributes)"""
        self.ontology = ontology

    def detect(self, context: FusedContext) -> List[ScenarioMatch]:
        """Detect all matching scenarios from context"""
        matches = []

        for sig_id, signature in self.signatures.items():
            match_result = self._check_signature(signature, context)
            if match_result:
                # Apply zone-based severity adjustments
                match_result = self._apply_zone_modifiers(match_result, context)
                matches.append(match_result)

        # Sort by severity (critical first) then confidence
        severity_order = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
            Severity.INFO: 4
        }
        matches.sort(key=lambda m: (severity_order.get(m.severity, 5), -m.match_confidence))

        return matches

    def _apply_zone_modifiers(
        self,
        match: ScenarioMatch,
        context: FusedContext
    ) -> ScenarioMatch:
        """Apply zone attribute-based severity modifiers"""
        if not self.ontology:
            return match
        
        # Get zone from trigger signal or context
        zone_id = None
        if context.trigger_signal:
            zone_id = context.trigger_signal.metadata.get("zone_id")
        
        if not zone_id:
            return match
        
        zone_attrs = self.ontology.get_zone_attributes(zone_id)
        if not zone_attrs:
            return match
        
        # Water leak + hardwood floors = escalate
        if match.category == ScenarioCategory.WATER_SAFETY:
            if zone_attrs.floor_type == "hardwood":
                match.severity = Severity.CRITICAL
                match.context_values["zone_risk"] = "hardwood_floors"
                match.matched_conditions.append("hardwood_floor_damage_risk")
        
        # High humidity + basement with sump pump = higher concern
        if match.scenario_id == "humidity_high_mold":
            if zone_attrs.has_sump_pump:
                match.context_values["zone_risk"] = "sump_pump_present"
                match.matched_conditions.append("sump_pump_area")
        
        # Temperature issues + infant/elderly = escalate
        if match.category == ScenarioCategory.COMFORT:
            if zone_attrs.has_infant:
                if match.severity in (Severity.LOW, Severity.INFO):
                    match.severity = Severity.MEDIUM
                match.context_values["vulnerable_occupant"] = "infant"
                match.matched_conditions.append("infant_safety")
            elif zone_attrs.has_elderly:
                if match.severity in (Severity.LOW, Severity.INFO):
                    match.severity = Severity.MEDIUM
                match.context_values["vulnerable_occupant"] = "elderly"
                match.matched_conditions.append("elderly_safety")
        
        # Smoke/CO in zone with HVAC return = critical (spread risk)
        if match.category == ScenarioCategory.AIR_QUALITY:
            if zone_attrs.has_hvac_return:
                match.severity = Severity.CRITICAL
                match.context_values["hvac_spread_risk"] = True
                match.matched_conditions.append("hvac_return_spread_risk")
        
        # Valuables present = higher priority for water/security
        if zone_attrs.has_valuables:
            if match.category in (ScenarioCategory.WATER_SAFETY, ScenarioCategory.SECURITY):
                if match.severity == Severity.LOW:
                    match.severity = Severity.MEDIUM
                match.context_values["valuables_at_risk"] = True
        
        return match

    def _check_signature(
        self,
        signature: ScenarioSignature,
        context: FusedContext
    ) -> Optional[ScenarioMatch]:
        """Check if a signature matches the context"""
        matched_conditions = []
        context_values = {}

        # Check threshold conditions
        for key, condition in signature.threshold_conditions.items():
            value = self._get_context_value(key, context)
            if value is None:
                continue

            context_values[key] = value

            if isinstance(condition, dict):
                if "min" in condition and value < condition["min"]:
                    continue
                if "max" in condition and value > condition["max"]:
                    continue
                matched_conditions.append(key)
            elif isinstance(condition, bool):
                if bool(value) == condition:
                    matched_conditions.append(key)
            elif value == condition:
                matched_conditions.append(key)

        # Check temporal conditions
        if signature.temporal_conditions:
            for key, values in signature.temporal_conditions.items():
                temporal_value = self._get_temporal_value(key, context)
                if temporal_value and temporal_value in values:
                    matched_conditions.append(f"temporal_{key}")

        # Calculate confidence
        total_conditions = len(signature.threshold_conditions)
        if signature.temporal_conditions:
            total_conditions += len(signature.temporal_conditions)

        if total_conditions == 0:
            return None

        confidence = len(matched_conditions) / total_conditions

        # Require minimum match
        if confidence < 0.5:
            return None

        # Adjust severity based on urgency factors
        severity = signature.base_severity
        for factor in signature.urgency_factors:
            if self._check_urgency_factor(factor, context, context_values):
                # Escalate severity
                if severity == Severity.INFO:
                    severity = Severity.LOW
                elif severity == Severity.LOW:
                    severity = Severity.MEDIUM
                elif severity == Severity.MEDIUM:
                    severity = Severity.HIGH

        return ScenarioMatch(
            scenario_id=signature.scenario_id,
            scenario_name=signature.name,
            category=signature.category,
            match_confidence=confidence,
            matched_conditions=matched_conditions,
            severity=severity,
            context_values=context_values
        )

    def _get_context_value(self, key: str, context: FusedContext) -> Any:
        """Get a value from context by key"""
        # Direct attributes
        if key == "indoor_humidity" and context.indoor_humidity is not None:
            return context.indoor_humidity
        if key == "indoor_temp" and context.indoor_temp is not None:
            return context.indoor_temp
        if key == "outdoor_aqi" and context.weather and context.weather.aqi:
            return context.weather.aqi

        # Active alarms
        if key == "leak_active":
            return len(context.active_leaks) > 0

        # Trends
        if key.startswith("humidity_trend"):
            for k, v in context.trend_1h.items():
                if "humidity" in k:
                    return v

        # Behavioral
        if key == "routine_deviation_score" and context.behavioral:
            return context.behavioral.routine_deviation_score

        # Room conditions
        for room, conditions in context.room_conditions.items():
            if key == "location" and room.lower() == key.lower():
                return room
            for cond_key, cond_val in conditions.items():
                if cond_key == key:
                    return cond_val

        return None

    def _get_temporal_value(self, key: str, context: FusedContext) -> Any:
        """Get temporal value from context"""
        if key == "season":
            return context.temporal.season
        if key == "is_nighttime":
            return not context.temporal.is_daytime
        if key == "is_occupied" and context.behavioral:
            return context.behavioral.occupancy_probability > 0.5
        if key == "weather_hot" and context.weather:
            return context.weather.is_hot
        return None

    def _check_urgency_factor(
        self,
        factor: str,
        context: FusedContext,
        values: Dict[str, Any]
    ) -> bool:
        """Check if an urgency factor is present"""
        if factor == "humidity_below_25":
            return values.get("indoor_humidity", 100) < 25
        if factor == "humidity_above_70":
            return values.get("indoor_humidity", 0) > 70
        if factor == "battery_below_10":
            return values.get("battery_percent", 100) < 10
        # Add more urgency factor checks as needed
        return False


class ReasoningEngine:
    """Applies reasoning templates to matched scenarios"""

    def __init__(self, templates: Optional[Dict[str, ReasoningTemplate]] = None):
        self.templates = templates or REASONING_TEMPLATES
        self.detector = ScenarioDetector()

    async def reason(
        self,
        context: FusedContext,
        matched_scenarios: Optional[List[ScenarioMatch]] = None
    ) -> ReasoningResult:
        """
        Apply reasoning to fused context.

        Args:
            context: Fused sensor context
            matched_scenarios: Pre-detected scenarios (optional)

        Returns:
            ReasoningResult with chain-of-thought and recommendations
        """
        start_time = datetime.now()

        # Detect scenarios if not provided
        if matched_scenarios is None:
            matched_scenarios = self.detector.detect(context)

        if not matched_scenarios:
            return ReasoningResult(
                trigger_type="none",
                primary_conclusion="No actionable scenarios detected",
                primary_confidence=1.0,
                timestamp=datetime.now()
            )

        # Get primary scenario
        primary = matched_scenarios[0]
        template = self.templates.get(primary.scenario_id)

        # Build reasoning chain
        reasoning_chain = None
        if template:
            reasoning_chain = self._build_chain(template, primary, context)

        # Extract insights from all matched scenarios
        insights = []
        for match in matched_scenarios:
            insight = self._scenario_to_insight(match, context)
            insights.append(insight)

        # Get recommended actions from primary template
        recommended_actions = []
        if template:
            recommended_actions = self._get_actions(template, primary, context)

        # Build primary conclusion
        primary_conclusion = self._format_conclusion(primary, template, context)

        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)

        return ReasoningResult(
            trigger_type=primary.category.value,
            trigger_device_id=context.trigger_signal.device_id if context.trigger_signal else None,
            reasoning_chain=reasoning_chain,
            insights=insights,
            primary_conclusion=primary_conclusion,
            primary_confidence=primary.match_confidence,
            recommended_actions=recommended_actions,
            timestamp=datetime.now(),
            processing_time_ms=processing_time
        )

    def _build_chain(
        self,
        template: ReasoningTemplate,
        match: ScenarioMatch,
        context: FusedContext
    ) -> ReasoningChain:
        """Build chain-of-thought reasoning"""
        steps = []

        for i, step_template in enumerate(template.reasoning_steps):
            # Format step with context values
            formatted_step = self._format_template(step_template, match, context)

            steps.append(ReasoningStep(
                step_number=i + 1,
                description=formatted_step,
                confidence=match.match_confidence
            ))

        return ReasoningChain(
            scenario=match.category,
            trigger=match.scenario_name,
            steps=steps,
            conclusion=template.user_message_template,
            confidence=match.match_confidence
        )

    def _scenario_to_insight(
        self,
        match: ScenarioMatch,
        context: FusedContext
    ) -> Insight:
        """Convert scenario match to insight"""
        template = self.templates.get(match.scenario_id)

        if template:
            title = self._format_template(template.user_message_template, match, context)
            description = self._format_template(template.detail_template, match, context)
        else:
            title = match.scenario_name
            description = f"Detected with {match.match_confidence:.0%} confidence"

        return Insight(
            category=match.category,
            severity=match.severity,
            title=title,
            description=description,
            evidence=match.matched_conditions,
            confidence=match.match_confidence,
            actionable=template is not None and len(template.recommended_actions) > 0
        )

    def _get_actions(
        self,
        template: ReasoningTemplate,
        match: ScenarioMatch,
        context: FusedContext
    ) -> List[Dict[str, Any]]:
        """Get recommended actions from template"""
        actions = []

        for action_template in template.recommended_actions:
            action = dict(action_template)

            # Add context-specific values
            action["scenario_id"] = match.scenario_id
            action["confidence"] = match.match_confidence
            action["severity"] = match.severity.value

            actions.append(action)

        return actions

    def _format_conclusion(
        self,
        match: ScenarioMatch,
        template: Optional[ReasoningTemplate],
        context: FusedContext
    ) -> str:
        """Format primary conclusion"""
        if template:
            return self._format_template(template.user_message_template, match, context)
        return match.scenario_name

    def _format_template(
        self,
        template: str,
        match: ScenarioMatch,
        context: FusedContext
    ) -> str:
        """Format a template string with context values"""
        values = dict(match.context_values)

        # Add common values
        if context.indoor_temp:
            values["temp"] = f"{context.indoor_temp:.1f}"
            values["indoor_temp"] = f"{context.indoor_temp:.1f}"
        if context.indoor_humidity:
            values["humidity"] = f"{context.indoor_humidity:.0f}"
            values["indoor_humidity"] = f"{context.indoor_humidity:.0f}"
        if context.weather:
            values["outdoor_temp"] = f"{context.weather.temperature:.0f}"
            values["outdoor_humidity"] = f"{context.weather.humidity}"
            values["weather_context"] = context.weather.description
        if context.temporal:
            values["season"] = context.temporal.season
            values["time"] = context.temporal.timestamp.strftime("%I:%M %p")
            values["day_of_week"] = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][context.temporal.day_of_week]

        # Add trigger info
        if context.trigger_signal:
            values["sensor_id"] = context.trigger_signal.sensor_id
            values["location"] = context.trigger_signal.metadata.get("location", "unknown")

        # Safe format (ignore missing keys)
        try:
            return template.format(**values)
        except KeyError:
            # Return template with unfilled placeholders
            return template

    def get_template(self, scenario_id: str) -> Optional[ReasoningTemplate]:
        """Get reasoning template by ID"""
        return self.templates.get(scenario_id)
