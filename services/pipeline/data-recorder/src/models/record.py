"""Models for record endpoints."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel


class StartRecordRequest(BaseModel):
    """Request model for starting recording."""

    episode_id: UUID


class StartRecordResponse(BaseModel):
    """Response model for starting recording."""

    status: str
    message: str


class StopRecordResponse(BaseModel):
    """Response model for stopping recording."""

    status: str
    message: str


class DeleteRecordRequest(BaseModel):
    """Request model for deleting recording."""

    episode_id: UUID


class DeleteRecordResponse(BaseModel):
    """Response model for deleting recording."""

    status: str
    message: str


class RecordStatusResponse(BaseModel):
    """Response model for recording status."""

    status: str
    is_recording: bool
    episode_id: UUID | None = None
    metadata: dict[str, Any] | None = None


class RecordStateResponse(BaseModel):
    """Response model for recording state."""

    status: str
    is_recording: bool
    episode_id: UUID | None = None
