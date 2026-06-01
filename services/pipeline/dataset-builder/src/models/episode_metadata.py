from typing import Any

from pydantic import BaseModel


class EpisodeMetadata(BaseModel):
    """Metadata for a single episode of collected data.

    Attributes:
        episode_index: Index of the episode in the dataset.
        chunk_index: Index of the chunk within the episode.
        frame_count: Total number of frames in the episode.
        duration_seconds: Duration of the episode in seconds.
        start_timestamp_ns: Start timestamp of the episode in epoch nanoseconds.
        end_timestamp_ns: End timestamp of the episode in epoch nanoseconds.
        parquet_file: Path to the associated Parquet file.
        tasks: List of task names associated with the episode.
        synchronized_frames: Number of frames successfully synchronized.
        mcap_file: Path to the associated MCAP file, if available.
        sync_stats: Synchronization statistics and metadata.
    """

    episode_index: int
    chunk_index: int
    frame_count: int
    duration_seconds: float
    start_timestamp_ns: int
    end_timestamp_ns: int
    parquet_file: str
    tasks: list[str] | None = None
    synchronized_frames: int | None = None
    mcap_file: str | None = None
    sync_stats: dict[str, Any] | None = None
