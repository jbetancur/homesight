"""
HomeSight Intelligence Layer (HSIL)

This package provides the intelligence layer that sits above the HomeSight core,
offering:
- Event ingestion and context building
- Feature extraction (trends, patterns, context)
- Home memory graph (preferences, history)
- Behavior models (comfort, water, HVAC, solar)
- Policy engine (safety & comfort rules)
- Conversational agent integration

HIL Evolution (v2.0):
- Sensor fusion engine (multi-source data fusion)
- Safety guardian (safe autonomy framework)
- Reasoning templates (chain-of-thought reasoning)
- Intelligence pipeline (unified ML + LLM coordinator)
- Incident generator (auto-incident creation)
"""

__version__ = "2.0.0"

# Core types
from .types import (
    EventContext,
    DeviceState,
    HomeState,
    ConversationRequest,
    ConversationResponse,
    ActionCommand
)

# HIL Evolution types
from .hil_types import (
    SensorSignal,
    SignalType,
    SensorType,
    IncidentType,
    FusedContext,
    WeatherContext,
    BehavioralContext,
    TemporalContext,
    ReasoningResult,
    ReasoningChain,
    ReasoningStep,
    Insight,
    SafetyDecision,
    SafetyRule,
    ActionProposal,
    ActionResult,
    PipelineResult,
    PipelineStage,
    ScenarioMatch,
    ScenarioSignature,
    ScenarioCategory,
    ReasoningTemplate,
    Severity,
    ConfidenceLevel,
    ActionMode,
)

# HIL Evolution components
from .sensor_fusion import SensorFusionEngine
from .safety_guardian import SafetyGuardian
from .reasoning_templates import ScenarioDetector, ReasoningEngine
from .intelligence_pipeline import IntelligencePipeline
from .incident_generator import IncidentGenerator, IncidentCorrelator

# Main service
from .service import HSILService

__all__ = [
    # Version
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
    "ReasoningResult",
    "ReasoningChain",
    "ReasoningStep",
    "Insight",
    "SafetyDecision",
    "SafetyRule",
    "ActionProposal",
    "ActionResult",
    "PipelineResult",
    "PipelineStage",
    "ScenarioMatch",
    "ScenarioSignature",
    "ScenarioCategory",
    "ReasoningTemplate",
    "Severity",
    "ConfidenceLevel",
    "ActionMode",
    
    # HIL components
    "SensorFusionEngine",
    "SafetyGuardian",
    "ScenarioDetector",
    "ReasoningEngine",
    "IntelligencePipeline",
    "IncidentGenerator",
    "IncidentCorrelator",
    
    # Service
    "HSILService",
]
