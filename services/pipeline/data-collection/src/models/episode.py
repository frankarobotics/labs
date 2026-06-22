"""Models for episodes."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from models.device import DeviceStatus, DeviceType


class EpisodeStatus(str, Enum):
    """Enum for episode status."""

    INIT = "INIT"
    RECORDING = "RECORDING"
    RECORDED = "RECORDED"
    SAVED = "SAVED"
    DISCARDED = "DISCARDED"
    ERROR = "ERROR"


class EpisodeLabel(str, Enum):
    """Enumeration of labels for an episode."""

    REVIEW_SUCCESS = "REVIEW_SUCCESS"
    REVIEW_FAILED = "REVIEW_FAILED"


class EpisodeProcessed(str, Enum):
    """Enumeration for episode processed status."""

    DEFAULT = "DEFAULT"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class EpisodeResponse(BaseModel):
    """Response model for episode endpoints."""

    episode_id: UUID
    task_id: UUID
    task_name: str = ""
    task_description: str = ""
    task_version: str | None = None
    task_language_instructions: list[str] = []
    task_metadata: dict[str, Any] = {}
    station_id: str
    status: EpisodeStatus
    message: str = ""
    tags: list[str] = []
    label: EpisodeLabel | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    duration_seconds: float | None = None
    processed: EpisodeProcessed = EpisodeProcessed.DEFAULT


class EpisodeDeleteResponse(BaseModel):
    """Response model for deleting episode."""

    status: str
    message: str = ""


class EpisodePatchRequest(BaseModel):
    """Request model used to patch episode fields (processed and message)."""

    processed: EpisodeProcessed | None = None
    message: str | None = None


class DeviceInfo(BaseModel):
    """Pydantic model for device information."""

    device_id: str
    device_type: DeviceType
    device_status: DeviceStatus
    device_config: dict[str, Any] = {}


class EpisodeMetadata(BaseModel):
    """Pydantic model for episode metadata stored on disk."""

    # Episode
    episode_id: UUID
    status: EpisodeStatus
    label: EpisodeLabel | None
    processed: EpisodeProcessed
    message: str = ""
    tags: list[str] = []
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    # Task
    task_id: UUID
    task_name: str
    task_description: str
    task_version: str | None = None
    task_language_instructions: list[str] = []
    task_metadata: dict[str, Any] = {}

    # Station
    station_id: str

    # Devices
    devices: list[DeviceInfo] = []
