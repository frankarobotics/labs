"""Parquet Writer for LeRobot dataset format."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from lerobot_conversion.lerobot_utils import get_observation_state_feature_name
from lerobot_conversion.topic_manifest import DatasetTopicManifest
from models.episode_metadata import EpisodeMetadata
from models.modality_config import ModalityConfig
from models.observation import Observation


class LeRobotParquetWriter:
    """Write synchronized observation/action data in LeRobot Parquet format."""

    def __init__(
        self,
        output_dir: Path,
        topic_manifest: DatasetTopicManifest | None = None,
        modality_config: ModalityConfig | None = None,
    ) -> None:
        """Initialize Parquet writer.

        Args:
            output_dir: Base output directory for LeRobot dataset
            topic_manifest: Optional topic manifest for alias resolution
            modality_config: Optional modality config for concatenated state and annotation columns
        """
        self.output_dir: Path = output_dir
        self.data_dir: Path = output_dir / "data"
        self.topic_manifest = topic_manifest
        self.modality_config = modality_config

        # Create directories
        self.data_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"LeRobotParquetWriter initialized: {output_dir}")

    def write_episode_data(
        self, synchronized_data: list[Observation], episode_index: int, chunk_index: int
    ) -> EpisodeMetadata:
        """Write episode data to Parquet format.

        Args:
            synchronized_data: Synchronized observations/actions
            episode_index: Episode number
            chunk_index: Chunk number for organizing data

        Returns:
            Episode metadata for tracking
        """
        logger.info(f"Writing episode {episode_index} to Parquet (chunk {chunk_index})")

        # Prepare data for Parquet
        rows: list[dict[str, Any]] = []
        total_frames = len(synchronized_data)

        for frame_idx, observation in enumerate(synchronized_data):
            row = self._create_parquet_row(observation, episode_index, frame_idx, total_frames)
            rows.append(row)

        # Convert to DataFrame
        df = pd.DataFrame(rows)

        # Write to Parquet file
        chunk_dir = self.data_dir / f"chunk-{chunk_index:03d}"
        chunk_dir.mkdir(exist_ok=True)

        parquet_file = chunk_dir / f"episode_{episode_index:06d}.parquet"
        df.to_parquet(parquet_file, index=False)

        logger.info(f"Wrote {len(df)} rows to {parquet_file}")

        # Generate episode metadata
        return EpisodeMetadata(
            episode_index=episode_index,
            chunk_index=chunk_index,
            frame_count=len(synchronized_data),
            duration_seconds=(synchronized_data[-1].timestamp_ns - synchronized_data[0].timestamp_ns) / 1e9,
            start_timestamp_ns=synchronized_data[0].timestamp_ns,
            end_timestamp_ns=synchronized_data[-1].timestamp_ns,
            parquet_file=str(parquet_file.relative_to(self.output_dir)),
        )

    def _create_parquet_row(
        self, observation: Observation, episode_index: int, frame_index: int, total_frames: int = 0
    ) -> dict[str, Any]:
        """Create a single Parquet row from observation data.

        Args:
            observation: Synchronized observation data
            episode_index: Episode number
            frame_index: Frame number within episode
            total_frames: Total frames in this episode (used to mark the last frame as done)

        Returns:
            Row dictionary for Parquet
        """
        row: dict[str, Any] = {
            "episode_index": episode_index,
            "frame_index": frame_index,
            "timestamp": observation.timestamp_ns / 1e9,  # Convert to seconds
        }

        for topic, observation_state in observation.state.items():
            state_alias = self.topic_manifest.get_state_alias(topic) if self.topic_manifest else topic
            row[get_observation_state_feature_name(state_alias)] = np.array(observation_state.values, dtype=np.float32)

        values = []
        for _topic, action in observation.action.items():
            values.extend(action.values)

        row["action"] = np.array(values, dtype=np.float32)

        # Concatenated observation.state: flat vector of all per-topic state values
        flat_state: list[float] = []
        for topic_state in observation.state.values():
            flat_state.extend(topic_state.values)
        if flat_state:
            row["observation.state"] = np.array(flat_state, dtype=np.float32)

        # next.done: True on the last frame of the episode
        # next.reward: 1.0 on the last frame, 0.0 otherwise
        is_last_frame = total_frames > 0 and frame_index == total_frames - 1
        row["next.reward"] = np.float32(is_last_frame)
        row["next.done"] = bool(is_last_frame)

        # annotation.human.action.task_description: copied from task_index if present
        row["annotation.human.action.task_description"] = np.int64(row.get("task_index", 0))
        # annotation.human.validity: default 1 (validated)
        row["annotation.human.validity"] = np.int64(1)

        return row
