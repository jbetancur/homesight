"""
HIL Type System - Core data structures for HomeSight Intelligence Layer

This module defines the unified type system for:
- Sensor fusion context
- Reasoning templates
- Safety decisions
- Intelligence pipeline results
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, List, Literal, Union
from datetime import datetime
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class Severity(str, Enum):
    """Severity levels for incidents and alerts"""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConfidenceLevel(str, Enum):
    """Confidence levels for predictions and decisions"""
    VERY_LOW = "very_low"      # < 0.3
    LOW = "low"                 # 0.3 - 0.5
    MEDIUM = "medium"           # 0.5 - 0.7
    HIGH = "high"               # 0.7 - 0.85
    VERY_HIGH = "very_high"     # > 0.85


class ActionMode(str, Enum):
    """Whether to ask user or act autonomously"""
    ASK = "ask"                 # Require user confirmation
    SUGGEST = "suggest"         # Suggest but don't act
    ACT = "act"                 # Act autonomously
    ACT_AND_NOTIFY = "act_and_notify"  # Act but notify user


class ScenarioCategory(str, Enum):
    """Categories of reasoning scenarios"""
    COMFORT = "comfort"
    WATER_SAFETY = "water_safety"
    HVAC_EFFICIENCY = "hvac_efficiency"
    AIR_QUALITY = "air_quality"
    HUMIDITY = "humidity"
    BEHAVIORAL = "behavioral"
    MAINTENANCE = "maintenance"
    SECURITY = "security"
    ENERGY = "energy"


class SignalType(str, Enum):
    """Types of input signals for fusion"""
    SENSOR_READING = "sensor_reading"
    WEATHER = "weather"
    TIME_CONTEXT = "time_context"
    BEHAVIORAL_PATTERN = "behavioral_pattern"
    HISTORICAL_BASELINE = "historical_baseline"
    USER_FEEDBACK = "user_feedback"
    EXTERNAL_API = "external_api"


class SensorType(str, Enum):
    """Types of sensors in the home"""
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    MOTION = "motion"
    CONTACT = "contact"
    LEAK = "leak"
    SMOKE = "smoke"
    CO = "co"
    CO2 = "co2"
    LIGHT = "light"
    POWER = "power"
    WATER_FLOW = "water_flow"
    PRESSURE = "pressure"
    BATTERY = "battery"
    THERMOSTAT = "thermostat"
    VALVE = "valve"
    LOCK = "lock"
    UNKNOWN = "unknown"


class IncidentType(str, Enum):
    """Types of incidents that can be auto-generated"""
    WATER_LEAK = "water_leak"
    HUMIDITY_ISSUE = "humidity_issue"
    HVAC_ISSUE = "hvac_issue"
    COMFORT_ISSUE = "comfort_issue"
    BATTERY_LOW = "battery_low"
    SECURITY_ALERT = "security_alert"
    AIR_QUALITY = "air_quality"
    BEHAVIORAL_ANOMALY = "behavioral_anomaly"
    SENSOR_ISSUE = "sensor_issue"
    MAINTENANCE = "maintenance"
    OTHER = "other"


# =============================================================================
# SENSOR FUSION TYPES
# =============================================================================

class SensorSignal(BaseModel):
    """Individual sensor signal with metadata"""
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    device_id: str
    sensor_id: str
    signal_type: SignalType
    value: Any
    unit: Optional[str] = None
    timestamp: datetime
    confidence: float = Field(default=1.0, ge=0, le=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TemporalContext(BaseModel):
    """Time-based context for pattern recognition"""
    timestamp: datetime
    hour_of_day: int = Field(ge=0, le=23)
    day_of_week: int = Field(ge=0, le=6)
    is_weekend: bool = False
    is_daytime: bool = True
    sun_elevation: float = Field(default=0.5, ge=0, le=1)
    sunrise_offset_hours: float = 0.0
    sunset_offset_hours: float = 0.0
    season: Literal["spring", "summer", "fall", "winter"] = "summer"


class WeatherContext(BaseModel):
    """External weather conditions"""
    temperature: float
    feels_like: float
    humidity: int
    pressure: int = 1013
    wind_speed: float = 0.0
    description: str = "clear"
    is_stormy: bool = False
    is_hot: bool = False
    is_cold: bool = False
    is_humid: bool = False
    aqi: Optional[int] = None  # Air quality index (1-5)


class BehavioralContext(BaseModel):
    """Learned behavioral patterns"""
    typical_wake_time: Optional[str] = None
    typical_sleep_time: Optional[str] = None
    occupancy_probability: float = Field(default=0.5, ge=0, le=1)
    activity_level: Literal["asleep", "resting", "active", "away"] = "active"
    last_motion_minutes_ago: Optional[int] = None
    routine_deviation_score: float = Field(default=0.0, ge=0, le=1)


class FusedContext(BaseModel):
    """Complete fused context from all signals"""
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    # Primary event that triggered reasoning
    trigger_signal: Optional[SensorSignal] = None

    # Temporal context
    temporal: TemporalContext

    # External context
    weather: Optional[WeatherContext] = None

    # Indoor conditions (fused from multiple sensors)
    indoor_temp: Optional[float] = None
    indoor_humidity: Optional[float] = None
    indoor_co2: Optional[float] = None
    indoor_aqi: Optional[int] = None

    # Room-specific conditions
    room_conditions: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    # Behavioral context
    behavioral: Optional[BehavioralContext] = None

    # Active alarms/incidents
    active_leaks: List[str] = Field(default_factory=list)
    active_smoke: List[str] = Field(default_factory=list)
    active_co: List[str] = Field(default_factory=list)

    # Anomaly signals
    anomalies: List[Dict[str, Any]] = Field(default_factory=list)

    # Historical context
    baseline_deviations: Dict[str, float] = Field(default_factory=dict)
    trend_1h: Dict[str, float] = Field(default_factory=dict)
    trend_24h: Dict[str, float] = Field(default_factory=dict)
    week_over_week_delta: Dict[str, float] = Field(default_factory=dict)

    # Fusion metadata
    signal_count: int = 0
    fusion_confidence: float = Field(default=1.0, ge=0, le=1)
    fusion_timestamp: datetime = Field(default_factory=datetime.now)


# =============================================================================
# REASONING TYPES
# =============================================================================

class ReasoningStep(BaseModel):
    """Single step in chain-of-thought reasoning"""
    step_number: int
    description: str
    observation: Optional[str] = None
    inference: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0, le=1)


class ReasoningChain(BaseModel):
    """Complete chain-of-thought reasoning"""
    scenario: ScenarioCategory
    trigger: str
    steps: List[ReasoningStep]
    conclusion: str
    confidence: float = Field(ge=0, le=1)
    reasoning_time_ms: int = 0


class Insight(BaseModel):
    """Individual insight from reasoning"""
    category: ScenarioCategory
    severity: Severity
    title: str
    description: str
    evidence: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    actionable: bool = True


class ReasoningResult(BaseModel):
    """Complete result from reasoning pipeline"""
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    # What triggered reasoning
    trigger_type: str
    trigger_device_id: Optional[str] = None

    # Chain of thought
    reasoning_chain: Optional[ReasoningChain] = None

    # Extracted insights
    insights: List[Insight] = Field(default_factory=list)

    # Primary conclusion
    primary_conclusion: str = ""
    primary_confidence: float = 0.0

    # Recommended actions
    recommended_actions: List[Dict[str, Any]] = Field(default_factory=list)

    # Metadata
    timestamp: datetime = Field(default_factory=datetime.now)
    processing_time_ms: int = 0


# =============================================================================
# SAFETY TYPES
# =============================================================================

class SafetyRule(BaseModel):
    """Safety rule definition"""
    rule_id: str
    name: str
    description: str
    category: ScenarioCategory
    severity: Severity
    conditions: Dict[str, Any]  # Conditions that trigger the rule
    action_mode: ActionMode
    max_auto_actions: int = 1  # Max autonomous actions per hour
    cooldown_minutes: int = 5  # Minimum time between actions
    requires_confirmation: bool = False
    fallback_action: Optional[str] = None


class SafetyDecision(BaseModel):
    """Safety guardian decision"""
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    # Decision
    allowed: bool
    action_mode: ActionMode
    requires_confirmation: bool = False

    # Reasoning
    triggered_rules: List[str] = Field(default_factory=list)
    reasoning: str = ""
    risk_score: float = Field(default=0.0, ge=0, le=1)

    # If blocked, why
    block_reason: Optional[str] = None

    # Modifications to proposed action
    modified_action: Optional[Dict[str, Any]] = None

    # Audit
    timestamp: datetime = Field(default_factory=datetime.now)
    context_snapshot: Dict[str, Any] = Field(default_factory=dict)


class ActionProposal(BaseModel):
    """Proposed action to be validated by safety guardian"""
    action_type: str
    target_device_id: str
    command: str
    value: Any
    source: Literal["ml", "llm", "rule", "user"] = "rule"
    confidence: float = Field(ge=0, le=1)
    urgency: Severity = Severity.MEDIUM
    reasoning: str = ""
    fallback_action: Optional[str] = None


class ActionResult(BaseModel):
    """Result of action execution"""
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    action_id: str
    success: bool
    executed_at: datetime
    device_id: str
    command: str
    value: Any

    # Safety decision
    safety_decision: SafetyDecision

    # Result
    error_message: Optional[str] = None
    response: Optional[Dict[str, Any]] = None

    # Learning
    outcome_score: Optional[float] = None  # Set later based on feedback
    user_feedback: Optional[str] = None


# =============================================================================
# SCENARIO TEMPLATES
# =============================================================================

class ScenarioSignature(BaseModel):
    """Signature to detect a specific scenario"""
    scenario_id: str
    category: ScenarioCategory
    name: str
    description: str

    # Detection conditions
    required_signals: List[str]  # e.g., ["humidity", "temperature"]
    threshold_conditions: Dict[str, Any]  # e.g., {"humidity": {"min": 70}}
    temporal_conditions: Optional[Dict[str, Any]] = None
    weather_conditions: Optional[Dict[str, Any]] = None

    # Severity and urgency
    base_severity: Severity = Severity.MEDIUM
    urgency_factors: List[str] = Field(default_factory=list)


class ScenarioMatch(BaseModel):
    """Result of scenario detection"""
    scenario_id: str
    scenario_name: str
    category: ScenarioCategory
    match_confidence: float = Field(ge=0, le=1)
    matched_conditions: List[str] = Field(default_factory=list)
    severity: Severity
    context_values: Dict[str, Any] = Field(default_factory=dict)


class ReasoningTemplate(BaseModel):
    """Template for scenario-specific reasoning"""
    scenario_id: str
    category: ScenarioCategory
    name: str

    # Chain of thought template
    reasoning_steps: List[str]

    # Action recommendations
    recommended_actions: List[Dict[str, Any]]

    # User-facing phrasing
    user_message_template: str
    detail_template: str

    # Safety
    safety_rules: List[str] = Field(default_factory=list)
    escalation_conditions: Dict[str, Any] = Field(default_factory=dict)

    # Confidence thresholds
    min_confidence_for_action: float = 0.7
    min_confidence_for_auto_action: float = 0.85


# =============================================================================
# PIPELINE TYPES
# =============================================================================

class PipelineStage(str, Enum):
    """Stages of the intelligence pipeline"""
    INGESTION = "ingestion"
    FUSION = "fusion"
    DETECTION = "detection"
    REASONING = "reasoning"
    SAFETY = "safety"
    ACTION = "action"
    LEARNING = "learning"


class PipelineResult(BaseModel):
    """Complete result from intelligence pipeline"""
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    # Input
    trigger_type: str
    trigger_data: Dict[str, Any]

    # Stages completed
    stages_completed: List[PipelineStage] = Field(default_factory=list)

    # Results
    fused_context: Optional[FusedContext] = None
    matched_scenarios: List[ScenarioMatch] = Field(default_factory=list)
    reasoning_result: Optional[ReasoningResult] = None
    safety_decisions: List[SafetyDecision] = Field(default_factory=list)
    actions_taken: List[ActionResult] = Field(default_factory=list)

    # Summary
    summary: str = ""
    insights_count: int = 0
    actions_count: int = 0

    # Performance
    total_processing_time_ms: int = 0
    stage_times: Dict[str, int] = Field(default_factory=dict)

    # Errors
    errors: List[str] = Field(default_factory=list)
