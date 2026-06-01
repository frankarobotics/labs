"""Models for record endpoints."""

from uuid import UUID

from pydantic import BaseModel


class RecordResponse(BaseModel):
    """Response model for record endpoints."""

    status: str
    message: str


class RecordStatusResponse(BaseModel):
    """Response model for record status endpoint."""

    status: str
    is_recording: bool
    episode_id: UUID | None = None


class RecordStateResponse(BaseModel):
    """Response model for record state endpoint."""

    is_recording: bool
    status: str
    episode_id: UUID | None = None
