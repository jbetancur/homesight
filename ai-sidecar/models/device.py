"""Device-related models"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class DeviceInfo(BaseModel):
    """Device information"""
    device_id: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class DeviceEvent(BaseModel):
    """Device lifecycle event"""
    type: str = Field(..., description="Event type (e.g., 'device.created')")
    data: DeviceInfo = Field(..., description="Device data")
