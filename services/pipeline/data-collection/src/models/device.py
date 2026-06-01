from enum import Enum
from typing import Any

from pydantic import BaseModel


class DeviceType(str, Enum):
    """Enum for device type."""

    TELEOP_ROBOT = "TELEOP_ROBOT"
    REALSENSE_CAMERA = "REALSENSE_CAMERA"
    ZED_CAMERA = "ZED_CAMERA"
    ROBOT_OBSERVER = "ROBOT_OBSERVER"


class DeviceStatus(str, Enum):
    """Device status enum."""

    UNKNOWN = "UNKNOWN"
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    ERROR = "ERROR"


class DeviceResponse(BaseModel):
    """Response model for a device."""

    id: str
    type: DeviceType
    status: DeviceStatus
    config: dict[str, Any]
