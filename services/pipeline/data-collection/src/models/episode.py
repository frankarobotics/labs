"""Models for episodes."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pipeline_episodes import EpisodeLabel, EpisodeProcessed, EpisodeStatus
from pydantic import BaseModel


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
