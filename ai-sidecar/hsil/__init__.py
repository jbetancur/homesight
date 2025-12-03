"""
HomeSight Intelligence Layer (HSIL) - Simplified

Architecture: ML data → LLM → response

Core components:
- Event ingestion
- ML learning (River)
- Device ontology
- Weather service
- Conversational agent (LLM reasons from data)
- Action dispatcher
"""

__version__ = "3.0.0-simplified"

# Core types
from .types import (
    EventContext,
    DeviceState,
    HomeState,
    ConversationRequest,
    ConversationResponse,
    ActionCommand
)

# HIL types (still useful for data structures)
from .hil_types import (
    SensorSignal,
    SignalType,
    SensorType,
    IncidentType,
    FusedContext,
    WeatherContext,
    BehavioralContext,
    TemporalContext,
    Severity,
    ConfidenceLevel,
)

# Core components
from .incident_generator import IncidentGenerator

# Main service
from .service import HSILService

__all__ = [
    "__version__",
    
    # Core types
    "EventContext",
    "DeviceState",
    "HomeState",
    "ConversationRequest",
    "ConversationResponse",
    "ActionCommand",
    
    # HIL types
    "SensorSignal",
    "SignalType",
    "SensorType",
    "IncidentType",
    "FusedContext",
    "WeatherContext",
    "BehavioralContext",
    "TemporalContext",
    "Severity",
    "ConfidenceLevel",
    
    # Components
    "IncidentGenerator",
    
    # Service
    "HSILService",
]
