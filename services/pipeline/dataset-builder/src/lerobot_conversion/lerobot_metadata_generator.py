"""LeRobot Metadata Generator for creating episodes.jsonl, tasks.jsonl, and info.json."""

import json
from pathlib import Path
from typing import Any

import numpy as np
from lerobot.datasets.compute_stats import compute_episode_stats  # type: ignore[import-not-found]
from lerobot.datasets.utils import DEFAULT_CHUNK_SIZE, write_episode_stats  # type: ignore[import-not-found]
from loguru import logger

from models.episode_metadata import EpisodeMetadata
from models.feature import Feature


class LeRobotMetadataGenerator:
    """Generate LeRobot dataset metadata files."""

    def __init__(self, output_dir: Path) -> None:
        """Initialize metadata generator.

        Args:
            output_dir: Base output directory for LeRobot dataset
        """
        self.output_dir: Path = output_dir
        self.meta_dir: Path = output_dir / "meta"
        self.meta_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"LeRobotMetadataGenerator initialized: {self.meta_dir}")

    def write_episodes_metadata(self, episodes_metadata: list[EpisodeMetadata]) -> Path:
        """Write episodes.jsonl file.

        Args:
            episodes_metadata: List of episode metadata objects.

        Returns:
            Path to episodes.jsonl file
        """
        episodes_file: Path = self.meta_dir / "episodes.jsonl"

        with episodes_file.open("w") as f:
            for episode_meta in episodes_metadata:
                episode_entry: dict[str, Any] = {
                    "episode_index": episode_meta.episode_index,
                    "tasks": episode_meta.tasks,
                    "length": episode_meta.frame_count,
                }
                f.write(json.dumps(episode_entry) + "\n")

        logger.info(f"Wrote {len(episodes_metadata)} episodes to {episodes_file}")
        return episodes_file

    def write_tasks_metadata(self, task_definitions: list[dict[str, Any]]) -> Path:
        """Write tasks.jsonl file.

        Args:
            task_definitions: List of task definitions

        Returns:
            Path to tasks.jsonl file
        """
        tasks_file: Path = self.meta_dir / "tasks.jsonl"

        with tasks_file.open("w") as f:
            for task in task_definitions:
                f.write(json.dumps(task) + "\n")

        logger.info(f"Wrote {len(task_definitions)} tasks to {tasks_file}")
        return tasks_file

    def write_episodes_stats_metadata(self, episode_index: int, features: dict[str, Feature]) -> Path:
        """Write episodes_stats.jsonl file.

        Returns:
            Path to episodes_stats.jsonl file
        """
        episodes_stats_file: Path = self.meta_dir / "episodes_stats.jsonl"

        # Empty buffer: stats are not computed in-memory here. LeRobot handles this gracefully
        # by producing zero-filled stats, which downstream consumers recompute on load.
        episode_buffer: dict[str, list[str] | np.ndarray] = {}
        episode_stats = compute_episode_stats(
            episode_buffer, {key: feature.to_dict for key, feature in features.items()}
        )

        # Re-create the episodes_stats_file to ensure it's fresh
        if episodes_stats_file.exists():
            episodes_stats_file.unlink()
        episodes_stats_file.touch()

        write_episode_stats(episode_index, episode_stats, self.output_dir)

        logger.info(f"Wrote episodes stats to {episodes_stats_file}")
        return episodes_stats_file

    def write_dataset_info(
        self,
        episode_metadata_list: list[EpisodeMetadata],
        features: dict[str, Feature],
        fps: int = 20,
        additional_info: dict[str, Any] | None = None,
    ) -> Path:
        """Write info.json file.

        Args:
            episode_metadata_list: List of episode metadata
            features: Feature definitions from Parquet data
            fps: Dataset frame rate
            additional_info: Optional additional metadata

        Returns:
            Path to info.json file
        """
        info_file: Path = self.meta_dir / "info.json"

        # Calculate dataset statistics
        total_episodes: int = len(episode_metadata_list)
        total_frames: int = sum(meta.frame_count for meta in episode_metadata_list)
        total_duration = int(sum(meta.duration_seconds for meta in episode_metadata_list))
        total_chunks = max((meta.chunk_index for meta in episode_metadata_list), default=-1) + 1

        info_data: dict[str, Any] = {
            "codebase_version": "v2.1",
            "robot_type": None,
            "total_episodes": total_episodes,
            "total_frames": total_frames,
            "total_tasks": 1,
            "total_videos": len([f for f in features if features[f].dtype == "video"]),
            "total_chunks": total_chunks,
            "chunks_size": DEFAULT_CHUNK_SIZE,
            "fps": int(fps),
            "splits": {"train": f"0:{total_episodes}"},
            "data_path": "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet",
            "video_path": "videos/chunk-{episode_chunk:03d}/{video_key}/episode_{episode_index:06d}.mp4",
            "features": {name: feature.to_dict() for name, feature in features.items()},
        }

        # Add additional info if provided
        if additional_info:
            info_data.update(additional_info)

        # Add dataset creation metadata
        info_data["creation_metadata"] = {
            "source": "labs-mcap-converter",
            "conversion_method": "compressed_video_to_lerobot",
            "target_fps": fps,
            "synchronization_method": "linear_interpolation",
        }

        with info_file.open("w") as f:
            json.dump(info_data, f, indent=2, default=str)

        logger.info(f"Wrote dataset info to {info_file}")
        logger.info(f"Dataset stats: {total_episodes} episodes, {total_frames} frames, {total_duration:.1f}s")
        return info_file

    def write_modality_metadata(self, modality_info: dict[str, dict[str, Any]]) -> Path:
        """Write modality.json file (optional).

        Args:
            modality_info: Modality mapping information

        Returns:
            Path to modality.json file
        """
        modality_file: Path = self.meta_dir / "modality.json"

        with modality_file.open("w") as f:
            json.dump(modality_info, f, indent=2)

        logger.info(f"Wrote modality info to {modality_file}")
        return modality_file

    def create_dataset_readme(
        self, dataset_name: str, description: str | None = None, additional_notes: str | None = None
    ) -> Path:
        """Create a README.md file for the dataset.

        Args:
            dataset_name: Name of the dataset
            description: Dataset description
            additional_notes: Additional notes about the dataset

        Returns:
            Path to README.md file
        """
        readme_file: Path = self.output_dir / "README.md"

        readme_content: str = f"""# {dataset_name}

## Description

{description or "Robotics demonstration dataset converted from MCAP format."}

## Dataset Structure

This dataset follows the LeRobot format:

```
dataset/
├── data/chunk-000/
│   ├── episode_000000.parquet
│   ├── episode_000001.parquet
│   └── ...
├── videos/chunk-000/
│   ├── observation.images.camera_name/
│   │   ├── episode_000000.mp4
│   │   ├── episode_000001.mp4
│   │   └── ...
│   └── ...
└── meta/
    ├── episodes.jsonl
    ├── tasks.jsonl
    ├── info.json
    └── modality.json (optional)
```

## Data Format

- **Parquet files**: Contain synchronized observation and action data at 20 Hz
- **Video files**: MP4 format with AV1 compression
- **Metadata files**: Episode, task, and feature definitions

## Conversion Details

- Source: MCAP files with CompressedVideo and robot state data
- Target FPS: 20 Hz
- Synchronization: Linear interpolation of robot states and actions
- Video format: AV1 compressed MP4 files

{additional_notes or ""}

## Usage

Load this dataset with the LeRobot library:

```python
from lerobot_conversion.common.datasets.lerobot_dataset import LeRobotDataset

dataset = LeRobotDataset("path/to/dataset")
```
"""

        with readme_file.open("w") as f:
            f.write(readme_content)

        logger.info(f"Created dataset README: {readme_file}")
        return readme_file

    def validate_metadata_files(self) -> bool:
        """Validate that all required metadata files exist and are valid.

        Returns:
            True if all files are valid, False otherwise
        """
        required_files: list[str] = ["episodes.jsonl", "tasks.jsonl", "info.json"]

        all_valid = True

        for filename in required_files:
            file_path: Path = self.meta_dir / filename

            if not file_path.exists():
                logger.error(f"Missing required metadata file: {filename}")
                all_valid = False
                continue

            try:
                if filename.endswith(".jsonl"):
                    # Validate JSONL format
                    with file_path.open("r") as f:
                        for _line_num, line in enumerate(f, 1):
                            json.loads(line.strip())
                else:
                    # Validate JSON format
                    with file_path.open("r") as f:
                        json.load(f)

                logger.info(f"Validated metadata file: {filename}")

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in {filename}: {e}")
                all_valid = False
            except Exception as e:
                logger.error(f"Error validating {filename}: {e}")
                all_valid = False

        if all_valid:
            logger.info("All metadata files are valid")
        else:
            logger.error("Some metadata files are invalid")

        return all_valid
