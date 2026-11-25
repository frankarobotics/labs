"""Where an episode lives on disk: <root>/YYYY/MM/DD/<episode_id>/."""

from datetime import datetime
from pathlib import Path
from uuid import UUID

import uuid7  # type: ignore[import-untyped]

EPISODE_METADATA_FILE = "episode_metadata.json"
# written by data-processor once an episode's processed output is complete
PROCESSING_COMPLETE_MARKER = ".processing_complete"


def episode_directory(root: Path, episode_id: UUID) -> Path:
    """Return the episode's directory, dated by its UUIDv7 creation time in UTC.

    Raises:
        ValueError: If ``episode_id`` is not a UUIDv7.
    """
    created: datetime = uuid7.time(episode_id)
    return root / created.strftime("%Y/%m/%d") / str(episode_id)
