"""Episode service logic.

This module provides the business logic for episode operations.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from loguru import logger

from configs.station import StationConfig
from configs.tasks import Task
from models.db import (
    DeviceDB,
    EpisodeDB,
    EpisodeLabelDB,
    EpisodeProcessedDB,
    EpisodeShippedDB,
    EpisodeStatusDB,
)
from models.episode import (
    EpisodeDeleteResponse,
    EpisodeLabel,
    EpisodeProcessed,
    EpisodeResponse,
    EpisodeShipped,
    EpisodeStatus,
)
from models.episode_metadata import DeviceInfo, EpisodeMetadata
from models.record import RecordResponse
from repos.data_recorder import DataRecorderRepo
from repos.devices import DeviceRepo
from repos.episode_metadata import EpisodeMetadataRepo
from repos.episodes import EpisodeListFilters, EpisodeRepo
from repos.tasks import TaskRepo


class EpisodeService:
    """Service for managing episodes."""

    def __init__(  # noqa: PLR0913
        self,
        data_recorder_repo: DataRecorderRepo,
        episode_repo: EpisodeRepo,
        episode_metadata_repo: EpisodeMetadataRepo,
        task_repo: TaskRepo,
        device_repo: DeviceRepo,
        station_config: StationConfig,
    ) -> None:
        """Initialize the episode service.

        Args:
            data_recorder_repo: Repository for communicating with the data recorder service.
            episode_repo: Repository for managing episode database operations.
            episode_metadata_repo: EpisodeMetadataRepo for writing per-episode metadata files.
            task_repo: Repository for task data access.
            device_repo: Repository for device data access.
            station_config: Station configuration.
        """
        self.data_recorder_repo: DataRecorderRepo = data_recorder_repo
        self.episode_repo: EpisodeRepo = episode_repo
        self.episode_metadata_repo: EpisodeMetadataRepo = episode_metadata_repo
        self.task_repo: TaskRepo = task_repo
        self.device_repo: DeviceRepo = device_repo
        self.station_config: StationConfig = station_config

    def get_episode_by_id(self, episode_id: UUID) -> EpisodeResponse | None:
        """Get a single episode by its ID."""
        episode: EpisodeDB | None = self.episode_repo.get_by_id(episode_id)
        if episode is None:
            return None
        duration: float | None = None
        if episode.created_at is not None and episode.updated_at is not None:
            duration = (episode.updated_at - episode.created_at).total_seconds()

        return EpisodeResponse(
            episode_id=episode.id,
            task_id=episode.task_id,
            station_id=self.station_config.metadata.station_id,
            status=EpisodeStatus(episode.status),
            message=episode.message,
            label=EpisodeLabel(episode.label) if episode.label else None,
            object_url=episode.object_url,
            processed=EpisodeProcessed(episode.processed) if episode.processed else EpisodeProcessed.DEFAULT,
            shipped=EpisodeShipped(episode.shipped) if episode.shipped else EpisodeShipped.DEFAULT,
            tags=episode.tags,
            created_at=episode.created_at,
            updated_at=episode.updated_at,
            duration_seconds=duration,
        )

    def get_episodes(  # noqa: PLR0913
        self,
        status: str | None = None,
        processed: str | None = None,
        shipped: str | None = None,
        task_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EpisodeResponse]:
        """Get episodes with optional filters."""
        status_enum = None
        if status:
            try:
                status_enum = EpisodeStatusDB(status)
            except Exception:
                status_enum = None
        filters = EpisodeListFilters(
            status=status_enum,
            processed=processed,
            shipped=shipped,
            task_id=task_id if task_id else None,
            station_id=self.station_config.metadata.station_id,
            limit=limit,
            offset=offset,
        )

        episodes: Sequence[EpisodeDB] = self.episode_repo.get_all(filters)
        return [
            EpisodeResponse(
                episode_id=ep.id,
                task_id=ep.task_id,
                task_name=task.name if task else "",
                task_description=task.description if task and task.description else "",
                task_version=task.version if task else None,
                task_language_instructions=task.language_instructions if task else [],
                task_metadata=task.metadata if task else {},
                station_id=self.station_config.metadata.station_id,
                status=EpisodeStatus(ep.status),
                label=EpisodeLabel(ep.label) if ep.label else None,
                object_url=ep.object_url,
                processed=EpisodeProcessed(ep.processed) if ep.processed else EpisodeProcessed.DEFAULT,
                shipped=EpisodeShipped(ep.shipped) if ep.shipped else EpisodeShipped.DEFAULT,
                message=ep.message,
                tags=ep.tags,
                created_at=ep.created_at,
                updated_at=ep.updated_at,
                duration_seconds=(
                    (ep.updated_at - ep.created_at).total_seconds()
                    if ep.created_at is not None and ep.updated_at is not None
                    else None
                ),
            )
            for ep in episodes
            for task in [self.task_repo.get_by_id(ep.task_id)]
        ]

    def create_episode(self, task_id: UUID, episode_id: UUID) -> None:
        """Create an episode when its recording is started."""
        try:
            # Add entry in the database
            self.episode_repo.create(
                id=episode_id,
                task_id=task_id,
                station_id=self.station_config.metadata.station_id,
                status=EpisodeStatusDB.INIT,
            )

            # Create episode metadata file.
            try:
                task: Task | None = self.task_repo.get_by_id(task_id)

                task_name: str = task.name if task else ""
                task_description: str = task.description if task and task.description else ""
                task_version: str | None = task.version if task else None
                task_language_instructions: list[str] = list(task.language_instructions) if task else []
                task_metadata: dict[str, object] = dict(task.metadata) if task else {}

                # Fetch all devices
                devices_db: Sequence[DeviceDB] = self.device_repo.get_all()
                devices: list[DeviceInfo] = [
                    DeviceInfo(
                        device_id=device.id,
                        device_type=device.type,
                        device_status=device.status,
                        device_config=device.config,
                    )
                    for device in devices_db
                ]

                metadata = EpisodeMetadata(
                    episode_id=episode_id,
                    status=EpisodeStatusDB.INIT,
                    label=None,
                    processed=EpisodeProcessedDB.DEFAULT,
                    shipped=EpisodeShippedDB.DEFAULT,
                    message="",
                    tags=[],
                    task_id=task_id,
                    task_name=task_name,
                    task_description=task_description,
                    task_version=task_version,
                    task_language_instructions=task_language_instructions,
                    task_metadata=task_metadata,
                    station_id=self.station_config.metadata.station_id,
                    devices=devices,
                )
                self.create_episode_metadata(metadata)

            except Exception as e:
                logger.warning(f"Failed to create episode metadata for {episode_id}: {e}")

        except Exception as e:
            # Update entry in the database
            try:
                self.update_episode(
                    episode_id,
                    task_id=task_id,
                    station_id=self.station_config.metadata.station_id,
                    status=EpisodeStatusDB.ERROR,
                    message=str(e),
                )
            except Exception:
                logger.error(f"Failed to update episode status: {e}")
            logger.error(f"Failed to start recording: {e}")
            raise e

    def update_episode(  # noqa: PLR0913
        self,
        episode_id: UUID,
        *,
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
        """Update episode fields in the database. Only provided (non-None) fields are changed."""
        try:
            return self.episode_repo.update(
                episode_id,
                task_id=task_id,
                station_id=station_id,
                status=status,
                message=message,
                label=label,
                object_url=object_url,
                tags=tags,
                processed=processed,
                shipped=shipped,
            )
        except Exception as e:
            logger.error(f"Failed to update episode {episode_id}: {e}")
            raise

    def create_episode_metadata(self, metadata: EpisodeMetadata) -> None:
        """Create the episode metadata file for the given episode."""
        try:
            self.episode_metadata_repo.create(metadata)
            logger.info(f"Episode metadata created successfully for episode {metadata.episode_id}")
        except Exception as e:
            logger.warning(f"Failed to create episode metadata for episode {metadata.episode_id}: {e}")

    def update_episode_metadata(  # noqa: PLR0913
        self,
        episode_id: UUID,
        *,
        status: EpisodeStatusDB | None = None,
        message: str | None = None,
        label: EpisodeLabelDB | None = None,
        tags: list[str] | None = None,
        processed: EpisodeProcessedDB | None = None,
        shipped: EpisodeShippedDB | None = None,
        object_url: str | None = None,
    ) -> None:
        """Update the episode metadata file for the given episode. Only provided (non-None) fields are changed."""
        try:
            md: EpisodeMetadata | None = self.episode_metadata_repo.read(episode_id)
            if md is not None:
                if status is not None:
                    md.status = status
                if message is not None:
                    md.message = message
                if label is not None:
                    md.label = label
                if tags is not None:
                    md.tags = tags
                if processed is not None:
                    md.processed = processed
                if shipped is not None:
                    md.shipped = shipped
                if object_url is not None:
                    md.object_url = object_url
                self.episode_metadata_repo.update(md)
                logger.info(f"Episode metadata updated successfully for episode {episode_id}")
            else:
                logger.warning(f"Episode metadata not found for episode {episode_id} when trying to update")
        except Exception as e:
            logger.warning(f"Failed to update episode metadata for episode {episode_id}: {e}")

    def delete_episode(self, episode_id: UUID) -> EpisodeDeleteResponse:
        """Delete an episode and its recording by id."""
        try:
            # Delete recording (episode) generated by recorder
            recorder_response: RecordResponse = self.data_recorder_repo.delete_recording(episode_id)
            if recorder_response.status != "success":
                raise Exception(f"DataRecorder failed to delete recording: {recorder_response.message}")

            # Remove episode row from DB
            deleted: bool = self.episode_repo.delete(episode_id)
            if not deleted:
                logger.warning(f"Episode not found when attempting delete: {episode_id}")
                return EpisodeDeleteResponse(status="not_found", message="Episode not found")

            logger.info(f"Successfully deleted episode and recording for {episode_id}")
            return EpisodeDeleteResponse(status="success", message="Deleted recording and episode")

        except Exception as e:
            # Attempt to mark episode as error in DB
            try:
                self.update_episode(episode_id, status=EpisodeStatusDB.ERROR, message=str(e))
            except Exception:
                logger.error(f"Failed to update episode status after delete error: {e}")

            logger.error(f"Failed to delete episode: {e}")
            return EpisodeDeleteResponse(status="error", message=f"Error deleting episode: {e}")

    def patch_episode(
        self,
        episode_id: UUID,
        processed: str | None = None,
        shipped: str | None = None,
        message: str | None = None,
        object_url: str | None = None,
    ) -> EpisodeResponse:
        """Patch certain mutable fields of an episode (shipped, message).

        Returns the updated EpisodeResponse.
        """
        # Convert processed and shipped to DB enum if provided
        processed_val = None
        shipped_val = None
        if processed is not None:
            processed_val = EpisodeProcessedDB(processed)
        if shipped is not None:
            shipped_val = EpisodeShippedDB(shipped)

        updated: EpisodeDB = self.update_episode(
            episode_id, processed=processed_val, shipped=shipped_val, message=message, object_url=object_url
        )

        duration: float | None = None
        if updated.created_at is not None and updated.updated_at is not None:
            duration = (updated.updated_at - updated.created_at).total_seconds()

        # Update episode metadata file
        self.update_episode_metadata(
            episode_id,
            processed=processed_val,
            shipped=shipped_val,
            message=message,
            object_url=object_url,
        )

        return EpisodeResponse(
            episode_id=updated.id,
            task_id=updated.task_id,
            station_id=updated.station_id,
            status=EpisodeStatus(updated.status),
            message=updated.message,
            label=EpisodeLabel(updated.label) if updated.label else None,
            object_url=updated.object_url,
            processed=EpisodeProcessed(updated.processed),
            shipped=EpisodeShipped(updated.shipped),
            tags=updated.tags,
            created_at=updated.created_at,
            updated_at=updated.updated_at,
            duration_seconds=duration,
        )
