"""Resolve completed recordings without importing ROS-dependent services."""

from pathlib import Path
from uuid import UUID

from pipeline_episodes import (
    EPISODE_METADATA_FILE,
    PROCESSING_COMPLETE_MARKER,
    EpisodeMetadata,
    EpisodeStatus,
    episode_directory,
)

from annotations.config import AnnotationConfig


def recording_path(config: AnnotationConfig, episode_id: UUID) -> Path:
    """Require LABS' processing marker before reading its completed MCAP."""
    root = config.processed_episodes_path
    directory = episode_directory(root, episode_id)
    if not directory.resolve().is_relative_to(root.resolve()):
        raise ValueError("The episode directory must remain inside the configured data directory.")
    metadata_path = directory / EPISODE_METADATA_FILE
    if not metadata_path.exists() or not (directory / PROCESSING_COMPLETE_MARKER).is_file():
        raise FileNotFoundError("The recording is not ready. Wait for LABS to finish processing the saved episode.")
    if not metadata_path.resolve().is_relative_to(directory.resolve()):
        raise ValueError("Episode metadata must remain inside the episode directory.")
    metadata = EpisodeMetadata.model_validate_json(metadata_path.read_text())
    if metadata.episode_id != episode_id or metadata.status != EpisodeStatus.SAVED:
        raise ValueError("Only saved episodes can be annotated.")
    candidates = sorted(directory.rglob("*.mcap"))
    if not candidates:
        raise FileNotFoundError("The processed recording is missing. Check the LABS processor before annotating.")
    if len(candidates) != 1:
        raise ValueError("This episode contains multiple MCAP files; a single processed recording is required.")
    recording = candidates[0]
    if not recording.resolve().is_relative_to(directory.resolve()):
        raise ValueError("Recording must remain inside its episode directory.")
    if recording.stat().st_size == 0:
        raise ValueError("The processed recording is empty. Check the LABS processor before annotating.")
    if recording.stat().st_size > config.max_recording_bytes:
        raise ValueError("The recording exceeds this station's configured annotation size limit.")
    return recording
