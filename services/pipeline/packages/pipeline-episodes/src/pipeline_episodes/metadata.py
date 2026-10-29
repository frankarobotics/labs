"""Episode metadata as stored in episode_metadata.json."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from pipeline_episodes.devices import DeviceInfo


class EpisodeStatus(StrEnum):
    """Enum for episode status."""

    INIT = "INIT"
    RECORDING = "RECORDING"
    RECORDED = "RECORDED"
    SAVED = "SAVED"
    DISCARDED = "DISCARDED"
    ERROR = "ERROR"


class EpisodeLabel(StrEnum):
    """Enumeration of labels for an episode."""

    REVIEW_SUCCESS = "REVIEW_SUCCESS"
    REVIEW_FAILED = "REVIEW_FAILED"


class EpisodeProcessed(StrEnum):
    """Enumeration for episode processed status."""

    DEFAULT = "DEFAULT"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


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
