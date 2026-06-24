"""LeRobot Dataset Converter for MCAP CompressedVideo files.

Conversion pipeline (in order):
  1. Read MCAP  — extract compressed video, robot states, and actions via LeRobotMCAPReader.
  2. Decode frames — decompress each video stream into per-frame images via VideoFrameExtractor.
  3. Synchronize — resample all modalities to a common target-FPS grid via TemporalSynchronizer.
  4. Write Parquet — serialize synchronized observations to chunked Parquet files via LeRobotParquetWriter.
  5. Write videos — encode the synchronized frames into target-FPS videos via LeRobotVideoWriter.
  6. Write metadata — generate episodes.jsonl / tasks.jsonl / info.json / modality.json via LeRobotMetadataGenerator.
"""

import json
from dataclasses import dataclass
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
from models.observation import Observation
from models.topic_statistics import TopicStatistics
from models.video_frame import VideoFrame


@dataclass(frozen=True)
class DatasetSchema:
    """Feature structure that every episode in a dataset must share.

    LeRobot datasets require identical features across all episodes (same cameras,
    observation-state layout, and action vector). These three fields are what
    `LeRobotConverter.finalize_dataset` uses to describe the whole dataset.
    """

    video_infos: dict[str, dict[str, Any]]
    observation_names: dict[str, list[str]]
    action_names: list[str]

    def camera_shapes(self) -> dict[str, tuple[Any, Any, Any]]:
        """Map each camera name to its (height, width, channels)."""
        return {
            name: (info.get("video.height"), info.get("video.width"), info.get("video.channels"))
            for name, info in self.video_infos.items()
        }

    def structure_fingerprint(self) -> tuple[Any, ...]:
        """Return a comparable signature of the schema-defining structure."""
        cameras = tuple((name, *shape) for name, shape in sorted(self.camera_shapes().items()))
        observations = tuple((topic, tuple(names)) for topic, names in sorted(self.observation_names.items()))
        return (cameras, observations, tuple(self.action_names))


@dataclass
class ConvertedEpisode:
    """Artifacts produced by converting a single episode."""

    episode_metadata: EpisodeMetadata
    task_definition: dict[str, Any]
    schema: DatasetSchema


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

        logger.debug(f"LeRobotConverter initialized: {output_dir}")
        logger.debug(f"Target FPS: {target_fps}, Dataset: {dataset_name}")

    def convert_episode(self, mcap_file: Path, episode_index: int = 0) -> ConvertedEpisode:
        """Convert a single MCAP file to LeRobot episode artifacts (Parquet + videos).

        Does **not** finalize dataset metadata — call `finalize_dataset` once after
        all episodes have been converted.

        Args:
            mcap_file: Path to input MCAP file.
            episode_index: Episode number.

        Returns:
            A `ConvertedEpisode` with all per-episode artifacts.
        """
        logger.info(f"Converting episode {episode_index}: {mcap_file}")

        if not mcap_file.exists():
            raise FileNotFoundError(f"MCAP file not found: {mcap_file}")

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
            video_infos = self._write_video_files(synchronized_data, episode_index, chunk_index)

            # Step 6: Update episode metadata
            episode_meta.mcap_file = str(mcap_file)
            episode_meta.synchronized_frames = len(synchronized_data)
            episode_meta.tasks = [str(task_definition["task"])]

            # Step 7: Generate synchronization statistics
            sync_stats: dict[str, Any] = self.synchronizer.calculate_synchronization_stats(synchronized_data)
            episode_meta.sync_stats = sync_stats

            logger.info(f"Episode {episode_index} converted successfully")
            logger.info(f"Generated {len(synchronized_data)} synchronized observations")

            return ConvertedEpisode(
                episode_metadata=episode_meta,
                task_definition=task_definition,
                schema=DatasetSchema(
                    video_infos=video_infos,
                    observation_names=get_observation_names(synchronized_data[0]),
                    action_names=get_action_names(synchronized_data[0]),
                ),
            )

        except Exception as e:
            # Try to get the episode UUID for logging purposes; fall back to the full path otherwise.
            episode_info = mcap_file.parent.parent.name if mcap_file.parent.name == "mcap" else str(mcap_file)
            logger.error(f"Failed to convert episode {episode_index} ({episode_info}): {e}")
            raise

    def _default_task_definition(self) -> dict[str, Any]:
        """Return the default task definition for single-episode conversion."""
        return {"task": self.DEFAULT_TASK_NAME}

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
            return {"task": task_description.strip()}

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
            dataset_description: Human-readable dataset description to embed in metadata
            video_infos: Video metadata per topic (codecs, dimensions, etc.)
            observation_names: Observation names grouped by modality
            action_topics: Action topic names used in the dataset
            episode_metadata: Episode-level metadata entries
            task_definitions: Task definitions to write to tasks metadata
            additional_info: Optional additional metadata to include

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

            # Episodes statistics metadata (one entry per episode)
            episode_indices = [meta.episode_index for meta in episode_metadata]
            metadata_files["episodes_stats"] = self.metadata_generator.write_episodes_stats_metadata(
                episode_indices, features
            )

            # Tasks metadata
            metadata_files["tasks"] = self.metadata_generator.write_tasks_metadata(task_definitions)

            # Dataset info
            metadata_files["info"] = self.metadata_generator.write_dataset_info(
                episode_metadata, features, int(self.target_fps), additional_info, total_tasks=len(task_definitions)
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
        self, synchronized_data: list[Observation], episode_index: int, chunk_index: int
    ) -> dict[str, dict[str, Any]]:
        """Encode one target-FPS video per camera from the synchronized frames."""
        if not synchronized_data:
            raise ValueError(f"No synchronized observations to write videos for (episode {episode_index})")

        video_infos = {}
        for camera_topic in synchronized_data[0].image:
            # Clean camera name for file system
            camera_alias = self.topic_manifest.get_image_alias(camera_topic) if self.topic_manifest else camera_topic
            camera_name: str = get_video_feature_name(camera_alias)

            frames = [observation.image[camera_topic].image for observation in synchronized_data]

            video_file: Path = self.video_writer.write_video_from_frames(
                frames, camera_name, episode_index, chunk_index, self.target_fps
            )

            video_info = get_video_info(video_file)
            video_infos[camera_topic] = video_info

            logger.debug(f"video properties: {json.dumps(video_info)}")
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


def convert_mcaps_to_lerobot(  # noqa: PLR0913
    mcap_files: tuple[Path, ...] | list[Path],
    output_dir: Path,
    target_fps: float = 20.0,
    dataset_name: str = "robot_dataset",
    station_config_path: Path | None = None,
    recorder_config_path: Path | None = None,
    modality_config_path: Path | None = None,
) -> dict[str, Any]:
    """Convert one or more MCAP files into a single LeRobot dataset.

    Args:
        mcap_files: Ordered paths to MCAP files (each becomes one episode)
        output_dir: Output directory for the LeRobot dataset
        target_fps: Target frame rate
        dataset_name: Dataset name
        station_config_path: Path to config_station.yml
        recorder_config_path: Path to config_data_recorder.yml
        modality_config_path: Path to modality.json

    Returns:
        Conversion result dict with episode metadata, metadata files, and dataset dir
    """
    converter = LeRobotConverter(
        output_dir, target_fps, dataset_name, station_config_path, recorder_config_path, modality_config_path
    )

    all_episode_meta: list[EpisodeMetadata] = []
    all_task_defs: list[dict[str, Any]] = []
    reference_episode: ConvertedEpisode | None = None

    try:
        for episode_index, mcap_file in enumerate(mcap_files):
            mcap_path = Path(mcap_file)

            converted = converter.convert_episode(mcap_path, episode_index=episode_index)

            if reference_episode is None:
                reference_episode = converted
            else:
                _assert_consistent_structure(reference_episode, converted, episode_index, mcap_path)

            all_episode_meta.append(converted.episode_metadata)

            # Record each distinct task only once, assigning it the next free task index
            if not any(t["task"] == converted.task_definition["task"] for t in all_task_defs):
                all_task_defs.append({**converted.task_definition, "task_index": len(all_task_defs)})

        if reference_episode is None:
            raise ValueError("No MCAP files were provided; cannot build a dataset.")

        description = f"Dataset with {len(all_episode_meta)} episode(s) converted from MCAP files"
        metadata_files = converter.finalize_dataset(
            description,
            reference_episode.schema.video_infos,
            reference_episode.schema.observation_names,
            reference_episode.schema.action_names,
            all_episode_meta,
            all_task_defs,
        )

        return {
            "episode_metadata": all_episode_meta,
            "metadata_files": metadata_files,
            "dataset_dir": output_dir,
        }

    finally:
        converter.close()


def _assert_consistent_structure(
    reference: ConvertedEpisode,
    current: ConvertedEpisode,
    episode_index: int,
    mcap_file: Path,
) -> None:
    """Raise error if current episode does not share the reference episode's feature structure."""
    if reference.schema.structure_fingerprint() == current.schema.structure_fingerprint():
        return

    reference_cameras = reference.schema.camera_shapes()
    current_cameras = current.schema.camera_shapes()

    differences: list[str] = []
    if reference_cameras != current_cameras:
        differences.append(f"cameras: expected {reference_cameras}, got {current_cameras}")
    if reference.schema.observation_names != current.schema.observation_names:
        differences.append(
            f"observation state: expected {reference.schema.observation_names}, got {current.schema.observation_names}"
        )
    if reference.schema.action_names != current.schema.action_names:
        differences.append(f"actions: expected {reference.schema.action_names}, got {current.schema.action_names}")

    raise ValueError(
        f"Episode {episode_index} ({mcap_file}) has a different structure than the first episode "
        f"and cannot be combined into one dataset. Differences -> " + "; ".join(differences)
    )
