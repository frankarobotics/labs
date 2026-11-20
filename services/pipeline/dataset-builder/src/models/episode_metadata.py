from typing import Any

from pydantic import BaseModel


class EpisodeMetadata(BaseModel):
    """Metadata for a single episode of collected data.

    Attributes:
        episode_index: Index of the episode in the dataset.
        frame_count: Total number of frames in the episode.
        duration_seconds: Duration of the episode in seconds.
        start_timestamp_ns: Timestamp of the first frame in nanoseconds, relative to the episode start.
        end_timestamp_ns: Timestamp of the last frame in nanoseconds, relative to the episode start.
        tasks: List of task names associated with the episode.
        mcap_file: Path to the associated MCAP file, if available.
        sync_stats: Synchronization statistics and metadata.
    """

    episode_index: int
    frame_count: int
    duration_seconds: float
    start_timestamp_ns: int
    end_timestamp_ns: int
    tasks: list[str] | None = None
    mcap_file: str | None = None
    sync_stats: dict[str, Any] | None = None
