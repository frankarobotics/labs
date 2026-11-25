from typing import Any

from pipeline_episodes import DeviceStatus, DeviceType
from pydantic import BaseModel


class DeviceResponse(BaseModel):
    """Response model for a device."""

    id: str
    type: DeviceType
    status: DeviceStatus
    config: dict[str, Any]
