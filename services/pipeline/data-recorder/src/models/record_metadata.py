"""Models for recording metadata."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

RECORD_METADATA_VERSION = "0.1"


class RecordMetadata(BaseModel):
    """Pydantic model for recording metadata."""

    episode_id: UUID
    topics: list[str]
    output_path: str
    metadata_path: str
    recording_path: str
    format: str
    serialization_format: str
    recording_software: str
    record_metadata_version: str = RECORD_METADATA_VERSION

    # Time information
    start_timestamp_iso: str
    start_timestamp: float
    end_timestamp_iso: str | None = None
    end_timestamp: float | None = None
    duration_seconds: float | None = None

    # File information
    file_size_bytes: int | None = None
    file_size_human: str | None = None

    # Status information
    status: str | None = None
    error_message: str | None = None

    # Additional information
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    model_config = ConfigDict(json_encoders={datetime: lambda dt: dt.isoformat()})
