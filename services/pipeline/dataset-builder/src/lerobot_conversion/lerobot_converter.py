"""LeRobot Dataset Converter for MCAP CompressedVideo files.

Conversion pipeline (in order):
  1. Read MCAP  — extract compressed video, robot states, and actions via LeRobotMCAPReader.
  2. Decode frames — decompress each video stream into per-frame images via VideoFrameExtractor.
  3. Synchronize — resample all modalities to a common target-FPS grid via TemporalSynchronizer.
  4. Write Parquet — serialize synchronized observations to chunked Parquet files via LeRobotParquetWriter.
  5. Write videos — copy the raw compressed video bytes into LeRobot's directory layout via LeRobotVideoWriter.
  6. Write metadata — generate episodes.jsonl / tasks.jsonl / info.json / modality.json via LeRobotMetadataGenerator.
"""

import json
from pathlib import Path
from typing import Any

from lerobot.datasets.utils import (  # type: ignore[import-not-found]
    DEFAULT_CHUNK_SIZE,
    DEFAULT_FEATURES,
)
from lerobot.datasets.video_utils import get_video_info  # type: ignore[import-not-found]
from loguru import logger

from lerobot_conversion.lerobot_mcap_reader import LeRobotMCAPReader
from lerobot_conversion.lerobot_metadata_generator import LeRobotMetadataGenerator
from lerobot_conversion.lerobot_parquet_writer import LeRobotParquetWriter
from lerobot_conversion.lerobot_utils import (
    get_action_names,
    get_observation_names,
    get_observation_state_feature_name,
    get_video_feature_name,
)
from lerobot_conversion.lerobot_video_writer import LeRobotVideoWriter
from lerobot_conversion.temporal_synchronizer import TemporalSynchronizer
from lerobot_conversion.topic_manifest import load_topic_manifest
from lerobot_conversion.video_frame_extractor import VideoFrameExtractor
from models.compressed_video_info import CompressedVideoInfo
from models.episode_metadata import EpisodeMetadata
from models.extracted_mcap_data import ExtractedMcapData
from models.feature import Feature, VideoFeature
from models.modality_config import ModalityConfig
from models.topic_statistics import TopicStatistics
from models.video_frame import VideoFrame


class LeRobotConverter:
    """Main converter for transforming MCAP files to LeRobot dataset format."""

    DEFAULT_TASK_NAME = "robot_demonstration"

    def __init__(  # noqa: PLR0913
        self,
        output_dir: Path,
        target_fps: float = 20.0,
        dataset_name: str = "robot_dataset",
        station_config_path: Path | None = None,
        recorder_config_path: Path | None = None,
        modality_config_path: Path | None = None,
    ) -> None:
        """Initialize LeRobot converter.

        Args:
            output_dir: Output directory for LeRobot dataset
            target_fps: Target frame rate for synchronization
            dataset_name: Name of the dataset
            station_config_path: Path to config_station.yml
            recorder_config_path: Path to config_data_recorder.yml
            modality_config_path: Path to modality.json defining state/annotation structure
        """
        self.output_dir: Path = output_dir
        self.target_fps: float = target_fps
        self.dataset_name: str = dataset_name

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.topic_manifest = load_topic_manifest(station_config_path, recorder_config_path)

        self.modality_config: ModalityConfig | None = (
            ModalityConfig.from_file(modality_config_path) if modality_config_path is not None else None
        )
        if self.modality_config is not None:
            logger.info(f"Loaded modality config from {modality_config_path}")

        # Initialize components
        self.mcap_reader: LeRobotMCAPReader = LeRobotMCAPReader(topic_manifest=self.topic_manifest)
        self.frame_extractor = VideoFrameExtractor(target_fps)
        self.synchronizer = TemporalSynchronizer(target_fps)
        self.parquet_writer = LeRobotParquetWriter(output_dir, self.topic_manifest, self.modality_config)
        self.video_writer = LeRobotVideoWriter(output_dir)
        self.metadata_generator = LeRobotMetadataGenerator(output_dir)

        logger.info(f"LeRobotConverter initialized: {output_dir}")
        logger.info(f"Target FPS: {target_fps}, Dataset: {dataset_name}")

    def convert_episode(
        self, mcap_file: Path, episode_index: int = 0, chunk_index: int | None = None
    ) -> dict[str, Any]:
        """Convert a single MCAP file to LeRobot format.

        Args:
            mcap_file: Path to input MCAP file
            episode_index: Episode number
            task_index: Task identifier
            chunk_index: Chunk number for organizing data. If omitted, derive it from episode_index.

        Returns:
            Episode conversion metadata
        """
        logger.info(f"Converting episode {episode_index}: {mcap_file}")

        if not mcap_file.exists():
            raise FileNotFoundError(f"MCAP file not found: {mcap_file}")

        if chunk_index is None:
            chunk_index = episode_index // DEFAULT_CHUNK_SIZE

        try:
            # Step 1: Extract data from MCAP
            extracted_data = self._extract_mcap_data(mcap_file)
            self._validate_extracted_data(extracted_data)
            task_definition = self._load_task_definition(extracted_data.metadata)

            # Step 2: Extract video frames
            videos = {
                topic: self._extract_video_frames(topic, extracted_data.video_topics[topic], video)
                for topic, video in extracted_data.compressed_videos.items()
            }

            # Step 3: Synchronize all modalities
            synchronized_data = self.synchronizer.synchronize_episode_data(videos, extracted_data)

            # Step 4: Write synchronized data to Parquet
            episode_meta = self.parquet_writer.write_episode_data(synchronized_data, episode_index, chunk_index)

            # Step 5: Write video files
            video_infos = self._write_video_files(extracted_data.compressed_videos, episode_index, chunk_index)

            # Step 6: Update episode metadata
            episode_meta.mcap_file = str(mcap_file)
            episode_meta.synchronized_frames = len(synchronized_data)
            episode_meta.tasks = [str(task_definition["task"])]

            # Step 7: Generate synchronization statistics
            sync_stats: dict[str, Any] = self.synchronizer.calculate_synchronization_stats(synchronized_data)
            episode_meta.sync_stats = sync_stats

            logger.info(f"Episode {episode_index} converted successfully")
            logger.info(f"Generated {len(synchronized_data)} synchronized observations")

            # Finalize dataset
            metadata_files: dict[str, Path] = self.finalize_dataset(
                f"Single episode dataset converted from {mcap_file.name}",
                video_infos,
                get_observation_names(synchronized_data[0]),
                get_action_names(synchronized_data[0]),
                [episode_meta],
                [task_definition],
            )

            return {"episode_metadata": episode_meta, "metadata_files": metadata_files, "dataset_dir": self.output_dir}

        except Exception as e:
            logger.error(f"Failed to convert episode {episode_index}: {e}")
            raise

    def _default_task_definition(self) -> dict[str, Any]:
        """Return the default task definition for single-episode conversion."""
        return {"task_index": 0, "task": self.DEFAULT_TASK_NAME}

    def _load_task_definition(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Load a task definition from MCAP metadata when available."""
        episode_context = metadata.get("episode_context")
        if not isinstance(episode_context, dict):
            return self._default_task_definition()

        serialized_context = episode_context.get("data")
        if not isinstance(serialized_context, str):
            return self._default_task_definition()

        try:
            decoded_context = json.loads(serialized_context)
        except json.JSONDecodeError as exc:
            logger.warning(f"Failed to decode episode_context metadata: {exc}")
            return self._default_task_definition()

        task_description = decoded_context.get("task_description")
        if isinstance(task_description, str) and task_description.strip():
            return {"task_index": 0, "task": task_description.strip()}

        return self._default_task_definition()

    def finalize_dataset(  # noqa: PLR0913
        self,
        dataset_description: str,
        video_infos: dict[str, dict[str, Any]],
        observation_names: dict[str, list[str]],
        action_topics: list[str],
        episode_metadata: list[EpisodeMetadata],
        task_definitions: list[dict[str, Any]],
        additional_info: dict[str, Any] | None = None,
    ) -> dict[str, Path]:
        """Finalize dataset by generating all metadata files.

        Args:
            dataset_description: Human-readable dataset description to embed in metadata.
            video_infos: Video metadata per topic (codecs, dimensions, etc.).
            observation_names: Observation names grouped by modality.
            action_topics: Action topic names used in the dataset.
            episode_metadata: Episode-level metadata entries.
            task_definitions: Task definitions to write to tasks metadata.
            additional_info: Optional additional metadata to include.

        Returns:
            Dictionary of created metadata file paths.
        """
        logger.info("Finalizing LeRobot dataset...")

        # Create metadata files
        metadata_files = {}

        try:
            # Episodes metadata
            metadata_files["episodes"] = self.metadata_generator.write_episodes_metadata(episode_metadata)

            # Generate features
            features = self._generate_features(video_infos, observation_names, action_topics)

            # Episodes statistics metadata
            metadata_files["episodes_stats"] = self.metadata_generator.write_episodes_stats_metadata(0, features)

            # Tasks metadata
            metadata_files["tasks"] = self.metadata_generator.write_tasks_metadata(task_definitions)

            # Dataset info
            metadata_files["info"] = self.metadata_generator.write_dataset_info(
                episode_metadata, features, int(self.target_fps), additional_info
            )

            # Modality metadata (written when a modality config is available)
            if self.modality_config is not None:
                metadata_files["modality"] = self.metadata_generator.write_modality_metadata(
                    self.modality_config.to_dict()
                )

            # Dataset README
            metadata_files["readme"] = self.metadata_generator.create_dataset_readme(
                self.dataset_name, dataset_description
            )

            # Validate all metadata
            if self.metadata_generator.validate_metadata_files():
                logger.info("Dataset finalized successfully")
            else:
                logger.warning("Dataset finalized with validation warnings")

        except Exception as e:
            logger.error(f"Failed to finalize dataset: {e}")
            raise

        return metadata_files

    def _extract_mcap_data(self, mcap_file: Path) -> ExtractedMcapData:
        """Extract data from MCAP file."""
        extracted_data = self.mcap_reader.extract_lerobot_data(mcap_file)

        logger.info("Extracted MCAP data:")
        logger.info(f"  CompressedVideo topics: {list(extracted_data.compressed_videos.keys())}")
        logger.info(f"  Robot state topics: {list(extracted_data.robot_states.keys())}")
        logger.info(f"  Action topics: {list(extracted_data.actions.keys())}")

        return extracted_data

    def _validate_extracted_data(self, extracted_data: ExtractedMcapData) -> None:
        """Validate extracted MCAP data before conversion continues."""
        if extracted_data.compressed_videos:
            return

        available_modalities = []
        if extracted_data.robot_states:
            available_modalities.append(f"robot states: {list(extracted_data.robot_states.keys())}")
        if extracted_data.actions:
            available_modalities.append(f"actions: {list(extracted_data.actions.keys())}")

        available_summary = (
            "; ".join(available_modalities) if available_modalities else "no supported topics were extracted"
        )
        raise ValueError(
            "No compressed video topics were found in the input MCAP. "
            "The dataset builder requires at least one video stream."
            f"Available extracted data: {available_summary}."
        )

    def _extract_video_frames(
        self,
        topic: str,
        video_stats: TopicStatistics,
        compressed_video: CompressedVideoInfo,
    ) -> list[VideoFrame]:
        """Extract video frames from CompressedVideo data."""
        logger.info(f"Extracting frames from camera: {topic}")
        video_bytes = compressed_video.data

        return self.frame_extractor.extract_frames(
            video_bytes,
            video_stats.first_message_time_ns,
            video_stats.last_message_time_ns - video_stats.first_message_time_ns,
        )

    def _write_video_files(
        self, compressed_video: dict[str, CompressedVideoInfo], episode_index: int, chunk_index: int
    ) -> dict[str, dict[str, Any]]:
        """Write video files to LeRobot structure."""
        video_infos = {}
        for camera_topic, video_data in compressed_video.items():
            # Clean camera name for file system
            camera_alias = self.topic_manifest.get_image_alias(camera_topic) if self.topic_manifest else camera_topic
            camera_name: str = get_video_feature_name(camera_alias)

            video_file: Path = self.video_writer.write_video_file(
                video_data.data, camera_name, episode_index, chunk_index
            )

            logger.info(f"Wrote video file: {video_file}")

            video_info = get_video_info(video_file)
            video_infos[camera_topic] = video_info

            logger.info(f"video properties: {json.dumps(video_info)}")
        return video_infos

    def _generate_features(
        self, video_infos: dict[str, dict[str, Any]], observation_names: dict[str, list[str]], action_topics: list[str]
    ) -> dict[str, Feature]:
        """Generate feature definitions."""
        # This covers the default features:
        # - timestamp
        # - frame_index
        # - episode_index
        # - index
        # - task_index
        default_features: dict[str, Feature] = {
            k: Feature(dtype=v["dtype"], shape=v["shape"], names=v["names"]) for k, v in DEFAULT_FEATURES.items()
        }

        # Video features: one entry per camera, keyed by the observation.images.<alias> name
        video_features: dict[str, VideoFeature] = {}
        for topic, video_info in video_infos.items():
            alias = self.topic_manifest.get_image_alias(topic) if self.topic_manifest else topic
            feature_name = get_video_feature_name(alias)
            video_features[feature_name] = VideoFeature(
                names=["height", "width", "channels"],
                shape=(video_info["video.height"], video_info["video.width"], video_info["video.channels"]),
                video_info=video_info,
            )

        observation_state_features: dict[str, Feature] = {
            get_observation_state_feature_name(
                self.topic_manifest.get_state_alias(topic) if self.topic_manifest else topic
            ): Feature(dtype="float32", shape=(len(names),), names=names)
            for topic, names in observation_names.items()
        }

        action_features: dict[str, Feature] = {
            "action": Feature(
                dtype="float32",
                shape=(len(action_topics),),
                names=action_topics,
            ),
        }

        transition_features: dict[str, Feature] = {
            "next.reward": Feature(dtype="float32", shape=(1,), names=None),
            "next.done": Feature(dtype="bool", shape=(1,), names=None),
        }
        annotation_features: dict[str, Feature] = {
            "annotation.human.action.task_description": Feature(dtype="int64", shape=(1,), names=None),
            "annotation.human.validity": Feature(dtype="int64", shape=(1,), names=None),
        }

        # Flat concatenation of all per-topic observation state vectors
        observation_state_flat_features: dict[str, Feature] = {}
        flat_state_names: list[str] = []
        for topic, names in observation_names.items():
            alias = self.topic_manifest.get_state_alias(topic) if self.topic_manifest else topic
            for fn in names:
                flat_state_names.append(f"{alias}_{fn}")
        if flat_state_names:
            observation_state_flat_features["observation.state"] = Feature(
                dtype="float32",
                shape=(len(flat_state_names),),
                names=flat_state_names,
            )

        features: dict[str, Feature] = {
            **default_features,
            **video_features,
            **observation_state_features,
            **action_features,
            **transition_features,
            **annotation_features,
            **observation_state_flat_features,
        }
        return features

    def close(self) -> None:
        """Clean up resources."""
        if self.frame_extractor:
            self.frame_extractor.close()

        logger.info("LeRobotConverter closed")


def convert_mcap_to_lerobot(  # noqa: PLR0913
    mcap_file: Path,
    output_dir: Path,
    target_fps: float = 20.0,
    dataset_name: str = "robot_dataset",
    station_config_path: Path | None = None,
    recorder_config_path: Path | None = None,
    modality_config_path: Path | None = None,
) -> dict[str, Any]:
    """Convenience function to convert a single MCAP file to LeRobot format.

    Args:
        mcap_file: Path to MCAP file
        output_dir: Output directory for LeRobot dataset
        target_fps: Target frame rate
        dataset_name: Dataset name
        station_config_path: Path to config_station.yml
        recorder_config_path: Path to config_data_recorder.yml
        modality_config_path: Path to modality.json

    Returns:
        Conversion metadata
    """
    converter = LeRobotConverter(
        output_dir, target_fps, dataset_name, station_config_path, recorder_config_path, modality_config_path
    )

    try:
        return converter.convert_episode(mcap_file)

    finally:
        converter.close()
