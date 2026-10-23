"""LeRobot Dataset Converter for MCAP CompressedVideo files.

Conversion pipeline (in order):
  1. Read MCAP  — extract the cameras, state and action segments the policy contract declares.
  2. Decode frames — decompress each video stream into per-frame images at the camera's declared
     shape via VideoFrameExtractor, scaling to it where the contract enables resize.
  3. Synchronize — resample all modalities to a common target-FPS grid via TemporalSynchronizer.
  4. Record — hand each synchronized frame to LeRobot's v3.0 dataset writer, which encodes the videos,
     packs episodes into shared data/video files and computes the per-episode stats.
  5. Finalize — close the writer, then add GR00T's meta/modality.json from the contract.
"""

import json
from pathlib import Path
from typing import Any

from lerobot.configs.video import RGBEncoderConfig  # type: ignore[import-untyped]
from lerobot.datasets.lerobot_dataset import LeRobotDataset  # type: ignore[import-untyped]
from loguru import logger
from pipeline_configs import CameraSegment

from lerobot_conversion.lerobot_features import build_features, build_modality_config
from lerobot_conversion.lerobot_frames import LeRobotFrameBuilder
from lerobot_conversion.lerobot_mcap_reader import LeRobotMCAPReader
from lerobot_conversion.policy_manifest import load_policy_manifest
from lerobot_conversion.temporal_synchronizer import TemporalSynchronizer
from lerobot_conversion.video_frame_extractor import RGB_CHANNELS, VideoFrameExtractor
from models.compressed_video_info import CompressedVideoInfo
from models.dataset_build_request import DatasetBuildRequest
from models.episode_metadata import EpisodeMetadata
from models.extracted_mcap_data import ExtractedMcapData
from models.observation import Observation
from models.topic_statistics import TopicStatistics
from models.video_frame import VideoFrame

ENCODE_PIX_FMT = "yuv420p"
# LeRobot stages each frame as a PNG before encoding; writing them off-thread keeps add_frame off the disk
IMAGE_WRITER_THREADS_PER_CAMERA = 4


def _video_encoder() -> RGBEncoderConfig:
    """Encoder settings mirroring data-processor's VideoEncoder, except GOP=2 for LeRobot's random frame access."""
    return RGBEncoderConfig(vcodec="libsvtav1", pix_fmt=ENCODE_PIX_FMT, g=2, crf=30, preset=8)


class LeRobotConverter:
    """Main converter for transforming MCAP files to LeRobot dataset format."""

    DEFAULT_TASK_NAME = "robot_demonstration"

    def __init__(
        self,
        output_dir: Path,
        policy_contract_path: Path,
        dataset_name: str = "robot_dataset",
        policy_type: str = "gr00t",
        target_fps: int | None = None,
    ) -> None:
        """Initialize LeRobot converter.

        Args:
            output_dir: Output directory for the LeRobot dataset; must not exist yet
            policy_contract_path: Path to the policy contract YAML file
            dataset_name: Name of the dataset
            policy_type: Policy model the contract targets; gates modality.json generation
            target_fps: Resampling target, defaulting to the contract's policy.control_rate_hz
        """
        self.output_dir: Path = output_dir
        self.dataset_name: str = dataset_name
        self.policy_type: str = policy_type

        self.manifest = load_policy_manifest(policy_contract_path)
        self.contract = self.manifest.contract
        self.target_fps = target_fps if target_fps is not None else self.contract.policy.control_rate_hz

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

        self.mcap_reader = LeRobotMCAPReader(manifest=self.manifest)
        self.frame_extractor = VideoFrameExtractor(self.target_fps)
        self.synchronizer = TemporalSynchronizer(self.target_fps)
        self.frame_builder = LeRobotFrameBuilder(self.contract)
        # created last: it claims output_dir, which a failed validation above must leave untouched
        self.dataset = LeRobotDataset.create(
            repo_id=dataset_name,
            fps=self.target_fps,
            features={name: feature.to_dict() for name, feature in build_features(self.contract).items()},
            root=output_dir,
            use_videos=True,
            rgb_encoder=_video_encoder(),
            image_writer_threads=IMAGE_WRITER_THREADS_PER_CAMERA * len(self.contract.cameras),
        )

        logger.debug(f"LeRobotConverter initialized: {output_dir}")
        logger.debug(f"Target FPS: {self.target_fps}, Dataset: {dataset_name}")

    def convert_episode(self, mcap_file: Path) -> EpisodeMetadata:
        """Convert a single MCAP file into the next episode of the dataset.

        Does **not** finalize the dataset — call `finalize_dataset` once after
        all episodes have been converted.

        Args:
            mcap_file: Path to input MCAP file.

        Returns:
            The recorded episode's metadata.
        """
        episode_index = self.dataset.meta.total_episodes
        logger.info(f"Converting episode {episode_index}: {mcap_file}")

        if not mcap_file.exists():
            raise FileNotFoundError(f"MCAP file not found: {mcap_file}")

        try:
            # Step 1: Extract data from MCAP
            extracted_data = self._extract_mcap_data(mcap_file)
            self._validate_extracted_data(extracted_data)
            task = self._load_task(extracted_data.metadata)

            # Step 2: Extract video frames
            videos = {
                policy_key: self._extract_video_frames(
                    policy_key, extracted_data.video_stats[policy_key], compressed_video
                )
                for policy_key, compressed_video in extracted_data.compressed_videos.items()
            }

            # Step 3: Synchronize all modalities
            synchronized_data = self.synchronizer.synchronize_episode_data(videos, extracted_data)

            # Step 4: Record the episode
            self.record_episode(synchronized_data, task)

            logger.info(f"Episode {episode_index} converted successfully")
            logger.info(f"Generated {len(synchronized_data)} synchronized observations")

            return EpisodeMetadata(
                episode_index=episode_index,
                frame_count=len(synchronized_data),
                duration_seconds=(synchronized_data[-1].timestamp_ns - synchronized_data[0].timestamp_ns) / 1e9,
                start_timestamp_ns=synchronized_data[0].timestamp_ns,
                end_timestamp_ns=synchronized_data[-1].timestamp_ns,
                tasks=[task],
                mcap_file=str(mcap_file),
                sync_stats=self.synchronizer.calculate_synchronization_stats(synchronized_data),
            )

        except Exception as e:
            # Try to get the episode UUID for logging purposes; fall back to the full path otherwise.
            episode_info = mcap_file.parent.parent.name if mcap_file.parent.name == "mcap" else str(mcap_file)
            logger.error(f"Failed to convert episode {episode_index} ({episode_info}): {e}")
            raise

    def record_episode(self, observations: list[Observation], task: str) -> None:
        """Write synchronized observations as the dataset's next episode.

        Args:
            observations: Synchronized observations in timeline order, one per frame
            task: The episode's task description
        """
        if not observations:
            raise ValueError(f"No synchronized observations to record (episode {self.dataset.meta.total_episodes})")

        task_index = self._resolve_task_index(task)
        last_frame = len(observations) - 1
        for frame_index, observation in enumerate(observations):
            self.dataset.add_frame(
                self.frame_builder.build(
                    observation, is_last_frame=frame_index == last_frame, task=task, task_index=task_index
                )
            )
        # serial: a process pool would fork() past the image-writer threads; libsvtav1 threads each encode anyway
        self.dataset.save_episode(parallel_encoding=False)

        # annotations copy task_index into their own column, so it must be the index LeRobot recorded
        recorded_index = self.dataset.meta.get_task_index(task)
        if recorded_index != task_index:
            raise RuntimeError(f"LeRobot indexed task {task!r} as {recorded_index}, but its frames carry {task_index}")

    def _load_task(self, metadata: dict[str, Any]) -> str:
        """Load the episode's task description from MCAP metadata when available."""
        episode_context = metadata.get("episode_context")
        if not isinstance(episode_context, dict):
            return self.DEFAULT_TASK_NAME

        serialized_context = episode_context.get("data")
        if not isinstance(serialized_context, str):
            return self.DEFAULT_TASK_NAME

        try:
            decoded_context = json.loads(serialized_context)
        except json.JSONDecodeError as exc:
            logger.warning(f"Failed to decode episode_context metadata: {exc}")
            return self.DEFAULT_TASK_NAME

        task_description = decoded_context.get("task_description")
        if isinstance(task_description, str) and task_description.strip():
            return task_description.strip()

        return self.DEFAULT_TASK_NAME

    def _resolve_task_index(self, task: str) -> int:
        """Index LeRobot gives this task in meta/tasks.parquet: its existing one, else the next free one."""
        tasks = self.dataset.meta.tasks
        if tasks is None:
            return 0
        if task in tasks.index:
            return int(tasks.loc[task].task_index)
        return len(tasks)

    def finalize_dataset(self) -> dict[str, Path]:
        """Close the dataset writer and add the contract-derived metadata LeRobot does not write.

        Returns:
            Dictionary of the dataset's metadata file paths.
        """
        logger.info("Finalizing LeRobot dataset...")

        self.dataset.finalize()
        for camera in self.contract.cameras:
            _check_camera_geometry(camera, self.dataset.meta.features[camera.dataset_feature_name].get("info", {}))

        meta_dir = self.output_dir / "meta"
        metadata_files = {
            "info": meta_dir / "info.json",
            "stats": meta_dir / "stats.json",
            "tasks": meta_dir / "tasks.parquet",
            "episodes": meta_dir / "episodes",
        }
        # modality.json is a GR00T-specific input file; other policies read features straight from info.json
        if self.policy_type == "gr00t":
            metadata_files["modality"] = meta_dir / "modality.json"
            metadata_files["modality"].write_text(json.dumps(build_modality_config(self.contract).to_dict(), indent=2))

        logger.info(
            f"Dataset finalized: {self.dataset.meta.total_episodes} episode(s), "
            f"{self.dataset.meta.total_frames} frame(s)"
        )
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
            "cameras": [key for key in self.contract.camera_keys if key not in extracted_data.compressed_videos],
            "state": [key for key in self.contract.state_keys if key not in extracted_data.robot_states],
            "action": [key for key in self.contract.action_keys if key not in extracted_data.actions],
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

    def close(self) -> None:
        """Clean up resources."""
        try:
            self.frame_extractor.close()
        finally:
            # idempotent; on a failed build it still stops the image-writer threads
            self.dataset.finalize()

        logger.info("LeRobotConverter closed")


def convert_mcaps_to_lerobot(request: DatasetBuildRequest) -> dict[str, Any]:
    """Convert one or more MCAP files into a single LeRobot dataset.

    Args:
        request: Build input; each MCAP file becomes one episode, in order, and the output directory must not exist yet

    Returns:
        Conversion result dict with episode metadata, metadata files, and dataset dir
    """
    if not request.mcap_files:
        raise ValueError("No MCAP files were provided; cannot build a dataset.")

    converter = LeRobotConverter(
        request.output_dir,
        request.policy_contract_path,
        request.dataset_name,
        request.policy_type,
        request.target_fps,
    )

    try:
        episode_metadata = [converter.convert_episode(Path(mcap_file)) for mcap_file in request.mcap_files]
        metadata_files = converter.finalize_dataset()
    finally:
        # a cleanup failure must neither replace a conversion error nor fail an already finalized dataset
        try:
            converter.close()
        except Exception:
            logger.exception("Failed to close the converter")

    return {
        "episode_metadata": episode_metadata,
        "metadata_files": metadata_files,
        "dataset_dir": request.output_dir,
    }


def _validate_camera_shapes(cameras: tuple[CameraSegment, ...]) -> None:
    """Reject declared geometry the video path cannot produce."""
    for camera in cameras:
        if camera.channels != RGB_CHANNELS:
            raise ValueError(
                f"Camera {camera.policy_key!r} declares {camera.channels} channels; "
                f"only {RGB_CHANNELS}-channel video is supported"
            )
        # ``yuv420p`` even-dimension requirement
        if camera.height % 2 or camera.width % 2:
            raise ValueError(
                f"Camera {camera.policy_key!r} declares odd shape {camera.width}x{camera.height}; "
                f"{ENCODE_PIX_FMT} requires even width and height"
            )


def _check_camera_geometry(camera: CameraSegment, video_info: dict[str, Any]) -> None:
    """Assert the encoded episode video carries the geometry the policy will be served at."""
    encoded = (video_info.get("video.height"), video_info.get("video.width"), video_info.get("video.channels"))
    if encoded == (camera.height, camera.width, camera.channels):
        return

    raise ValueError(
        f"Camera {camera.policy_key!r} frames were written at {list(camera.shape)} but the encoded "
        f"video is {list(encoded)}"
    )
