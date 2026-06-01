"""API models for the data-processor client to consume."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class EpisodeStatus(str, Enum):
    """Enum describing possible episode lifecycle states returned by the API."""

    INIT = "INIT"
    RECORDING = "RECORDING"
    RECORDED = "RECORDED"
    SAVED = "SAVED"
    DISCARDED = "DISCARDED"
    ERROR = "ERROR"


class EpisodeProcessed(str, Enum):
    """Enum for the processed state of an episode."""

    DEFAULT = "DEFAULT"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class EpisodeShipped(str, Enum):
    """Enum for the shipped state of an episode."""

    DEFAULT = "DEFAULT"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class EpisodeResponse(BaseModel):
    """Typed response model for episodes coming from the data-collection API."""

    episode_id: UUID
    task_id: UUID
    task_name: str = ""
    task_description: str = ""
    task_version: str | None = None
    task_language_instructions: list[str] = []
    task_metadata: dict[str, Any] = {}
    station_id: str = ""
    status: EpisodeStatus
    message: str = ""
    tags: list[str] = []
    label: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    duration_seconds: float | None = None
    shipped: EpisodeShipped | None = None


class EpisodePatchRequest(BaseModel):
    """Request model for patching episode data."""

    shipped: EpisodeShipped | None = None
    message: str | None = None


class HealthCheckResponse(BaseModel):
    """Response model for health check endpoints."""

    status: str
    timestamp: datetime | None = None
    details: dict[str, str] | None = None


class S3UploadResult(BaseModel):
    """Result of S3-compatible upload operation."""

    success: bool
    uploaded_files: list[str] = []
    failed_files: list[str] = []
    total_size_bytes: int = 0
    upload_duration_seconds: float = 0
    error_message: str | None = None


class FileChecksum(BaseModel):
    """File checksum information for integrity verification."""

    file_path: str
    size_bytes: int
    md5_hash: str
    sha256_hash: str | None = None


class ConversionMetadata(BaseModel):
    """Metadata about the MCAP conversion process."""

    input_file: str
    output_file: str
    camera_topics: list[str]
    av1_settings: dict[str, str | int]  # Contains preset, gop_size, pixel_format, threads
    conversion_start_time: datetime
    conversion_end_time: datetime
    conversion_duration_seconds: float
    original_size_bytes: int
    compressed_size_bytes: int
    compression_ratio: float
    frame_count: int
    codec_used: str = "libsvtav1"  # AV1 encoder used
    error_message: str | None = None
