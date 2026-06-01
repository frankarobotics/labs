import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import uuid7  # type: ignore[import-untyped]
from loguru import logger

from models.episode_metadata import EpisodeMetadata


class EpisodeMetadataRepo:
    """Thread-safe repository for CRUD operations on episode metadata JSON files."""

    def __init__(self, base_path: str) -> None:
        """Initialize the repository with the base path for metadata files.

        Args:
            base_path: Directory path where metadata files are stored
        """
        self.base_path = Path(base_path)
        self.lock = threading.Lock()
        os.makedirs(self.base_path, exist_ok=True)

    def _get_file_path(self, episode_id: UUID) -> Path:
        """Get the file path for a specific episode_id.

        Args:
            episode_id: The episode identifier

        Returns:
            Path to the metadata JSON file
        """
        dt: datetime = uuid7.time(episode_id)
        return Path(
            f"{self.base_path}/{dt.strftime('%Y')}/{dt.strftime('%m')}/{dt.strftime('%d')}/{episode_id}/episode_metadata.json"
        )

    def create(self, metadata: EpisodeMetadata) -> bool:
        """Create a new metadata file.

        Args:
            metadata: The metadata to save

        Returns:
            True if successful, False if the file already exists
        """
        file_path: Path = self._get_file_path(metadata.episode_id)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with self.lock:
            if file_path.exists():
                return False

            now: str = datetime.now(UTC).isoformat()
            metadata.created_at = now
            metadata.updated_at = now

            # Use Pydantic's JSON dumper which respects configured json_encoders
            with open(file_path, "w") as f:
                f.write(metadata.model_dump_json(indent=2))

            logger.info(f"Created {metadata=}")
            return True

    def read(self, episode_id: UUID) -> EpisodeMetadata | None:
        """Read metadata for a specific episode.

        Args:
            episode_id: The episode identifier

        Returns:
            EpisodeMetadata if found, None otherwise
        """
        file_path: Path = self._get_file_path(episode_id)

        with self.lock:
            if not file_path.exists():
                return None

            try:
                with open(file_path) as f:
                    data: dict[str, Any] = json.load(f)
                return EpisodeMetadata(**data)
            except json.JSONDecodeError:
                return None

    def update(self, metadata: EpisodeMetadata) -> bool:
        """Update an existing metadata file.

        Args:
            metadata: The updated metadata

        Returns:
            True if successful, False if the file doesn't exist
        """
        file_path: Path = self._get_file_path(metadata.episode_id)

        with self.lock:
            if not file_path.exists():
                return False

            metadata.updated_at = datetime.now(UTC).isoformat()

            # Use Pydantic's JSON dumper which respects configured json_encoders
            with open(file_path, "w") as f:
                f.write(metadata.model_dump_json(indent=2))

            logger.info(f"Updated {metadata=}")

            return True

    def delete(self, episode_id: UUID) -> bool:
        """Delete metadata for a specific episode.

        Args:
            episode_id: The episode identifier

        Returns:
            True if successful, False if the file doesn't exist
        """
        file_path: Path = self._get_file_path(episode_id)

        with self.lock:
            if not file_path.exists():
                return False

            os.remove(file_path)

            logger.info(f"Deleted metadata for {episode_id=}, {file_path=}")
            return True
