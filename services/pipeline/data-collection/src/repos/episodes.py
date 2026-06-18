"""Filesystem-based repository for episodes.

Episodes are stored as episode_metadata.json files under:
  {base_path}/{YYYY}/{MM}/{DD}/{episode_id}/episode_metadata.json

The episode_metadata.json file is the single source of truth.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import uuid7  # type: ignore[import-untyped]
from loguru import logger

from models.episode import EpisodeLabel, EpisodeMetadata, EpisodeProcessed, EpisodeStatus


@dataclass
class EpisodeListFilters:
    """Filters for listing episodes."""

    status: EpisodeStatus | str | None = None
    processed: EpisodeProcessed | str | None = None
    task_id: UUID | None = None
    station_id: str | None = None
    limit: int = 100
    offset: int = 0


class EpisodeRepo:
    """Thread-safe filesystem repository for episodes."""

    def __init__(self, base_path: str) -> None:
        """Initialize the episode repository with the base data path."""
        self.base_path = Path(base_path)
        self._lock = threading.Lock()
        os.makedirs(self.base_path, exist_ok=True)

    def _get_file_path(self, episode_id: UUID) -> Path:
        """Resolve the metadata JSON path from an episode_id via its UUIDv7 timestamp."""
        dt: datetime = uuid7.time(episode_id)
        return (
            self.base_path
            / dt.strftime("%Y")
            / dt.strftime("%m")
            / dt.strftime("%d")
            / str(episode_id)
            / "episode_metadata.json"
        )

    def get_by_id(self, episode_id: UUID) -> EpisodeMetadata | None:
        """Read episode metadata by ID (O(1) path lookup via UUIDv7 timestamp)."""
        file_path = self._get_file_path(episode_id)
        with self._lock:
            if not file_path.exists():
                return None
            try:
                return EpisodeMetadata(**json.loads(file_path.read_text()))
            except Exception as e:
                logger.error(f"Failed to read episode metadata for {episode_id}: {e}")
                return None

    def get_all(self, filters: EpisodeListFilters | None = None) -> list[EpisodeMetadata]:
        """Return all episodes matching the given filters (filesystem scan, newest first)."""
        if filters is None:
            filters = EpisodeListFilters()

        episodes: list[EpisodeMetadata] = []
        with self._lock:
            for meta_file in sorted(self.base_path.rglob("episode_metadata.json"), reverse=True):
                try:
                    episodes.append(EpisodeMetadata(**json.loads(meta_file.read_text())))
                except Exception as e:
                    logger.warning(f"Skipping malformed metadata file {meta_file}: {e}")

        # Apply filters in-memory
        if filters.status:
            status_val = filters.status.value if isinstance(filters.status, EpisodeStatus) else str(filters.status)
            episodes = [e for e in episodes if e.status.value == status_val]
        if filters.processed:
            proc_val = (
                filters.processed.value if isinstance(filters.processed, EpisodeProcessed) else str(filters.processed)
            )
            episodes = [e for e in episodes if e.processed.value == proc_val]
        if filters.task_id:
            episodes = [e for e in episodes if e.task_id == filters.task_id]
        if filters.station_id:
            episodes = [e for e in episodes if e.station_id == filters.station_id]

        return episodes[filters.offset : filters.offset + filters.limit]

    def create(self, metadata: EpisodeMetadata) -> bool:
        """Write a new episode_metadata.json. Returns False if file already exists."""
        file_path = self._get_file_path(metadata.episode_id)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            if file_path.exists():
                return False
            now = datetime.now(UTC).isoformat()
            metadata.created_at = now
            metadata.updated_at = now
            file_path.write_text(metadata.model_dump_json(indent=2))
            logger.info(f"Created episode metadata for {metadata.episode_id}")
            return True

    def update(  # noqa: PLR0913
        self,
        episode_id: UUID,
        *,
        status: EpisodeStatus | str | None = None,
        message: str | None = None,
        label: EpisodeLabel | str | None = None,
        tags: list[str] | None = None,
        processed: EpisodeProcessed | str | None = None,
    ) -> EpisodeMetadata:
        """Patch specified fields of the episode metadata file. Returns the updated metadata."""
        file_path = self._get_file_path(episode_id)
        with self._lock:
            if not file_path.exists():
                raise ValueError(f"Episode not found: {episode_id}")
            md = EpisodeMetadata(**json.loads(file_path.read_text()))
            if status is not None:
                md.status = EpisodeStatus(status) if isinstance(status, str) else status
            if message is not None:
                md.message = message
            if label is not None:
                md.label = EpisodeLabel(label) if isinstance(label, str) else label
            if tags is not None:
                md.tags = tags
            if processed is not None:
                md.processed = EpisodeProcessed(processed) if isinstance(processed, str) else processed
            md.updated_at = datetime.now(UTC).isoformat()
            file_path.write_text(md.model_dump_json(indent=2))
            return md

    def delete(self, episode_id: UUID) -> bool:
        """Return True if the episode metadata file exists, False if not found.

        Note: Physical deletion of the episode directory is handled by the data-recorder service.
        """
        return self._get_file_path(episode_id).exists()
