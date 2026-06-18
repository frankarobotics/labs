"""Episode service logic.

This module provides the business logic for episode operations.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from uuid import UUID

import uuid7  # type: ignore[import-untyped]
from loguru import logger

from configs.station import StationConfig
from configs.tasks import Task
from models.episode import (
    DeviceInfo,
    EpisodeDeleteResponse,
    EpisodeLabel,
    EpisodeMetadata,
    EpisodeProcessed,
    EpisodeResponse,
    EpisodeStatus,
)
from models.record import RecordResponse
from repos.data_recorder import DataRecorderRepo
from repos.devices import DeviceRecord, DeviceRepo
from repos.episodes import EpisodeListFilters, EpisodeRepo
from repos.tasks import TaskRepo


class EpisodeService:
    """Service for managing episodes."""

    def __init__(  # noqa: PLR0913
        self,
        data_recorder_repo: DataRecorderRepo,
        raw_episode_repo: EpisodeRepo,
        processed_episode_repo: EpisodeRepo,
        task_repo: TaskRepo,
        device_repo: DeviceRepo,
        station_config: StationConfig,
        processed_data_path: str = "/workspace/data/processed_episodes",
    ) -> None:
        """Initialize the episode service.

        Args:
            data_recorder_repo: Repository for communicating with the data recorder service.
            raw_episode_repo: Filesystem repository for raw episode metadata (written during recording).
            processed_episode_repo: Filesystem repository for processed episode metadata (read by the API).
            task_repo: Repository for task data access.
            device_repo: In-memory repository for device data access.
            station_config: Station configuration.
            processed_data_path: Base directory for processed episode data.
        """
        self.data_recorder_repo: DataRecorderRepo = data_recorder_repo
        self.raw_episode_repo: EpisodeRepo = raw_episode_repo
        self.processed_episode_repo: EpisodeRepo = processed_episode_repo
        self.task_repo: TaskRepo = task_repo
        self.device_repo: DeviceRepo = device_repo
        self.station_config: StationConfig = station_config
        self.processed_data_path: Path = Path(processed_data_path)

    def _resolve_metadata(self, md: EpisodeMetadata) -> EpisodeMetadata:
        """Return processed episode_metadata.json if available, otherwise the raw metadata."""
        try:
            processed_meta_path = self._get_processed_episode_path(md.episode_id) / "episode_metadata.json"
            if processed_meta_path.exists():
                return EpisodeMetadata(**json.loads(processed_meta_path.read_text()))
        except Exception as e:
            logger.warning(f"Failed to read processed metadata for {md.episode_id}, falling back to raw: {e}")
        return md

    def _to_response(self, md: EpisodeMetadata) -> EpisodeResponse:
        """Convert an EpisodeMetadata model to an EpisodeResponse."""
        created_at: datetime | None = datetime.fromisoformat(md.created_at) if md.created_at else None
        updated_at: datetime | None = datetime.fromisoformat(md.updated_at) if md.updated_at else None
        duration: float | None = (updated_at - created_at).total_seconds() if created_at and updated_at else None
        return EpisodeResponse(
            episode_id=md.episode_id,
            task_id=md.task_id,
            task_name=md.task_name,
            task_description=md.task_description,
            task_version=md.task_version,
            task_language_instructions=md.task_language_instructions,
            task_metadata=md.task_metadata,
            station_id=md.station_id,
            status=EpisodeStatus(md.status),
            message=md.message,
            label=EpisodeLabel(md.label) if md.label else None,
            processed=EpisodeProcessed(md.processed),
            tags=md.tags,
            created_at=created_at,
            updated_at=updated_at,
            duration_seconds=duration,
        )

    def get_episode_by_id(self, episode_id: UUID) -> EpisodeResponse | None:
        """Get a single episode by its ID."""
        md: EpisodeMetadata | None = self.raw_episode_repo.get_by_id(episode_id)
        if md is None:
            # Raw episode may have been deleted after processing (delete_raw_episode=true)
            md = self.processed_episode_repo.get_by_id(episode_id)
        if md is None:
            return None
        return self._to_response(self._resolve_metadata(md))

    def get_episodes(
        self,
        status: str | None = None,
        processed: str | None = None,
        task_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EpisodeResponse]:
        """Get episodes with optional filters."""
        filters = EpisodeListFilters(
            status=status,
            processed=processed,
            task_id=task_id if task_id else None,
            station_id=self.station_config.metadata.station_id,
            limit=limit,
            offset=offset,
        )
        # Scan raw episodes; also include processed-only episodes for the case
        # where delete_raw_episode=true removed the raw directory after conversion.
        scan_filters = EpisodeListFilters(
            status=filters.status,
            processed=filters.processed,
            task_id=filters.task_id,
            station_id=filters.station_id,
            limit=100_000,
            offset=0,
        )
        raw_episodes: list[EpisodeMetadata] = self.raw_episode_repo.get_all(scan_filters)
        raw_ids: set[UUID] = {e.episode_id for e in raw_episodes}
        processed_only: list[EpisodeMetadata] = [
            e for e in self.processed_episode_repo.get_all(scan_filters) if e.episode_id not in raw_ids
        ]
        merged = raw_episodes + processed_only
        merged.sort(key=lambda e: e.created_at or "", reverse=True)
        paginated = merged[filters.offset : filters.offset + filters.limit]
        return [self._to_response(self._resolve_metadata(md)) for md in paginated]

    def create_episode(self, task_id: UUID, episode_id: UUID) -> None:
        """Create an episode metadata file when its recording is started."""
        task: Task | None = self.task_repo.get_by_id(task_id)
        devices_records: list[DeviceRecord] = self.device_repo.get_all()
        devices: list[DeviceInfo] = [
            DeviceInfo(
                device_id=d.id,
                device_type=d.type,
                device_status=d.status,
                device_config=d.config,
            )
            for d in devices_records
        ]
        metadata = EpisodeMetadata(
            episode_id=episode_id,
            status=EpisodeStatus.INIT,
            label=None,
            processed=EpisodeProcessed.DEFAULT,
            message="",
            tags=[],
            task_id=task_id,
            task_name=task.name if task else "",
            task_description=task.description if task and task.description else "",
            task_version=task.version if task else None,
            task_language_instructions=list(task.language_instructions) if task else [],
            task_metadata=dict(task.metadata) if task else {},
            station_id=self.station_config.metadata.station_id,
            devices=devices,
        )
        try:
            if not self.raw_episode_repo.create(metadata):
                raise ValueError(f"Episode {episode_id} already exists")
        except Exception as e:
            logger.error(f"Failed to create episode {episode_id}: {e}")
            raise

    def update_episode(  # noqa: PLR0913
        self,
        episode_id: UUID,
        *,
        status: EpisodeStatus | str | None = None,
        message: str | None = None,
        label: EpisodeLabel | str | None = None,
        tags: list[str] | None = None,
        processed: EpisodeProcessed | str | None = None,
    ) -> EpisodeMetadata:
        """Update episode fields in the metadata file. Only provided (non-None) fields are changed."""
        try:
            return self.raw_episode_repo.update(
                episode_id,
                status=status,
                message=message,
                label=label,
                tags=tags,
                processed=processed,
            )
        except Exception as e:
            logger.error(f"Failed to update episode {episode_id}: {e}")
            raise

    def _get_processed_episode_path(self, episode_id: UUID) -> Path:
        """Resolve the processed episode directory path from a UUIDv7-based episode_id."""
        dt: datetime = uuid7.time(episode_id)
        return self.processed_data_path / dt.strftime("%Y") / dt.strftime("%m") / dt.strftime("%d") / str(episode_id)

    def delete_episode(self, episode_id: UUID) -> EpisodeDeleteResponse:
        """Delete an episode by id.

        Checks for a processed episode first and deletes it if present.
        Then checks for the raw episode and deletes it if present.
        Returns 'not_found' only if neither exists.
        """
        try:
            deleted_any: bool = False

            # Delete processed episode directory if it exists
            processed_path: Path = self._get_processed_episode_path(episode_id)
            if processed_path.exists():
                shutil.rmtree(processed_path)
                logger.info(f"Deleted processed episode directory for {episode_id}")
                deleted_any = True

            # Delete raw episode if it exists (recorder also removes episode_metadata.json)
            if self.raw_episode_repo.delete(episode_id):
                recorder_response: RecordResponse = self.data_recorder_repo.delete_recording(episode_id)
                if recorder_response.status != "success":
                    raise Exception(f"DataRecorder failed to delete recording: {recorder_response.message}")
                logger.info(f"Deleted raw episode recording for {episode_id}")
                deleted_any = True

            if not deleted_any:
                return EpisodeDeleteResponse(status="not_found", message="Episode not found")

            logger.info(f"Successfully deleted episode {episode_id}")
            return EpisodeDeleteResponse(status="success", message="Deleted episode")

        except Exception as e:
            try:
                self.raw_episode_repo.update(episode_id, status=EpisodeStatus.ERROR, message=str(e))
            except Exception:
                logger.error(f"Failed to update episode status after delete error: {e}")
            logger.error(f"Failed to delete episode: {e}")
            return EpisodeDeleteResponse(status="error", message=f"Error deleting episode: {e}")

    def patch_episode(
        self,
        episode_id: UUID,
        processed: str | None = None,
        message: str | None = None,
    ) -> EpisodeResponse:
        """Patch certain mutable fields of an episode (processed, message).

        Returns the updated EpisodeResponse.
        """
        processed_val = EpisodeProcessed(processed) if processed is not None else None

        updated_raw: EpisodeMetadata | None = None
        updated_processed: EpisodeMetadata | None = None

        # Keep raw metadata in sync so filtering by `processed` works even when
        # raw episodes are retained (delete_raw_episode=false).
        try:
            updated_raw = self.raw_episode_repo.update(episode_id, processed=processed_val, message=message)
        except ValueError:
            logger.debug(f"Raw episode metadata not found for patch: {episode_id}")

        # Also update processed metadata if it exists.
        try:
            updated_processed = self.processed_episode_repo.update(episode_id, processed=processed_val, message=message)
        except ValueError:
            logger.debug(f"Processed episode metadata not found for patch: {episode_id}")

        updated: EpisodeMetadata | None = updated_processed or updated_raw
        if updated is None:
            raise ValueError(f"Episode not found: {episode_id}")

        return self._to_response(updated)
