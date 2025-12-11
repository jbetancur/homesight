"""Device-related models"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class DeviceInfo(BaseModel):
    """Device information"""
    device_id: str
    name: Optional[str] = None  # Original device name from integration
    display_name: Optional[str] = None  # User-defined friendly name
    display_name: Optional[str] = None  # Computed: display_name if set, else name
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def get_display_name(self) -> str:
        """Returns display_name if set, otherwise name, otherwise device_id"""
        return self.display_name or self.name or self.device_id


class DeviceEvent(BaseModel):
    """Device lifecycle event"""
    type: str = Field(..., description="Event type (e.g., 'device.created')")
    data: DeviceInfo = Field(..., description="Device data")
