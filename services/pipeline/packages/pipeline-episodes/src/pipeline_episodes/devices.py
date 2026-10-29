"""Device records stored in episode metadata."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class DeviceType(StrEnum):
    """Enum for device type."""

    TELEOP_ROBOT = "TELEOP_ROBOT"
    REALSENSE_CAMERA = "REALSENSE_CAMERA"
    ZED_CAMERA = "ZED_CAMERA"
    ROBOT_OBSERVER = "ROBOT_OBSERVER"


class DeviceStatus(StrEnum):
    """Device status enum."""

    UNKNOWN = "UNKNOWN"
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    ERROR = "ERROR"


class DeviceInfo(BaseModel):
    """Pydantic model for device information."""

    device_id: str
    device_type: DeviceType
    device_status: DeviceStatus
    device_config: dict[str, Any] = {}
