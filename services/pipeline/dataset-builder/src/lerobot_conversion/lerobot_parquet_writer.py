"""Parquet Writer for LeRobot dataset format."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger
from pipeline_configs import PolicyContract

from lerobot_conversion.lerobot_utils import get_annotation_feature_name, get_observation_state_feature_name
from models.episode_metadata import EpisodeMetadata
from models.observation import Observation

# annotation columns are indices into an external table, never policy values
ANNOTATION_DTYPE = np.int64
# an annotation without an original_key to copy is a flag dataset-builder asserts (human.validity)
DEFAULT_ANNOTATION_VALUE = 1


class LeRobotParquetWriter:
    """Write synchronized observation/action data in LeRobot Parquet format."""

    def __init__(self, output_dir: Path, contract: PolicyContract) -> None:
        """Initialize Parquet writer.

        Args:
            output_dir: Base output directory for LeRobot dataset
            contract: Policy contract defining column order, layout and dtype
        """
        self.output_dir: Path = output_dir
        self.data_dir: Path = output_dir / "data"
        self.contract = contract
        self.dtype = np.dtype(contract.policy.dtype)

        # Create directories
        self.data_dir.mkdir(parents=True, exist_ok=True)

        logger.debug(f"LeRobotParquetWriter initialized: {output_dir}")

    def write_episode_data(
        self, synchronized_data: list[Observation], episode_index: int, chunk_index: int, task_index: int = 0
    ) -> EpisodeMetadata:
        """Write episode data to Parquet format.

        Args:
            synchronized_data: Synchronized observations/actions
            episode_index: Episode number
            chunk_index: Chunk number for organizing data
            task_index: Index of this episode's task in tasks.jsonl

        Returns:
            Episode metadata for tracking
        """
        logger.info(f"Writing episode {episode_index} to Parquet (chunk {chunk_index})")

        total_frames = len(synchronized_data)
        rows = [
            self._create_parquet_row(observation, episode_index, frame_index, total_frames, task_index)
            for frame_index, observation in enumerate(synchronized_data)
        ]

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
        self,
        observation: Observation,
        episode_index: int,
        frame_index: int,
        total_frames: int = 0,
        task_index: int = 0,
    ) -> dict[str, Any]:
        """Create a single Parquet row from observation data.

        Args:
            observation: Synchronized observation data
            episode_index: Episode number
            frame_index: Frame number within episode
            total_frames: Total frames in this episode (used to mark the last frame as done)
            task_index: Index of this episode's task in tasks.jsonl

        Returns:
            Row dictionary for Parquet
        """
        row: dict[str, Any] = {
            "episode_index": episode_index,
            "frame_index": frame_index,
            "timestamp": observation.timestamp_ns / 1e9,  # Convert to seconds
            "task_index": ANNOTATION_DTYPE(task_index),
        }

        for segment in self.contract.state:
            values = observation.state[segment.policy_key].values
            row[get_observation_state_feature_name(segment.policy_key)] = np.array(values, dtype=self.dtype)

        # observation.state / action are the concatenations the contract's slices index into,
        # so they must follow its declaration order rather than the extraction order
        row["observation.state"] = np.array(
            [value for segment in self.contract.state for value in observation.state[segment.policy_key].values],
            dtype=self.dtype,
        )
        row["action"] = np.array(
            [value for segment in self.contract.action for value in observation.action[segment.policy_key].values],
            dtype=self.dtype,
        )

        # next.done: True on the last frame of the episode
        # next.reward: 1.0 on the last frame, 0.0 otherwise
        is_last_frame = total_frames > 0 and frame_index == total_frames - 1
        row["next.reward"] = np.float32(is_last_frame)
        row["next.done"] = bool(is_last_frame)

        for annotation in self.contract.annotations:
            source_value = row.get(annotation.original_key, 0) if annotation.original_key else DEFAULT_ANNOTATION_VALUE
            row[get_annotation_feature_name(annotation.policy_key)] = ANNOTATION_DTYPE(source_value)

        return row
