"""
Climate Insights Pipeline

Hybrid approach: Rule-based data computation + LLM reasoning

Architecture:
1. compute_climate_context() - Pure data computation, no LLM
2. generate_rule_based_insights() - Deterministic fallback insights
3. generate_llm_insights() - LLM with strict guardrails
"""

import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import httpx

from .prompts import get_prompt

logger = logging.getLogger(__name__)


# =============================================================================
# DATA MODELS
# =============================================================================

class RoomClimateStats(BaseModel):
    """Climate statistics for a single room/device"""
    room_id: str
    room_name: str
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    zone_type: Optional[str] = None  # bedroom, office, basement, etc.

    # Readings
    temperature: Optional[float] = None
    humidity: Optional[float] = None

    # Flags (computed from thresholds)
    temp_deviation_from_avg: Optional[float] = None  # degrees from home average
    is_temp_outlier: bool = False  # >5°F from average
    humidity_status: Optional[str] = None  # "too_dry", "ideal", "too_humid"


class ZoneClimateStats(BaseModel):
    """Aggregated climate statistics for a zone"""
    zone_id: str
    zone_name: str
    zone_type: Optional[str] = None

    # Zone attributes (from /api/zones)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    # e.g., insulation="poor", windows="single_pane", floor="attic", exposure="south"

    # Aggregated stats
    room_count: int = 0
    avg_temperature: Optional[float] = None
    min_temperature: Optional[float] = None
    max_temperature: Optional[float] = None
    avg_humidity: Optional[float] = None
    min_humidity: Optional[float] = None
    max_humidity: Optional[float] = None

    # Flags
    has_temp_outlier: bool = False
    humidity_status: Optional[str] = None  # majority status


class GlobalClimateStats(BaseModel):
    """Home-wide climate statistics"""
    # Temperature
    temp_min: Optional[float] = None
    temp_max: Optional[float] = None
    temp_avg: Optional[float] = None
    temp_range: Optional[float] = None  # max - min
    temp_variation_level: Optional[str] = None  # "very_consistent", "consistent", "moderate", "significant"

    # Humidity
    humidity_min: Optional[float] = None
    humidity_max: Optional[float] = None
    humidity_avg: Optional[float] = None

    # Counts
    total_rooms: int = 0
    rooms_too_dry: int = 0  # < 30%
    rooms_ideal_humidity: int = 0  # 30-50%
    rooms_too_humid: int = 0  # > 50%
    rooms_temp_outlier: int = 0  # >5°F from avg


class WeatherSummary(BaseModel):
    """Outdoor weather summary"""
    temperature: Optional[float] = None
    humidity: Optional[int] = None
    description: Optional[str] = None
    wind_speed: Optional[float] = None


class ClimateContext(BaseModel):
    """
    Complete climate context for LLM reasoning.

    This is the "ground truth" - all numeric facts are pre-computed.
    The LLM must not invent numbers; it can only reference values in this structure.
    """
    timestamp: datetime = Field(default_factory=datetime.now)

    # Global stats
    global_stats: GlobalClimateStats = Field(default_factory=GlobalClimateStats)

    # Per-room stats (device level)
    rooms: List[RoomClimateStats] = Field(default_factory=list)

    # Per-zone aggregated stats
    zones: List[ZoneClimateStats] = Field(default_factory=list)

    # Outdoor weather
    weather: Optional[WeatherSummary] = None

    # Categorized room lists (for easy LLM reference)
    rooms_too_dry: List[str] = Field(default_factory=list)  # room names with humidity < 30%
    rooms_too_humid: List[str] = Field(default_factory=list)  # room names with humidity > 50%
    rooms_ideal_humidity: List[str] = Field(default_factory=list)  # room names 30-50%
    rooms_temp_hot: List[str] = Field(default_factory=list)  # rooms >5°F above avg
    rooms_temp_cold: List[str] = Field(default_factory=list)  # rooms >5°F below avg


class ClimateInsight(BaseModel):
    """A single climate insight"""
    type: str  # "info", "warning", "success"
    title: str
    description: str


# =============================================================================
# THRESHOLDS (constants)
# =============================================================================

HUMIDITY_TOO_DRY = 30
HUMIDITY_TOO_HUMID = 50
TEMP_OUTLIER_THRESHOLD = 4.0  # degrees F from average (lowered from 5.0 to catch more outliers)

TEMP_VARIATION_THRESHOLDS = {
    "very_consistent": 3.0,
    "consistent": 5.0,
    "moderate": 8.0,
    # > 8.0 = "significant"
}


# =============================================================================
# COMPUTE CLIMATE CONTEXT (Pure Data)
# =============================================================================

async def compute_climate_context(
    backend_url: str,
    weather_service: Any,
) -> ClimateContext:
    """
    Compute all climate facts from devices and zones.

    This is pure data computation - no LLM, no insights.
    All numeric calculations happen here.
    """
    context = ClimateContext()

    # Fetch zones and devices in parallel
    zones_data = {}
    devices_data = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Fetch zones
        try:
            resp = await client.get(f"{backend_url}/api/zones")
            resp.raise_for_status()
            zones_list = resp.json()
            zones_data = {z["id"]: z for z in zones_list}
            logger.debug(f"Fetched {len(zones_data)} zones")
        except Exception as e:
            logger.warning(f"Failed to fetch zones: {e}")

        # Fetch devices
        try:
            resp = await client.get(f"{backend_url}/api/devices")
            resp.raise_for_status()
            data = resp.json()
            devices_data = data.get("devices", []) if isinstance(data, dict) else data
            logger.debug(f"Fetched {len(devices_data)} devices")
        except Exception as e:
            logger.error(f"Failed to fetch devices: {e}")
            return context

    # Fetch weather
    try:
        weather_ctx = await weather_service.get_environmental_context()
        if weather_ctx and weather_ctx.weather:
            context.weather = WeatherSummary(
                temperature=weather_ctx.weather.temperature,
                humidity=weather_ctx.weather.humidity,
                description=weather_ctx.weather.description,
                wind_speed=weather_ctx.weather.wind_speed,
            )
    except Exception as e:
        logger.warning(f"Failed to fetch weather: {e}")

    # Extract climate readings from devices
    all_temps: List[float] = []
    all_humidity: List[float] = []
    room_stats: List[RoomClimateStats] = []
    zone_readings: Dict[str, Dict[str, List[float]]] = {}  # zone_id -> {temps: [], humidity: []}

    for device in devices_data:
        readings = device.get("readings", {})
        device_id = device.get("id", "")
        # Prefer display_name (user-set) over name (model name) for human-readable output
        device_name = device.get("display_name") or device.get("name") or device_id
        zone_id = device.get("zone_id", "")

        # Get temperature (support both field names)
        temp = readings.get("temperature") or readings.get("temperature_f")
        humidity = readings.get("humidity")

        # Skip devices without climate readings
        if temp is None and humidity is None:
            continue

        # Create room stats
        room = RoomClimateStats(
            room_id=device_id,
            room_name=device_name,
            zone_id=zone_id if zone_id else None,
        )

        # Get zone info
        if zone_id and zone_id in zones_data:
            zone = zones_data[zone_id]
            room.zone_name = zone.get("name", zone_id)
            room.zone_type = zone.get("type")

        # Temperature
        if temp is not None:
            try:
                temp_f = float(temp)
                room.temperature = temp_f
                all_temps.append(temp_f)

                # Track per-zone
                if zone_id:
                    if zone_id not in zone_readings:
                        zone_readings[zone_id] = {"temps": [], "humidity": []}
                    zone_readings[zone_id]["temps"].append(temp_f)
            except (ValueError, TypeError):
                pass

        # Humidity
        if humidity is not None:
            try:
                hum_f = float(humidity)
                room.humidity = hum_f
                all_humidity.append(hum_f)

                # Use zone name if available, otherwise device name
                display_name = room.zone_name or device_name

                # Categorize humidity
                if hum_f < HUMIDITY_TOO_DRY:
                    room.humidity_status = "too_dry"
                    context.rooms_too_dry.append(f"{display_name} ({hum_f:.0f}%)")
                elif hum_f > HUMIDITY_TOO_HUMID:
                    room.humidity_status = "too_humid"
                    context.rooms_too_humid.append(f"{display_name} ({hum_f:.0f}%)")
                else:
                    room.humidity_status = "ideal"
                    context.rooms_ideal_humidity.append(f"{display_name} ({hum_f:.0f}%)")

                # Track per-zone
                if zone_id:
                    if zone_id not in zone_readings:
                        zone_readings[zone_id] = {"temps": [], "humidity": []}
                    zone_readings[zone_id]["humidity"].append(hum_f)
            except (ValueError, TypeError):
                pass

        room_stats.append(room)

    # Compute global stats
    if all_temps:
        context.global_stats.temp_min = min(all_temps)
        context.global_stats.temp_max = max(all_temps)
        context.global_stats.temp_avg = sum(all_temps) / len(all_temps)
        context.global_stats.temp_range = context.global_stats.temp_max - context.global_stats.temp_min

        # Classify temperature variation
        temp_range = context.global_stats.temp_range
        if temp_range < TEMP_VARIATION_THRESHOLDS["very_consistent"]:
            context.global_stats.temp_variation_level = "very_consistent"
        elif temp_range < TEMP_VARIATION_THRESHOLDS["consistent"]:
            context.global_stats.temp_variation_level = "consistent"
        elif temp_range < TEMP_VARIATION_THRESHOLDS["moderate"]:
            context.global_stats.temp_variation_level = "moderate"
        else:
            context.global_stats.temp_variation_level = "significant"

        # Compute per-room deviation and outliers
        avg_temp = context.global_stats.temp_avg
        for room in room_stats:
            if room.temperature is not None:
                deviation = room.temperature - avg_temp
                room.temp_deviation_from_avg = round(deviation, 1)
                # Use zone name if available for display
                display_name = room.zone_name or room.room_name
                if abs(deviation) > TEMP_OUTLIER_THRESHOLD:
                    room.is_temp_outlier = True
                    context.global_stats.rooms_temp_outlier += 1
                    if deviation > 0:
                        context.rooms_temp_hot.append(
                            f"{display_name} ({room.temperature:.1f}°F, +{deviation:.1f}°F)"
                        )
                    else:
                        context.rooms_temp_cold.append(
                            f"{display_name} ({room.temperature:.1f}°F, {deviation:.1f}°F)"
                        )

    if all_humidity:
        context.global_stats.humidity_min = min(all_humidity)
        context.global_stats.humidity_max = max(all_humidity)
        context.global_stats.humidity_avg = sum(all_humidity) / len(all_humidity)

    # Count humidity categories
    context.global_stats.total_rooms = len(room_stats)
    context.global_stats.rooms_too_dry = len(context.rooms_too_dry)
    context.global_stats.rooms_ideal_humidity = len(context.rooms_ideal_humidity)
    context.global_stats.rooms_too_humid = len(context.rooms_too_humid)

    context.rooms = room_stats

    # Build zone-level stats
    for zone_id, zone_info in zones_data.items():
        readings = zone_readings.get(zone_id, {"temps": [], "humidity": []})

        zone_stats = ZoneClimateStats(
            zone_id=zone_id,
            zone_name=zone_info.get("name", zone_id),
            zone_type=zone_info.get("type"),
            attributes=zone_info.get("attributes") or {},  # Handle None
            room_count=len(readings["temps"]) or len(readings["humidity"]),
        )

        if readings["temps"]:
            zone_stats.avg_temperature = sum(readings["temps"]) / len(readings["temps"])
            zone_stats.min_temperature = min(readings["temps"])
            zone_stats.max_temperature = max(readings["temps"])

            # Check if zone has outlier
            if context.global_stats.temp_avg:
                zone_dev = abs(zone_stats.avg_temperature - context.global_stats.temp_avg)
                zone_stats.has_temp_outlier = zone_dev > TEMP_OUTLIER_THRESHOLD

        if readings["humidity"]:
            zone_stats.avg_humidity = sum(readings["humidity"]) / len(readings["humidity"])
            zone_stats.min_humidity = min(readings["humidity"])
            zone_stats.max_humidity = max(readings["humidity"])

            # Majority humidity status
            avg_h = zone_stats.avg_humidity
            if avg_h < HUMIDITY_TOO_DRY:
                zone_stats.humidity_status = "too_dry"
            elif avg_h > HUMIDITY_TOO_HUMID:
                zone_stats.humidity_status = "too_humid"
            else:
                zone_stats.humidity_status = "ideal"

        if zone_stats.room_count > 0:
            context.zones.append(zone_stats)

    return context


# =============================================================================
# RULE-BASED INSIGHTS (Fallback)
# =============================================================================

def _get_zone_climate_analysis(zone: ZoneClimateStats, is_hot: bool) -> Dict[str, Any]:
    """
    Analyze zone attributes for climate issues - FACT-BASED ONLY.

    Only reports facts from actual attribute values, never assumes or guesses.

    Returns dict with:
    - facts: List of relevant facts from attributes
    - recommendations: List of actionable recommendations based on facts
    """
    facts = []
    recommendations = []
    attrs = zone.attributes
    zone_type = (zone.zone_type or "").lower()

    if not attrs:
        return {"facts": [], "recommendations": []}

    # === INSULATION (only if explicitly set) ===
    insulation = str(attrs.get("Insulation", attrs.get("insulation", ""))).lower()
    if insulation == "none":
        facts.append("has no insulation")
        recommendations.append("adding insulation would help regulate temperature")
    elif insulation and insulation not in ("", "none"):
        facts.append(f"has {insulation} insulation")

    # === HVAC FEATURES (only report what's explicitly set) ===
    # Check if attribute exists AND is True (not just truthiness)
    if attrs.get("has_hvac_vent") is True:
        facts.append("has HVAC vent")
        if is_hot:
            recommendations.append("verify vent is open and unobstructed")
    elif attrs.get("has_hvac_vent") is False:
        facts.append("no HVAC vent")
        if is_hot:
            recommendations.append("consider adding cooling source")
        elif not is_hot:
            recommendations.append("consider adding heat source")

    if attrs.get("has_hvac_return") is True:
        facts.append("has HVAC return")
    elif attrs.get("has_hvac_return") is False:
        facts.append("no HVAC return (may limit airflow)")

    if attrs.get("has_radiators") is True:
        facts.append("has radiators")
    elif attrs.get("has_radiators") is False and not is_hot:
        facts.append("no radiators")

    if attrs.get("has_radiant_heat") is True:
        facts.append("has radiant floor heat")

    if attrs.get("has_ceiling_fan") is True:
        facts.append("has ceiling fan")
        recommendations.append("use ceiling fan to circulate air")
    elif attrs.get("has_ceiling_fan") is False and is_hot:
        facts.append("no ceiling fan")

    # === WINDOWS (only if explicitly set) ===
    if attrs.get("has_windows") is True:
        facts.append("has windows")
        if is_hot:
            recommendations.append("close blinds during peak sun")
        else:
            recommendations.append("check window seals for drafts")
    elif attrs.get("has_windows") is False:
        facts.append("no windows")

    # === HEAT-GENERATING EQUIPMENT (only if True) ===
    if attrs.get("has_water_heater") is True:
        facts.append("contains water heater")
        if is_hot:
            recommendations.append("water heater adds ambient heat")

    if attrs.get("has_washer") is True:
        facts.append("contains washer/dryer")
        if is_hot:
            recommendations.append("dryer adds heat when running")

    heating_system = attrs.get("has_heating_system", "")
    if heating_system and heating_system != "none":
        facts.append(f"contains {heating_system}")
        if is_hot:
            recommendations.append(f"{heating_system} equipment may add heat")

    cooling_system = attrs.get("has_cooling_system", "")
    if cooling_system and cooling_system != "none":
        facts.append(f"has {cooling_system}")
        if is_hot:
            recommendations.append(f"check {cooling_system} is working properly")

    # === ZONE TYPE (factual context) ===
    if zone_type == "basement":
        facts.append("basement zone (ground contact)")
    elif zone_type == "garage":
        facts.append("garage zone")
    elif "attic" in zone.zone_name.lower():
        facts.append("attic location (heat rises)")

    return {
        "facts": facts,
        "recommendations": recommendations
    }


def _format_zone_insight(zone: ZoneClimateStats, issue_type: str) -> str:
    """Format a zone-specific insight with fact-based analysis."""
    is_hot = issue_type == "hot"
    analysis = _get_zone_climate_analysis(zone, is_hot)

    parts = []

    if analysis["facts"]:
        parts.append(f"Zone info: {', '.join(analysis['facts'][:3])}")

    if analysis["recommendations"]:
        parts.append(f"Check: {', '.join(analysis['recommendations'][:2])}")

    return " ".join(parts) if parts else ""


def generate_rule_based_insights(context: ClimateContext) -> List[ClimateInsight]:
    """
    Generate deterministic insights from pre-computed context.

    No LLM needed. Uses simple rules on pre-computed facts.
    Leverages zone attributes for causal reasoning.
    """
    insights: List[ClimateInsight] = []
    gs = context.global_stats

    if gs.total_rooms == 0:
        return [ClimateInsight(
            type="info",
            title="No Climate Data",
            description="No climate sensors detected. Add temperature and humidity sensors to get insights."
        )]

    # Build zone lookup for attribute-based reasoning
    zones_by_name: Dict[str, ZoneClimateStats] = {}
    for zone in context.zones:
        zones_by_name[zone.zone_name.lower()] = zone
        # Also index by zone_id for direct lookups
        zones_by_name[zone.zone_id.lower()] = zone

    # === TEMPERATURE INSIGHTS ===
    if gs.temp_range is not None:
        variation = gs.temp_variation_level

        if variation == "very_consistent":
            insights.append(ClimateInsight(
                type="success",
                title="Excellent Temperature Balance",
                description=f"Temperature varies by only {gs.temp_range:.1f}°F across all zones "
                           f"({gs.temp_min:.1f}°F to {gs.temp_max:.1f}°F). HVAC is well-balanced."
            ))
        elif variation == "consistent":
            insights.append(ClimateInsight(
                type="info",
                title="Good Temperature Distribution",
                description=f"Temperature ranges from {gs.temp_min:.1f}°F to {gs.temp_max:.1f}°F "
                           f"({gs.temp_range:.1f}°F variation). Good comfort across zones."
            ))
        elif variation == "moderate":
            # Include specific outliers if any
            desc = f"Temperature varies {gs.temp_range:.1f}°F ({gs.temp_min:.1f}°F to {gs.temp_max:.1f}°F). "
            if context.rooms_temp_hot:
                desc += f"Warm: {', '.join(context.rooms_temp_hot[:2])}. "
            if context.rooms_temp_cold:
                desc += f"Cool: {', '.join(context.rooms_temp_cold[:2])}. "
            desc += "Consider checking airflow or insulation in outlier rooms."

            insights.append(ClimateInsight(
                type="info",
                title="Moderate Temperature Variation",
                description=desc
            ))
        else:  # significant
            desc = f"Significant temperature imbalance: {gs.temp_range:.1f}°F range "
            desc += f"({gs.temp_min:.1f}°F to {gs.temp_max:.1f}°F). "
            if context.rooms_temp_hot:
                desc += f"Hot spots: {', '.join(context.rooms_temp_hot[:3])}. "
            if context.rooms_temp_cold:
                desc += f"Cold spots: {', '.join(context.rooms_temp_cold[:3])}. "
            desc += "Check for air leaks, blocked vents, or insulation issues."

            insights.append(ClimateInsight(
                type="warning",
                title="Significant Temperature Imbalance",
                description=desc
            ))

    # === ZONE-SPECIFIC INSIGHTS (with attributes) ===
    # Generate insights for zones with outliers AND meaningful attributes
    for zone in context.zones:
        if not zone.has_temp_outlier or not zone.attributes:
            continue

        # Determine if hot or cold outlier
        if zone.avg_temperature and gs.temp_avg:
            deviation = zone.avg_temperature - gs.temp_avg
            if abs(deviation) > TEMP_OUTLIER_THRESHOLD:
                is_hot = deviation > 0
                cause_text = _format_zone_insight(zone, "hot" if is_hot else "cold")

                if cause_text:  # Only add if we have meaningful causes
                    if is_hot:
                        insights.append(ClimateInsight(
                            type="warning",
                            title=f"{zone.zone_name} Running Warm",
                            description=f"{zone.zone_name} averages {zone.avg_temperature:.1f}°F, "
                                       f"+{deviation:.1f}°F above home average.{cause_text}"
                        ))
                    else:
                        insights.append(ClimateInsight(
                            type="warning",
                            title=f"{zone.zone_name} Running Cool",
                            description=f"{zone.zone_name} averages {zone.avg_temperature:.1f}°F, "
                                       f"{deviation:.1f}°F below home average.{cause_text}"
                        ))

    # === HUMIDITY INSIGHTS ===
    # Determine overall humidity status
    total_with_humidity = gs.rooms_too_dry + gs.rooms_ideal_humidity + gs.rooms_too_humid

    if total_with_humidity > 0:
        if gs.rooms_too_dry == total_with_humidity:
            # ALL rooms too dry
            room_list = ", ".join(context.rooms_too_dry[:3])
            more = f" (+{len(context.rooms_too_dry) - 3} more)" if len(context.rooms_too_dry) > 3 else ""
            insights.append(ClimateInsight(
                type="warning",
                title="Air Too Dry Throughout Home",
                description=f"All {gs.rooms_too_dry} rooms are below 30% humidity. "
                           f"Rooms: {room_list}{more}. "
                           f"Low humidity causes dry skin and respiratory issues. Add humidifiers."
            ))
        elif gs.rooms_too_humid == total_with_humidity:
            # ALL rooms too humid
            room_list = ", ".join(context.rooms_too_humid[:3])
            more = f" (+{len(context.rooms_too_humid) - 3} more)" if len(context.rooms_too_humid) > 3 else ""
            insights.append(ClimateInsight(
                type="warning",
                title="Humidity Too High Throughout Home",
                description=f"All {gs.rooms_too_humid} rooms exceed 50% humidity. "
                           f"Rooms: {room_list}{more}. "
                           f"High humidity promotes mold. Use dehumidifiers."
            ))
        elif gs.rooms_ideal_humidity == total_with_humidity:
            # ALL rooms ideal
            room_list = ", ".join(context.rooms_ideal_humidity[:4])
            more = f" (+{len(context.rooms_ideal_humidity) - 4} more)" if len(context.rooms_ideal_humidity) > 4 else ""
            insights.append(ClimateInsight(
                type="success",
                title="Ideal Humidity Throughout Home",
                description=f"All {gs.rooms_ideal_humidity} rooms are in the optimal 30-50% range. "
                           f"Rooms: {room_list}{more}."
            ))
        else:
            # Mixed conditions - report issues
            if gs.rooms_too_dry > 0:
                room_list = ", ".join(context.rooms_too_dry[:3])
                more = f" (+{len(context.rooms_too_dry) - 3} more)" if len(context.rooms_too_dry) > 3 else ""
                insights.append(ClimateInsight(
                    type="warning",
                    title=f"{gs.rooms_too_dry} Room(s) Too Dry",
                    description=f"Below optimal 30% humidity: {room_list}{more}. "
                               f"Add humidifiers to these areas."
                ))

            if gs.rooms_too_humid > 0:
                room_list = ", ".join(context.rooms_too_humid[:3])
                more = f" (+{len(context.rooms_too_humid) - 3} more)" if len(context.rooms_too_humid) > 3 else ""
                insights.append(ClimateInsight(
                    type="warning",
                    title=f"{gs.rooms_too_humid} Room(s) Too Humid",
                    description=f"Above optimal 50% humidity: {room_list}{more}. "
                               f"Use dehumidifiers or improve ventilation."
                ))

    # === WEATHER CORRELATION ===
    if context.weather and context.weather.temperature is not None and gs.temp_avg is not None:
        outdoor = context.weather.temperature
        indoor_avg = gs.temp_avg

        if outdoor < 40 and indoor_avg > 65:
            insights.append(ClimateInsight(
                type="info",
                title="Effective Winter Heating",
                description=f"Outdoor: {outdoor:.0f}°F, Indoor avg: {indoor_avg:.1f}°F. "
                           f"Heating system maintains comfort despite cold weather."
            ))
        elif outdoor > 85 and indoor_avg < 78:
            insights.append(ClimateInsight(
                type="info",
                title="Effective Summer Cooling",
                description=f"Outdoor: {outdoor:.0f}°F, Indoor avg: {indoor_avg:.1f}°F. "
                           f"Cooling system keeps home comfortable despite heat."
            ))

    # Ensure we have at least one insight
    if not insights:
        insights.append(ClimateInsight(
            type="info",
            title="Climate Monitoring Active",
            description=f"Monitoring {gs.total_rooms} climate sensors. "
                       f"Avg temp: {gs.temp_avg:.1f}°F, Avg humidity: {gs.humidity_avg:.0f}%."
        ))

    return insights[:5]  # Limit to 5


# =============================================================================
# LLM INSIGHTS (with strict guardrails)
# =============================================================================

def build_llm_prompt(context: ClimateContext) -> str:
    """
    Build the LLM prompt with all pre-computed facts embedded.

    The LLM cannot invent numbers - it can only reference values from this prompt.
    Prompt template loaded from external YAML for hot-reload capability.
    """
    gs = context.global_stats

    # Build context sections
    sections = []

    # Global stats
    sections.append("## HOME CLIMATE SUMMARY (Pre-computed Facts)")
    if gs.temp_avg is not None:
        sections.append(f"- Temperature: {gs.temp_min:.1f}°F to {gs.temp_max:.1f}°F "
                       f"(range: {gs.temp_range:.1f}°F, avg: {gs.temp_avg:.1f}°F)")
        sections.append(f"- Temperature variation: {gs.temp_variation_level.upper().replace('_', ' ')}")
    if gs.humidity_avg is not None:
        sections.append(f"- Humidity: {gs.humidity_min:.0f}% to {gs.humidity_max:.0f}% "
                       f"(avg: {gs.humidity_avg:.0f}%)")
    sections.append(f"- Total rooms monitored: {gs.total_rooms}")

    # Humidity categorization
    sections.append("\n## HUMIDITY STATUS (Pre-categorized)")
    sections.append(f"- Too dry (<30%): {gs.rooms_too_dry} rooms")
    if context.rooms_too_dry:
        sections.append(f"  Rooms: {', '.join(context.rooms_too_dry)}")
    sections.append(f"- Ideal (30-50%): {gs.rooms_ideal_humidity} rooms")
    if context.rooms_ideal_humidity:
        sections.append(f"  Rooms: {', '.join(context.rooms_ideal_humidity)}")
    sections.append(f"- Too humid (>50%): {gs.rooms_too_humid} rooms")
    if context.rooms_too_humid:
        sections.append(f"  Rooms: {', '.join(context.rooms_too_humid)}")

    # Temperature outliers
    if context.rooms_temp_hot or context.rooms_temp_cold:
        sections.append("\n## TEMPERATURE OUTLIERS (>5°F from average)")
        if context.rooms_temp_hot:
            sections.append(f"- Warmer than avg: {', '.join(context.rooms_temp_hot)}")
        if context.rooms_temp_cold:
            sections.append(f"- Cooler than avg: {', '.join(context.rooms_temp_cold)}")

    # Zone details with attributes - format for easy LLM reasoning
    zones_with_attrs = [z for z in context.zones if z.attributes]
    if zones_with_attrs:
        sections.append("\n## ZONE ATTRIBUTES (FACTS - use these for analysis)")
        sections.append("These are known facts about each zone. Use them to explain temperature/humidity issues.")
        for zone in zones_with_attrs:
            sections.append(f"\n### {zone.zone_name} ({zone.zone_type})")
            if zone.avg_temperature:
                sections.append(f"  Temperature: {zone.avg_temperature:.1f}°F")
            if zone.avg_humidity:
                sections.append(f"  Humidity: {zone.avg_humidity:.0f}%")
            # Format attributes clearly
            for key, value in zone.attributes.items():
                if value is True:
                    sections.append(f"  ✓ {key.replace('_', ' ')}")
                elif value is False:
                    sections.append(f"  ✗ {key.replace('_', ' ')}: NO")
                elif value and value != "none":
                    sections.append(f"  • {key.replace('_', ' ')}: {value}")

    # Weather with seasonal context
    if context.weather:
        outdoor_temp = context.weather.temperature
        sections.append("\n## OUTDOOR WEATHER (USE FOR SEASONAL CONTEXT)")
        sections.append(f"- Temperature: {outdoor_temp:.0f}°F")
        sections.append(f"- Humidity: {context.weather.humidity}%")
        sections.append(f"- Conditions: {context.weather.description}")
        # Add explicit seasonal guidance
        if outdoor_temp < 50:
            sections.append(f"- SEASON: WINTER/COLD (outdoor {outdoor_temp:.0f}°F) - focus on HEATING issues, not AC")
        elif outdoor_temp > 75:
            sections.append(f"- SEASON: SUMMER/HOT (outdoor {outdoor_temp:.0f}°F) - focus on COOLING issues")
        else:
            sections.append(f"- SEASON: MILD (outdoor {outdoor_temp:.0f}°F)")

    context_text = "\n".join(sections)

    # Load prompt template from external YAML and format with context
    prompt = get_prompt(
        "climate_insights",
        "analysis_prompt",
        context=context_text,
        rooms_too_dry=gs.rooms_too_dry,
        rooms_ideal_humidity=gs.rooms_ideal_humidity,
        rooms_too_humid=gs.rooms_too_humid,
        temp_variation_level=gs.temp_variation_level or 'unknown',
        temp_range=f"{gs.temp_range:.1f}" if gs.temp_range else "0"
    )

    return prompt


async def generate_llm_insights(
    context: ClimateContext,
    llm_provider: Any,
) -> List[ClimateInsight]:
    """
    Generate insights using LLM with strict guardrails.

    The LLM receives pre-computed facts and must not invent numbers.
    Falls back to rule-based if LLM fails or is unavailable.
    """
    if not llm_provider or not llm_provider.is_available():
        logger.info("LLM unavailable, using rule-based insights")
        return generate_rule_based_insights(context)

    prompt = build_llm_prompt(context)

    try:
        response_text, _ = llm_provider.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,  # Low temperature for consistency
            max_tokens=1000,
        )

        # Parse JSON response
        response_text = response_text.strip()

        # Remove markdown code block if present
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1]) if len(lines) > 2 else response_text

        insights_data = json.loads(response_text)

        # Validate and convert
        insights = []
        for item in insights_data[:5]:
            insight = ClimateInsight(
                type=item.get("type", "info"),
                title=item.get("title", "Climate Insight"),
                description=item.get("description", "")
            )
            insights.append(insight)

        if insights:
            logger.info(f"LLM generated {len(insights)} climate insights")
            return insights
        else:
            logger.warning("LLM returned empty insights, falling back to rules")
            return generate_rule_based_insights(context)

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        return generate_rule_based_insights(context)
    except Exception as e:
        logger.error(f"LLM insight generation failed: {e}")
        return generate_rule_based_insights(context)


# =============================================================================
# VALIDATION (Post-processing check)
# =============================================================================

def validate_insights(insights: List[ClimateInsight], context: ClimateContext) -> List[ClimateInsight]:
    """
    Validate LLM-generated insights against ground truth.

    Removes insights that contradict the pre-computed facts.
    """
    gs = context.global_stats
    validated = []

    for insight in insights:
        desc_lower = insight.description.lower()
        title_lower = insight.title.lower()

        # Check for contradictions
        is_valid = True

        # Rule: Can't say "ideal humidity" if there are dry/humid rooms
        if "ideal humidity" in title_lower or "optimal humidity" in title_lower:
            if "throughout" in desc_lower or "all rooms" in desc_lower:
                if gs.rooms_too_dry > 0 or gs.rooms_too_humid > 0:
                    logger.warning(f"Rejecting insight: claims all ideal but {gs.rooms_too_dry} dry, {gs.rooms_too_humid} humid")
                    is_valid = False

        # Rule: Can't say "excellent balance" if variation is significant
        if "excellent" in title_lower and "balance" in title_lower:
            if gs.temp_variation_level == "significant":
                logger.warning(f"Rejecting insight: claims excellent balance but variation is significant")
                is_valid = False

        # Rule: Can't say "heating effective" for a room that's cooler than average
        if "heating" in desc_lower and ("effective" in desc_lower or "working well" in desc_lower):
            if "cooler than" in desc_lower or "below average" in desc_lower or "below the average" in desc_lower:
                logger.warning(f"Rejecting insight: claims heating effective but room is cooler than average")
                is_valid = False

        # Rule: Can't say "cooling effective" for a room that's warmer than average
        if "cooling" in desc_lower and ("effective" in desc_lower or "working well" in desc_lower):
            if "warmer than" in desc_lower or "above average" in desc_lower or "above the average" in desc_lower:
                logger.warning(f"Rejecting insight: claims cooling effective but room is warmer than average")
                is_valid = False

        if is_valid:
            validated.append(insight)

    return validated if validated else generate_rule_based_insights(context)


# =============================================================================
# TREND PATTERN ANALYSIS
# =============================================================================

class TrendPatternInsight(BaseModel):
    """A trend pattern insight for a specific device"""
    device_id: str
    device_name: str
    zone_name: Optional[str] = None
    metric: str  # "temperature" or "humidity"
    pattern_type: str  # "morning_low_evening_high", "diurnal_cycle", etc.
    daily_swing: float
    min_value: float
    max_value: float
    typical_low_time: Optional[str] = None
    typical_high_time: Optional[str] = None
    insight: str  # LLM-generated or rule-based explanation
    is_normal: bool = True
    likely_cause: Optional[str] = None
    recommendation: Optional[str] = None


async def analyze_trend_patterns(
    backend_url: str,
    learning_engine: Any,
    llm_provider: Any,
    zones_data: Dict[str, Any],
) -> List[TrendPatternInsight]:
    """
    Analyze temperature/humidity trend patterns for all climate devices.

    Steps:
    1. Fetch recent readings (48 hours) for each climate device
    2. Use ML engine to detect patterns (cyclical, erratic, etc.)
    3. Use LLM to generate human-readable insights

    Args:
        backend_url: Backend API URL
        learning_engine: HSILRiverLearningEngine instance
        llm_provider: LLM provider for generating insights
        zones_data: Dict of zone_id -> zone info

    Returns:
        List of TrendPatternInsight for devices with detected patterns
    """
    insights: List[TrendPatternInsight] = []

    # Fetch devices with climate readings
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{backend_url}/api/devices")
            resp.raise_for_status()
            data = resp.json()
            devices = data.get("devices", []) if isinstance(data, dict) else data
        except Exception as e:
            logger.error(f"Failed to fetch devices for trend analysis: {e}")
            return insights

        # Filter to climate devices (those with temperature or humidity)
        climate_devices = []
        for device in devices:
            readings = device.get("readings", {})
            if readings.get("temperature") or readings.get("temperature_f") or readings.get("humidity"):
                climate_devices.append(device)

        logger.debug(f"Analyzing trends for {len(climate_devices)} climate devices")

        # Track which device+metric combinations we've already analyzed
        analyzed_combinations: set[str] = set()

        # Analyze each device
        for device in climate_devices[:5]:  # Limit to 5 devices to avoid slow response
            device_id = device.get("id", "")
            device_name = device.get("display_name") or device.get("name", device_id)
            zone_id = device.get("zone_id", "")
            zone_info = zones_data.get(zone_id, {})
            zone_name = zone_info.get("name", zone_id) if zone_id else None

            readings_data = device.get("readings", {})

            # Check which metrics this device has
            for metric in ["temperature", "humidity"]:
                if metric not in readings_data and f"{metric}_f" not in readings_data:
                    continue

                # Skip if we've already analyzed this device+metric
                combo_key = f"{device_id}:{metric}"
                if combo_key in analyzed_combinations:
                    continue
                analyzed_combinations.add(combo_key)

                # Fetch historical readings (last 48 hours)
                try:
                    since = (datetime.now() - timedelta(hours=48)).isoformat() + "Z"
                    resp = await client.get(
                        f"{backend_url}/api/sensors/{device_id}/readings",
                        params={"type": metric, "since": since, "limit": 200}
                    )
                    if resp.status_code != 200:
                        continue

                    readings = resp.json()
                    if not readings or len(readings) < 6:
                        continue

                    # Analyze pattern using ML engine
                    pattern = await learning_engine.analyze_device_trend_pattern(
                        device_id=device_id,
                        metric=metric,
                        readings=readings
                    )

                    if not pattern or not pattern.get("pattern_detected"):
                        continue

                    # Generate insight - use rule-based for speed (skip LLM per-pattern)
                    # LLM calls per-pattern are too slow (~10s each)
                    # Use zone_name for display if available
                    display_name = zone_name if zone_name else device_name
                    llm_insight = {
                        "insight": _generate_rule_based_trend_insight(pattern, display_name),
                        "is_normal": pattern.get("pattern_type") == "morning_low_evening_high",
                        "likely_cause": "HVAC setback schedule" if pattern.get("pattern_type") == "morning_low_evening_high" else None,
                        "recommendation": None if pattern.get("daily_swing", 0) < 8 else "Consider checking HVAC or insulation",
                    }

                    insight = TrendPatternInsight(
                        device_id=device_id,
                        device_name=device_name,
                        zone_name=zone_name,
                        metric=metric,
                        pattern_type=pattern.get("pattern_type", "unknown"),
                        daily_swing=pattern.get("daily_swing", 0),
                        min_value=pattern.get("min_value", 0),
                        max_value=pattern.get("max_value", 0),
                        typical_low_time=pattern.get("typical_low_time"),
                        typical_high_time=pattern.get("typical_high_time"),
                        insight=llm_insight.get("insight", _generate_rule_based_trend_insight(pattern, device_name)),
                        is_normal=llm_insight.get("is_normal", True),
                        likely_cause=llm_insight.get("likely_cause"),
                        recommendation=llm_insight.get("recommendation"),
                    )
                    insights.append(insight)

                except Exception as e:
                    logger.warning(f"Failed to analyze trends for {device_id}/{metric}: {e}")
                    continue

    return insights


async def _generate_trend_llm_insight(
    pattern: Dict[str, Any],
    device_name: str,
    zone_name: Optional[str],
    zone_info: Dict[str, Any],
    llm_provider: Any,
) -> Dict[str, Any]:
    """
    Generate LLM insight for a detected trend pattern.

    Falls back to rule-based if LLM unavailable.
    """
    if not llm_provider or not llm_provider.is_available():
        return {
            "insight": _generate_rule_based_trend_insight(pattern, device_name),
            "is_normal": True,
            "likely_cause": "HVAC scheduling" if pattern.get("pattern_type") == "morning_low_evening_high" else None,
            "recommendation": None,
        }

    # Build context for LLM
    pattern_data = f"""
Device: {device_name} ({zone_name or 'Unknown Zone'})
Metric: {pattern.get('metric', 'temperature')}
Pattern Type: {pattern.get('pattern_type', 'unknown')}
Daily Swing: {pattern.get('daily_swing', 0)}°F
Min Value: {pattern.get('min_value', 0)}°F at {pattern.get('typical_low_time', 'unknown')}
Max Value: {pattern.get('max_value', 0)}°F at {pattern.get('typical_high_time', 'unknown')}
Current Deviation from Expected: {pattern.get('deviation_from_expected', 'N/A')}°F
Pattern Regularity: {pattern.get('pattern_regularity', 0):.0%}
"""

    # Zone context
    zone_context = "No zone attributes available."
    if zone_info:
        attrs = zone_info.get("attributes", {})
        if attrs:
            attr_list = []
            for k, v in attrs.items():
                if v is True:
                    attr_list.append(f"- Has {k.replace('_', ' ')}")
                elif v and v not in (False, "none", ""):
                    attr_list.append(f"- {k.replace('_', ' ')}: {v}")
            if attr_list:
                zone_context = f"Zone: {zone_name}\n" + "\n".join(attr_list[:5])

    try:
        prompt = get_prompt(
            "climate_insights",
            "trend_pattern_prompt",
            pattern_data=pattern_data,
            zone_context=zone_context,
        )

        response_text, _ = llm_provider.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300,
        )

        # Parse JSON response
        response_text = response_text.strip()
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1]) if len(lines) > 2 else response_text

        result = json.loads(response_text)
        return result

    except Exception as e:
        logger.warning(f"LLM trend insight failed: {e}")
        return {
            "insight": _generate_rule_based_trend_insight(pattern, device_name),
            "is_normal": True,
            "likely_cause": None,
            "recommendation": None,
        }


def _generate_rule_based_trend_insight(pattern: Dict[str, Any], device_name: str) -> str:
    """Generate a simple rule-based insight when LLM is unavailable."""
    pattern_type = pattern.get("pattern_type", "unknown")
    swing = pattern.get("daily_swing", 0)
    low_time = pattern.get("typical_low_time", "morning")
    high_time = pattern.get("typical_high_time", "evening")
    metric = pattern.get("metric", "temperature")

    # Use appropriate unit
    unit = "%" if metric == "humidity" else "°F"
    metric_label = "humidity" if metric == "humidity" else "temperature"

    if pattern_type == "morning_low_evening_high":
        if metric == "humidity":
            return f"{device_name} shows a regular daily humidity cycle: {swing:.0f}% swing from lows around {low_time} to highs around {high_time}."
        return f"{device_name} shows a regular daily cycle: {swing:.1f}°F swing from lows around {low_time} to highs around {high_time}. This is typical HVAC setback behavior."
    elif pattern_type == "morning_high_evening_low":
        return f"{device_name} shows an unusual pattern: highs in the morning, lows in the evening ({swing:.1f}{unit} swing). Consider checking HVAC schedule."
    else:
        return f"{device_name} shows a {swing:.1f}{unit} daily {metric_label} swing between {pattern.get('min_value', 0):.1f}{unit} and {pattern.get('max_value', 0):.1f}{unit}."
