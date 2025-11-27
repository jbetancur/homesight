"""Pydantic models for API requests and responses"""

from .chat import ChatRequest, ChatResponse, ChatSession
from .analyze import AnalyzeRequest, AnalyzeResponse
from .device import DeviceEvent, DeviceInfo  # Legacy - deprecated
from .device_profile import (
    DeviceProfile,
    DeviceType,
    PowerSource,
    Protocol,
    BatteryType,
    DeviceCapability,
    DocumentStatus
)

__all__ = [
    "ChatRequest",
    "ChatResponse",
    "ChatSession",
    "AnalyzeRequest",
    "AnalyzeResponse",
    "DeviceEvent",
    "DeviceInfo",  # Deprecated
    # New device ontology
    "DeviceProfile",
    "DeviceType",
    "PowerSource",
    "Protocol",
    "BatteryType",
    "DeviceCapability",
    "DocumentStatus",
]
