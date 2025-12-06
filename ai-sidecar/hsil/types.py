"""
HSIL Type definitions
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class EventContext(BaseModel):
    """Normalized event with enriched context"""
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    device_id: str
    sensor_id: str
    event_type: str  # "temperature", "humidity", "leak", "motion", etc.
    event_value: Any
    location: str  # Zone name
    device_type: str  # "temp_sensor", "leak_sensor", etc.
    timestamp: datetime
    trend_1h: Optional[float] = None  # 1-hour trend (change rate)
    trend_24h: Optional[float] = None  # 24-hour trend
    anomaly_score: Optional[float] = None  # 0-1 probability of anomaly
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Feature(BaseModel):
    """Extracted high-level features"""
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    name: str
    value: Any
    timestamp: datetime
    device_id: str
    zone_id: Optional[str] = None


class MemoryType(str, Enum):
    """Types of memory entries"""
    PREFERENCE = "preference"
    BEHAVIOR = "behavior"
    BASELINE = "baseline"
    INCIDENT = "incident"
    ACTION = "action"


class MemoryEntry(BaseModel):
    """Stored preference or learned behavior"""
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    id: str
    type: MemoryType
    content: str
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class BehaviorPredictionType(str, Enum):
    """Types of behavior predictions"""
    COMFORT = "comfort"
    WATER_SAFETY = "water_safety"
    MAINTENANCE = "maintenance"
    OCCUPANCY = "occupancy"
    ENERGY = "energy"


class BehaviorPrediction(BaseModel):
    """Model prediction"""
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    type: BehaviorPredictionType
    prediction: Any
    confidence: float  # 0-1
    timestamp: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ActionCommand(BaseModel):
    """Command to be executed"""
    topic: str  # MQTT topic
    command: str
    value: Any


class PolicyDecision(BaseModel):
    """Policy engine decision"""
    intent: str  # User intent or trigger
    action: Optional[ActionCommand] = None
    reasoning: str
    confidence: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConversationRequest(BaseModel):
    """LLM conversation input"""
    message: str
    event_context: Optional[EventContext] = None
    home_state: Dict[str, Any] = Field(default_factory=dict)
    memory_results: List[MemoryEntry] = Field(default_factory=list)


class ConversationResponse(BaseModel):
    """LLM conversation output"""
    reply: str
    action: Optional[ActionCommand] = None
    clarification: Optional[Dict[str, Any]] = None  # For disambiguation requests


class DeviceStateEnum(str, Enum):
    """Device state for UI"""
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class DeviceState(BaseModel):
    """Device current state for dashboard"""
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    id: str
    type: str  # "temp", "humidity", "leak", "motion", etc.
    label: str  # "Kitchen Temperature"
    state: DeviceStateEnum
    value: Any  # Current reading
    active: bool = False  # Currently active/triggered
    location: str
    unit: Optional[str] = None
    last_updated: datetime
    trend: Optional[str] = None  # "up", "down", "stable"


class HomeState(BaseModel):
    """Current state of the home"""
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    devices: List[DeviceState]
    timestamp: datetime
    summary: Dict[str, Any] = Field(default_factory=dict)
