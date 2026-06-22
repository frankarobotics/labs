"""Models for recording metadata."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RecordMetadata(BaseModel):
    """Pydantic model for recording metadata."""

    # Episode
    episode_id: UUID
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    # Recording
    topics: list[str]
    format: str
    serialization_format: str
    recording_software: str

    # Time
    start_timestamp_iso: str
    end_timestamp_iso: str | None = None
    duration_seconds: float | None = None

    # File
    file_size_bytes: int | None = None

    # Status
    status: str | None = None
    error_message: str | None = None
