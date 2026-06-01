"""CRUD operations for EpisodeDB."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from models.db import EpisodeDB, EpisodeLabelDB, EpisodeProcessedDB, EpisodeShippedDB, EpisodeStatusDB


@dataclass
class EpisodeListFilters:
    """Filters for listing episodes."""

    status: EpisodeStatusDB | str | None = None
    processed: EpisodeProcessedDB | str | None = None
    shipped: EpisodeShippedDB | str | None = None
    task_id: UUID | None = None
    station_id: str | None = None
    limit: int = 100
    offset: int = 0


class EpisodeRepo:
    """Repository for managing episodes."""

    def __init__(self, db: Session) -> None:
        """Initialize the episode repository."""
        self.db: Session = db

    def create(  # noqa: PLR0913
        self,
        id: UUID,  # noqa: A002
        task_id: UUID,
        station_id: str,
        status: EpisodeStatusDB | str,
        message: str = "",
        label: EpisodeLabelDB | str | None = None,
        object_url: str | None = None,
        tags: list[str] | None = None,
        processed: EpisodeProcessedDB | str = EpisodeProcessedDB.DEFAULT,
        shipped: EpisodeShippedDB | str = EpisodeShippedDB.DEFAULT,
    ) -> EpisodeDB:
        """Create a new episode."""
        episode = EpisodeDB(
            id=id,
            task_id=task_id,
            station_id=station_id,
            status=EpisodeStatusDB(status),
            message=message,
            label=EpisodeLabelDB(label) if label else None,
            object_url=object_url,
            tags=tags if tags is not None else [],
            processed=EpisodeProcessedDB(processed) if isinstance(processed, str) else processed,
            shipped=EpisodeShippedDB(shipped) if isinstance(shipped, str) else shipped,
        )
        self.db.add(episode)
        self.db.commit()
        self.db.refresh(episode)
        return episode

    def get_by_id(self, episode_id: UUID) -> EpisodeDB | None:
        """Get an episode by its ID."""
        stmt: Select[tuple[EpisodeDB]] = select(EpisodeDB).where(EpisodeDB.id == episode_id)
        return self.db.scalar(stmt)

    def get_all(self, filters: EpisodeListFilters | None = None) -> Sequence[EpisodeDB]:
        """Get all episodes with optional filters provided via EpisodeListFilters."""
        if filters is None:
            filters = EpisodeListFilters()

        stmt: Select[tuple[EpisodeDB]] = select(EpisodeDB)
        if filters.status:
            stmt = stmt.where(EpisodeDB.status == EpisodeStatusDB(filters.status))
        if filters.processed:
            stmt = stmt.where(EpisodeDB.processed == EpisodeProcessedDB(filters.processed))
        if filters.shipped:
            stmt = stmt.where(EpisodeDB.shipped == EpisodeShippedDB(filters.shipped))
        if filters.task_id:
            stmt = stmt.where(EpisodeDB.task_id == filters.task_id)
        if filters.station_id:
            stmt = stmt.where(EpisodeDB.station_id == filters.station_id)
        # Ensure deterministic ordering (newest first for episodes)
        stmt = stmt.order_by(EpisodeDB.created_at.desc()).offset(filters.offset).limit(filters.limit)
        return self.db.scalars(stmt).all()

    def update(  # noqa: PLR0913, C901
        self,
        episode_id: UUID,
        task_id: UUID | None = None,
        station_id: str | None = None,
        status: EpisodeStatusDB | None = None,
        message: str | None = None,
        label: EpisodeLabelDB | None = None,
        object_url: str | None = None,
        tags: list[str] | None = None,
        processed: EpisodeProcessedDB | None = None,
        shipped: EpisodeShippedDB | None = None,
    ) -> EpisodeDB:
        """Update an episode's status, message, label, and/or tags."""
        stmt: Select[tuple[EpisodeDB]] = select(EpisodeDB).where(EpisodeDB.id == episode_id)
        episode: EpisodeDB | None = self.db.scalar(stmt)
        if not episode:
            raise ValueError(f"Episode not found in the database. {episode_id=}")
        if task_id is not None:
            episode.task_id = task_id
        if station_id is not None:
            episode.station_id = station_id
        if status is not None:
            episode.status = EpisodeStatusDB(status)
        if message is not None:
            episode.message = message
        if label is not None:
            episode.label = EpisodeLabelDB(label)
        if object_url is not None:
            episode.object_url = object_url
        if tags is not None:
            episode.tags = tags
        if processed is not None:
            episode.processed = EpisodeProcessedDB(processed) if isinstance(processed, str) else processed
        if shipped is not None:
            episode.shipped = EpisodeShippedDB(shipped) if isinstance(shipped, str) else shipped
        episode.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(episode)
        return episode

    def delete(self, episode_id: UUID) -> bool:
        """Hard delete an episode row by id."""
        stmt: Select[tuple[EpisodeDB]] = select(EpisodeDB).where(EpisodeDB.id == episode_id)
        episode: EpisodeDB | None = self.db.scalar(stmt)
        if not episode:
            return False
        self.db.delete(episode)
        self.db.commit()
        return True
