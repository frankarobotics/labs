from __future__ import annotations

from pydantic import BaseModel


class ActiveEpisode(BaseModel):
    """Represents an active episode summary."""

    id: str
    status: str
    started_on: str | None = None
    task_id: str | None = None


class SystemGetResponse(BaseModel):
    """Detailed system information model."""

    workflow_state: str
    recording_state: str
    system_status: str
    station_id: str
    active_episode: ActiveEpisode | None = None
