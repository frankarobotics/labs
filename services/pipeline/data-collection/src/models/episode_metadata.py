"""Models for episode metadata."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from models.db import (
    DeviceStatusDB,
    DeviceTypeDB,
    EpisodeLabelDB,
    EpisodeProcessedDB,
    EpisodeShippedDB,
    EpisodeStatusDB,
)

EPISODE_METADATA_VERSION = "0.1"


class DeviceInfo(BaseModel):
    """Pydantic model for device information."""

    device_id: str
    device_type: DeviceTypeDB
    device_status: DeviceStatusDB
    device_config: dict[str, Any] = {}


class EpisodeMetadata(BaseModel):
    """Pydantic model for episode metadata."""

    # Episode
    episode_id: UUID
    status: EpisodeStatusDB
    label: EpisodeLabelDB | None
    object_url: str | None = None
    processed: EpisodeProcessedDB
    shipped: EpisodeShippedDB
    message: str = ""
    tags: list[str] = []

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

    episode_metadata_version: str = EPISODE_METADATA_VERSION

    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    model_config = ConfigDict(json_encoders={datetime: lambda dt: dt.isoformat()})
