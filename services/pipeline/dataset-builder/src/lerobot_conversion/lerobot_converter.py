"""LeRobot Dataset Converter for MCAP CompressedVideo files.

Conversion pipeline (in order):
  1. Read MCAP  — extract the cameras, state and action segments the policy contract declares.
  2. Decode frames — decompress each video stream into per-frame images at the camera's declared
     shape via VideoFrameExtractor, scaling to it where the contract enables resize.
  3. Synchronize — resample all modalities to a common target-FPS grid via TemporalSynchronizer.
  4. Write Parquet — serialize synchronized observations to chunked Parquet files via LeRobotParquetWriter.
  5. Write videos — encode the synchronized frames into target-FPS videos via LeRobotVideoWriter.
  6. Write metadata — generate episodes.jsonl / tasks.jsonl / info.json / modality.json via LeRobotMetadataGenerator.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lerobot.datasets.utils import DEFAULT_CHUNK_SIZE  # type: ignore[import-not-found]
from lerobot.datasets.video_utils import get_video_info  # type: ignore[import-not-found]
from loguru import logger
from pipeline_configs import CameraSegment

from lerobot_conversion.lerobot_features import build_features, build_modality_config
from lerobot_conversion.lerobot_mcap_reader import LeRobotMCAPReader
from lerobot_conversion.lerobot_metadata_generator import LeRobotMetadataGenerator
from lerobot_conversion.lerobot_parquet_writer import LeRobotParquetWriter
from lerobot_conversion.lerobot_utils import get_video_feature_name
from lerobot_conversion.lerobot_video_writer import ENCODE_PIX_FMT, LeRobotVideoWriter
from lerobot_conversion.policy_manifest import load_policy_manifest
from lerobot_conversion.temporal_synchronizer import TemporalSynchronizer
from lerobot_conversion.video_frame_extractor import BGR_CHANNELS, VideoFrameExtractor
from models.compressed_video_info import CompressedVideoInfo
from models.episode_metadata import EpisodeMetadata
from models.extracted_mcap_data import ExtractedMcapData
from models.observation import Observation
from models.topic_statistics import TopicStatistics
from models.video_frame import VideoFrame


@dataclass(frozen=True)
class DatasetSchema:
    """Feature structure that every episode in a dataset must share.

    The contract fixes the observation-state and action layout for every episode, so only the
    encoded video geometry can still differ between them.
    """

    video_infos: dict[str, dict[str, Any]]

    def camera_shapes(self) -> dict[str, tuple[Any, Any, Any]]:
        """Map each camera policy key to its (height, width, channels)."""
        return {
            name: (info.get("video.height"), info.get("video.width"), info.get("video.channels"))
            for name, info in self.video_infos.items()
        }


@dataclass
class ConvertedEpisode:
    """Artifacts produced by converting a single episode."""

    episode_metadata: EpisodeMetadata
    task_definition: dict[str, Any]
    schema: DatasetSchema


class LeRobotConverter:
    """Main converter for transforming MCAP files to LeRobot dataset format."""

    DEFAULT_TASK_NAME = "robot_demonstration"

    def __init__(
        self,
        output_dir: Path,
        policy_contract_path: Path,
        dataset_name: str = "robot_dataset",
        policy_type: str = "gr00t",
        target_fps: float | None = None,
    ) -> None:
        """Initialize LeRobot converter.

        Args:
            output_dir: Output directory for LeRobot dataset
            policy_contract_path: Path to the policy contract YAML file
            dataset_name: Name of the dataset
            policy_type: Policy model the contract targets; gates modality.json generation
            target_fps: Resampling target, defaulting to the contract's policy.control_rate_hz
        """
        self.output_dir: Path = output_dir
        self.dataset_name: str = dataset_name
        self.policy_type: str = policy_type
        # each distinct task gets the next free index, which every frame of its episodes carries
        self.task_definitions: list[dict[str, Any]] = []

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.manifest = load_policy_manifest(policy_contract_path)
        self.contract = self.manifest.contract
        self.target_fps: float = target_fps if target_fps is not None else self.contract.policy.control_rate_hz

        # LeRobot episodes are video-backed: the timebase every other modality is resampled onto comes from a camera
        if not self.contract.cameras:
            raise ValueError(f"Policy contract {policy_contract_path} declares no cameras")
        # Validate the shapes of the contract's cameras before any MCAP is opened
        _validate_camera_shapes(self.contract.cameras)

        logger.info(
            f"Loaded policy contract v{self.contract.version} from {policy_contract_path}: "
            f"{len(self.contract.cameras)} camera(s), state width {self.contract.state_width}, "
            f"action width {self.contract.action_width}"
        )

        # Initialize components
        self.mcap_reader = LeRobotMCAPReader(manifest=self.manifest)
        self.frame_extractor = VideoFrameExtractor(self.target_fps)
        self.synchronizer = TemporalSynchronizer(self.target_fps)
        self.parquet_writer = LeRobotParquetWriter(output_dir, self.contract)
        self.video_writer = LeRobotVideoWriter(output_dir)
        self.metadata_generator = LeRobotMetadataGenerator(output_dir)

        logger.debug(f"LeRobotConverter initialized: {output_dir}")
        logger.debug(f"Target FPS: {self.target_fps}, Dataset: {dataset_name}")

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
            task_index = self._resolve_task_index(task_definition)

            # Step 2: Extract video frames
            videos = {
                policy_key: self._extract_video_frames(
                    policy_key, extracted_data.video_stats[policy_key], compressed_video
                )
                for policy_key, compressed_video in extracted_data.compressed_videos.items()
            }

            # Step 3: Synchronize all modalities
            synchronized_data = self.synchronizer.synchronize_episode_data(videos, extracted_data)

            # Step 4: Write synchronized data to Parquet
            episode_meta = self.parquet_writer.write_episode_data(
                synchronized_data, episode_index, chunk_index, task_index
            )

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
                schema=DatasetSchema(video_infos=video_infos),
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

    def _resolve_task_index(self, task_definition: dict[str, Any]) -> int:
        """Index of this task in tasks.jsonl, registering it the first time it is seen."""
        task = task_definition["task"]
        for known in self.task_definitions:
            if known["task"] == task:
                return int(known["task_index"])
        self.task_definitions.append({**task_definition, "task_index": len(self.task_definitions)})
        return len(self.task_definitions) - 1

    def finalize_dataset(
        self,
        dataset_description: str,
        video_infos: dict[str, dict[str, Any]],
        episode_metadata: list[EpisodeMetadata],
        task_definitions: list[dict[str, Any]],
        additional_info: dict[str, Any] | None = None,
    ) -> dict[str, Path]:
        """Finalize dataset by generating all metadata files.

        Args:
            dataset_description: Human-readable dataset description to embed in metadata
            video_infos: Video metadata per camera policy key (codecs, dimensions, etc.)
            episode_metadata: Episode-level metadata entries
            task_definitions: Task definitions to write to tasks metadata
            additional_info: Optional additional metadata to include

        Returns:
            Dictionary of created metadata file paths.
        """
        logger.info("Finalizing LeRobot dataset...")

        metadata_files = {}

        try:
            # Episodes metadata
            metadata_files["episodes"] = self.metadata_generator.write_episodes_metadata(episode_metadata)

            features = build_features(self.contract, video_infos)

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

            # modality.json is a GR00T-specific input file; other policies read features straight from info.json
            if self.policy_type == "gr00t":
                metadata_files["modality"] = self.metadata_generator.write_modality_metadata(
                    build_modality_config(self.contract).to_dict()
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
        logger.info(f"  Cameras: {list(extracted_data.compressed_videos.keys())}")
        logger.info(f"  State segments: {list(extracted_data.robot_states.keys())}")
        logger.info(f"  Action segments: {list(extracted_data.actions.keys())}")

        return extracted_data

    def _validate_extracted_data(self, extracted_data: ExtractedMcapData) -> None:
        """Reject an episode that cannot fill the vector layout the contract declares.

        A dataset's columns are fixed by the contract, so a segment with no recorded messages
        would silently shorten the flat state/action vectors of every frame.
        """
        missing = {
            "cameras": [key for key in self.manifest.camera_keys if key not in extracted_data.compressed_videos],
            "state": [key for key in self.manifest.state_keys if key not in extracted_data.robot_states],
            "action": [key for key in self.manifest.action_keys if key not in extracted_data.actions],
        }
        reported = [f"{label}: {', '.join(keys)}" for label, keys in missing.items() if keys]
        if reported:
            raise ValueError(
                "Episode is missing data for policy contract segments -> "
                + "; ".join(reported)
                + ". Check that the contract's topics match what data-recorder captured and data-processor encoded."
            )

    def _extract_video_frames(
        self,
        policy_key: str,
        video_stats: TopicStatistics,
        compressed_video: CompressedVideoInfo,
    ) -> list[VideoFrame]:
        """Extract video frames from CompressedVideo data at the camera's declared shape."""
        camera = self.manifest.camera_for(policy_key)
        logger.info(f"Extracting frames from camera: {policy_key} (shape: {camera.shape}, resize: {camera.resize})")

        try:
            return self.frame_extractor.extract_frames(
                compressed_video.data,
                video_stats.first_message_time_ns,
                video_stats.last_message_time_ns - video_stats.first_message_time_ns,
                (camera.height, camera.width),
                camera.resize,
            )
        except ValueError as error:
            # the extractor works on bare video bytes and cannot name the segment that declared them
            raise ValueError(f"Camera {policy_key!r}: {error}") from error

    def _write_video_files(
        self, synchronized_data: list[Observation], episode_index: int, chunk_index: int
    ) -> dict[str, dict[str, Any]]:
        """Encode one target-FPS video per camera from the synchronized frames."""
        if not synchronized_data:
            raise ValueError(f"No synchronized observations to write videos for (episode {episode_index})")

        video_infos = {}
        for policy_key in synchronized_data[0].image:
            feature_name: str = get_video_feature_name(policy_key)
            frames = [observation.image[policy_key].image for observation in synchronized_data]

            video_file: Path = self.video_writer.write_video_from_frames(
                frames, feature_name, episode_index, chunk_index, self.target_fps
            )

            video_info = get_video_info(video_file)
            video_infos[policy_key] = video_info
            _check_camera_geometry(self.manifest.camera_for(policy_key), video_info)

            logger.debug(f"video properties: {json.dumps(video_info)}")
        return video_infos

    def close(self) -> None:
        """Clean up resources."""
        if self.frame_extractor:
            self.frame_extractor.close()

        logger.info("LeRobotConverter closed")


def convert_mcaps_to_lerobot(
    mcap_files: tuple[Path, ...] | list[Path],
    output_dir: Path,
    policy_contract_path: Path,
    dataset_name: str = "robot_dataset",
    policy_type: str = "gr00t",
    target_fps: float | None = None,
) -> dict[str, Any]:
    """Convert one or more MCAP files into a single LeRobot dataset.

    Args:
        mcap_files: Ordered paths to MCAP files (each becomes one episode)
        output_dir: Output directory for the LeRobot dataset
        policy_contract_path: Path to the policy contract YAML file
        dataset_name: Dataset name
        policy_type: Policy model the contract targets; gates modality.json generation
        target_fps: Resampling target, defaulting to the contract's policy.control_rate_hz

    Returns:
        Conversion result dict with episode metadata, metadata files, and dataset dir
    """
    converter = LeRobotConverter(output_dir, policy_contract_path, dataset_name, policy_type, target_fps)

    all_episode_meta: list[EpisodeMetadata] = []
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

        if reference_episode is None:
            raise ValueError("No MCAP files were provided; cannot build a dataset.")

        description = f"Dataset with {len(all_episode_meta)} episode(s) converted from MCAP files"
        metadata_files = converter.finalize_dataset(
            description,
            reference_episode.schema.video_infos,
            all_episode_meta,
            converter.task_definitions,
        )

        return {
            "episode_metadata": all_episode_meta,
            "metadata_files": metadata_files,
            "dataset_dir": output_dir,
        }

    finally:
        converter.close()


def _validate_camera_shapes(cameras: tuple[CameraSegment, ...]) -> None:
    """Reject declared geometry the video path cannot produce."""
    for camera in cameras:
        if camera.channels != BGR_CHANNELS:
            raise ValueError(
                f"Camera {camera.policy_key!r} declares {camera.channels} channels; "
                f"only {BGR_CHANNELS}-channel video is supported"
            )
        # ``yuv420p`` even-dimension requirement
        if camera.height % 2 or camera.width % 2:
            raise ValueError(
                f"Camera {camera.policy_key!r} declares odd shape {camera.width}x{camera.height}; "
                f"{ENCODE_PIX_FMT} requires even width and height"
            )


def _check_camera_geometry(camera: CameraSegment, video_info: dict[str, Any]) -> None:
    """Assert the encoded episode video carries the geometry the policy will be served at."""
    encoded = (video_info["video.height"], video_info["video.width"], video_info["video.channels"])
    if encoded == (camera.height, camera.width, camera.channels):
        return

    raise ValueError(
        f"Camera {camera.policy_key!r} frames were written at {list(camera.shape)} but the encoded "
        f"video is {list(encoded)}"
    )


def _assert_consistent_structure(
    reference: ConvertedEpisode,
    current: ConvertedEpisode,
    episode_index: int,
    mcap_file: Path,
) -> None:
    """Raise error if current episode does not share the reference episode's camera geometry."""
    reference_cameras = reference.schema.camera_shapes()
    current_cameras = current.schema.camera_shapes()
    if reference_cameras == current_cameras:
        return

    raise ValueError(
        f"Episode {episode_index} ({mcap_file}) has a different structure than the first episode "
        f"and cannot be combined into one dataset. Differences -> "
        f"cameras: expected {reference_cameras}, got {current_cameras}"
    )
