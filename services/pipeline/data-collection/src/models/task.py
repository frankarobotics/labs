"""Pydantic models for task endpoints."""

from uuid import UUID

from pydantic import BaseModel, Field


class TaskResponse(BaseModel):
    """Response model for tasks."""

    task_id: UUID
    name: str
    description: str | None = None
    version: str | None = None
    language_instructions: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
