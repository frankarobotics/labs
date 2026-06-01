"""Models for episode endpoints."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel


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


class EpisodeShipped(str, Enum):
    """Enumeration for episode shipped status."""

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
    shipped: EpisodeShipped = EpisodeShipped.DEFAULT
    object_url: str | None = None


class EpisodeDeleteResponse(BaseModel):
    """Response model for deleting episode."""

    status: str
    message: str = ""


class EpisodePatchRequest(BaseModel):
    """Request model used to patch episode fields (shipped and message)."""

    processed: EpisodeProcessed | None = None
    shipped: EpisodeShipped | None = None
    message: str | None = None
    object_url: str | None = None
