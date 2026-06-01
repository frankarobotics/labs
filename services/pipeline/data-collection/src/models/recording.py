from uuid import UUID

from pydantic import BaseModel


class StartRecordingResponse(BaseModel):
    """Response model for starting a recording."""

    episode_id: UUID
    status: str
    message: str


class StopRecordingResponse(BaseModel):
    """Response model for stopping a recording."""

    status: str
    message: str


class SaveRecordingResponse(BaseModel):
    """Response model for saving a recording."""

    status: str
    message: str


class DiscardRecordingResponse(BaseModel):
    """Response model for discarding a recording."""

    status: str
    message: str
