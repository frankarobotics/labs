"""Persistent jobs and the public annotation response contract."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, JsonValue

JobState = Literal[
    "queued", "preparing", "uploading", "ingesting", "indexing", "fetching", "completed", "failed", "interrupted"
]
ACTIVE_STATES = ("queued", "preparing", "uploading", "ingesting", "indexing", "fetching")


def now() -> datetime:
    """Return an explicit UTC timestamp for persisted records."""
    return datetime.now(UTC)


class AnnotationEvent(BaseModel):
    """One action window returned by Nomadic."""

    event_id: str
    start_seconds: float = Field(ge=0, allow_inf_nan=False)
    end_seconds: float = Field(gt=0, allow_inf_nan=False)
    description: str
    category: str | None = None
    acting_hand: Literal["left", "right", "both"] | None = None
    objects: list[str] = Field(default_factory=list)
    action_classes: list[str] = Field(default_factory=list)
    gripper_transitions: list[str] = Field(default_factory=list)
    object_interactions: list[str | dict[str, JsonValue]] = Field(default_factory=list)
    structured_output: dict[str, JsonValue] = Field(default_factory=dict)


class AnnotationJob(BaseModel):
    """Durable local state, including identifiers needed to inspect remote work."""

    job_id: UUID
    episode_id: UUID
    state: JobState = "queued"
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
    message: str = "Waiting to prepare recording."
    remote_started: bool = False
    ingest_id: str | None = None
    video_id: str | None = None
    batch_id: str | None = None
    index_run_id: str | None = None
    analysis_id: str | None = None
    source_sha256: str | None = None
    warnings: list[str] = Field(default_factory=list)
    events: list[AnnotationEvent] = Field(default_factory=list)
    viewer_url: str | None = None


class AnnotationStatus(BaseModel):
    """Status loaded by the episode UI without exposing configuration secrets."""

    enabled: bool
    can_submit: bool = False
    message: str
    job: AnnotationJob | None = None
