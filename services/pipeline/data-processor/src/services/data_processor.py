"""DataProcessor class for converting MCAP episodes from raw to compressed video format."""

import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import uuid7  # type: ignore[import-untyped]
from loguru import logger

from configs.data_collection import DataCollectionConfig, load_data_collection_config
from configs.data_processor import DataProcessorConfig, load_data_processor_config
from models.episode import (
    ConversionMetadata,
    EpisodeProcessed,
    EpisodeResponse,
    EpisodeStatus,
)
from repos.data_collection import DataCollectionRepo
from services.mcap_reader import MCAPReader
from services.mcap_writer import MCAPWriter
from services.metadata_manager import MetadataManager
from services.video_encoder import VideoEncoder


class DataProcessor:
    """Processor class for converting MCAP episodes from raw to compressed video format."""

    def __init__(self) -> None:
        """Initialize DataProcessor with configurations and repositories."""
        # Load configurations
        self.config: DataProcessorConfig = load_data_processor_config()
        self.data_collection_config: DataCollectionConfig = load_data_collection_config()

        # Initialize repositories
        self.data_collection_repo = DataCollectionRepo(self.data_collection_config)

        # Processing state
        self.running = False

        # Initialize directories
        raw_path = Path(self.config.raw_data_path)
        raw_path.mkdir(parents=True, exist_ok=True)
        processed_path = Path(self.config.processed_data_path)
        processed_path.mkdir(parents=True, exist_ok=True)

        logger.info("DataProcessor initialized")
        logger.info(
            "Processing poll interval: {}s, Episode limit: {}",
            self.config.poll_interval_seconds,
            self.config.episode_limit_per_poll,
        )
        logger.info(
            "Raw data path: {}, Processed data path: {}", self.config.raw_data_path, self.config.processed_data_path
        )

    def start(self) -> None:
        """Start the main processing loop."""
        self.running = True
        logger.info("Starting DataProcessor main loop")

        while self.running:
            try:
                self._process_episodes()
                logger.debug("Waiting {} seconds before next poll", self.config.poll_interval_seconds)
                time.sleep(self.config.poll_interval_seconds)
            except KeyboardInterrupt:
                logger.info("Received interrupt signal, stopping DataProcessor")
                break
            except Exception as e:
                logger.error("Unexpected error in main loop: {}", e)
                time.sleep(self.config.poll_interval_seconds)

        self.running = False

        logger.info("DataProcessor stopped")

    def stop(self) -> None:
        """Stop the processing loop."""
        self.running = False
        logger.info("DataProcessor stop requested")

    def _process_episodes(self) -> None:
        """Main episode processing workflow."""
        # Step 1: Check data-collection service availability
        data_collection_available: bool = self.data_collection_repo.health_check()
        if not data_collection_available:
            logger.warning("Data-collection service unavailable, skipping episode processing")
            return

        # Step 2: Get episodes to process (not yet processed)
        try:
            unprocessed: list[EpisodeResponse] = self.data_collection_repo.get_episodes(
                status=EpisodeStatus.SAVED,
                processed=EpisodeProcessed.DEFAULT,
                limit=self.config.episode_limit_per_poll,
            )

            if not unprocessed:
                logger.debug("No episodes found for processing")
                return

            logger.info("Found {} unprocessed episodes", len(unprocessed))

        except Exception as e:
            logger.error("Failed to retrieve episodes: {}", e)
            return

        # Step 3: Process episodes sequentially
        for episode in unprocessed:
            try:
                self._process_single_episode(episode)
            except Exception as e:
                logger.error(
                    "Failed to process episode {}: {} (type: {}, raw_path: {})",
                    episode.episode_id,
                    e,
                    type(e).__name__,
                    f"{self.config.raw_data_path}/.../.../{episode.episode_id}",
                )
                # Update episode status to ERROR
                try:
                    self.data_collection_repo.patch_episode(
                        episode.episode_id,
                        processed=EpisodeProcessed.ERROR,
                        message=f"Processing failed: {e!s}",
                    )
                except Exception as patch_error:
                    logger.error("Failed to update episode {} status to ERROR: {}", episode.episode_id, patch_error)

    def _process_single_episode(self, episode: EpisodeResponse) -> None:
        """Process a single episode through conversion workflow.

        Args:
            episode: Episode to process
        """
        episode_id: UUID = episode.episode_id
        logger.info("Processing episode: {}", episode_id)

        # Step 1: Validation
        dt: datetime = uuid7.time(episode_id)
        raw_episode_dir: Path = Path(
            f"{self.config.raw_data_path}/{dt.strftime('%Y')}/{dt.strftime('%m')}/{dt.strftime('%d')}/{episode_id}"
        )
        raw_mcap_file: Path = raw_episode_dir / "mcap" / "mcap_0.mcap"

        if not raw_episode_dir.exists():
            raise ValueError(f"Episode directory not found: {raw_episode_dir}")
        if not raw_mcap_file.exists():
            raise ValueError(f"MCAP file not found: {raw_mcap_file}")

        # Step 2: Setup output directory
        processed_episode_dir: Path = Path(
            f"{self.config.processed_data_path}/{dt.strftime('%Y')}/{dt.strftime('%m')}/{dt.strftime('%d')}/{episode_id}"
        )

        if processed_episode_dir.exists():
            logger.warning("Processed directory already exists, cleaning up: {}", processed_episode_dir)
            shutil.rmtree(processed_episode_dir)

        processed_episode_dir.mkdir(parents=True, exist_ok=True)
        (processed_episode_dir / "mcap").mkdir(exist_ok=True)
        (processed_episode_dir / "logs").mkdir(exist_ok=True)

        # Step 3: MCAP Conversion
        conversion_metadata: ConversionMetadata = self._convert_mcap(
            raw_mcap_file,
            processed_episode_dir,
            self._build_episode_context(episode),
        )

        # Check if conversion had errors
        if hasattr(conversion_metadata, "error_message") and conversion_metadata.error_message:
            raise ValueError(f"MCAP conversion failed: {conversion_metadata.error_message}")

        # Step 4: Copy metadata files
        self._copy_metadata_files(raw_episode_dir, processed_episode_dir)

        # Step 5: Save conversion metadata
        self._save_conversion_metadata(processed_episode_dir, conversion_metadata)

        # Step 6: Validate output files before marking as SUCCESS
        if not self._validate_output_files(processed_episode_dir, conversion_metadata):
            raise ValueError("Output file validation failed - processed files are invalid or missing")

        # Step 7: Mark processed SUCCESS (conversion completed)
        try:
            self.data_collection_repo.patch_episode(
                episode_id,
                processed=EpisodeProcessed.SUCCESS,
                message="Conversion completed successfully",
            )
        except Exception as e:
            logger.warning("Failed to patch episode {} processed status: {}", episode_id, e)

        # Step 7a: Write completion marker file for data shipper
        # Note: episode_metadata.json is already copied from raw directory in step 4
        try:
            completion_marker: Path = processed_episode_dir / ".processing_complete"
            completion_marker.touch()
            logger.debug("Created processing completion marker for data shipper")
        except Exception as e:
            logger.warning("Failed to create completion marker: {}", e)

        # Step 8: Delete raw data if configured (keep processed for DataShipper)
        if self.config.delete_raw_episode:
            try:
                self._delete_raw_episode(episode_id, raw_episode_dir)
            except Exception as e:
                logger.warning("Failed to delete raw directory for episode {}: {}", episode_id, e)

        logger.info("Episode {} processing completed", episode_id)

    def _convert_mcap(  # noqa: C901, PLR0912, PLR0915
        self,
        input_mcap: Path,
        output_dir: Path,
        episode_context: dict[str, Any] | None = None,
    ) -> ConversionMetadata:
        """Convert MCAP file with AV1 encoding.

        Args:
            input_mcap: Input MCAP file path
            output_dir: Output directory for converted MCAP
            episode_context: Optional episode/task provenance metadata

        Returns:
            ConversionMetadata with conversion details
        """
        start_time: datetime = datetime.now()
        discovered_topics: list[str] = []
        output_mcap: Path = output_dir / "mcap" / "mcap_0.mcap"

        logger.info("Starting MCAP conversion: {} -> {}", input_mcap, output_mcap)

        # Prepare AV1 settings from config
        av1_settings: dict[str, Any] = {
            "codec": "libsvtav1",
            "preset": self.config.av1_preset,
            "gop_size": self.config.av1_gop_size,
            "pixel_format": self.config.av1_pixel_format,
            "threads": self.config.av1_threads,
        }

        mcap_reader = None
        video_encoder = None
        metadata_manager = None
        mcap_writer = None

        try:
            # Initialize services
            mcap_reader = MCAPReader(input_mcap)
            video_encoder = VideoEncoder(av1_settings)
            metadata_manager = MetadataManager()
            mcap_writer = MCAPWriter(output_mcap)

            # Read original metadata and discover camera topics from the MCAP
            original_metadata: dict[str, Any] = mcap_reader.read_original_metadata()
            discovered_topics = mcap_reader.discover_image_topics()
            if discovered_topics:
                logger.info("Discovered camera topics from MCAP: {}", discovered_topics)
                image_data, non_image_data = mcap_reader.read_messages(discovered_topics)
            else:
                # No topics discovered in the MCAP — proceed with empty image set
                logger.warning("No camera topics discovered in MCAP; skipping image conversion")
                image_data, non_image_data = mcap_reader.read_messages([])

            # Process each camera topic
            converted_video_data: dict[str, dict[str, Any]] = {}
            total_frame_count = 0

            # Iterate over the topics discovered in this MCAP
            used_topics: list[str] = discovered_topics or []
            for topic in used_topics:
                if topic in image_data:
                    frames: list[dict[str, Any]] = image_data[topic]
                    if not frames:
                        # No frames captured for this topic — skip encoding but keep processing others.
                        logger.warning("No frames provided for topic {}, skipping encoding", topic)
                        continue

                    logger.info("Converting camera topic: {}", topic)
                    total_frame_count += len(frames)

                    # Encode frames to AV1
                    video_data, encoding_metadata = video_encoder.encode_frames(frames, topic)

                    # Generate output topic name
                    output_topic: str = self._generate_output_topic_name(topic)
                    converted_video_data[output_topic] = {
                        "video_data": video_data,
                        "metadata": encoding_metadata,
                        "original_topic": topic,
                    }

                    logger.info("Converted {} frames: {} -> {}", len(frames), topic, output_topic)

            # Generate comprehensive metadata for reversibility
            logger.info("Generating reversibility metadata...")
            conversion_config = {"codec_settings": av1_settings}
            comprehensive_metadata: dict[str, Any] = metadata_manager.generate_metadata(
                image_data,
                converted_video_data,
                conversion_config,
                episode_context=episode_context,
            )

            # Write output MCAP with comprehensive metadata
            mcap_writer.write_converted_mcap(
                converted_video_data, non_image_data, comprehensive_metadata, original_metadata
            )

        except Exception as e:
            logger.error("MCAP conversion failed: {}", e)
            raise
        finally:
            # Ensure cleanup happens even on exceptions
            if mcap_reader is not None:
                try:
                    mcap_reader.close()
                except Exception as cleanup_error:
                    logger.warning("Error closing MCAP reader: {}", cleanup_error)

            if video_encoder is not None:
                try:
                    video_encoder.close()
                except Exception as cleanup_error:
                    logger.warning("Error closing video encoder: {}", cleanup_error)

            if mcap_writer is not None:
                try:
                    mcap_writer.close()
                except Exception as cleanup_error:
                    logger.warning("Error closing MCAP writer: {}", cleanup_error)

        end_time: datetime = datetime.now()
        conversion_duration: float = (end_time - start_time).total_seconds()

        # Calculate file sizes and compression ratio
        original_size: int = input_mcap.stat().st_size
        compressed_size: int = output_mcap.stat().st_size if output_mcap.exists() else 0
        compression_ratio = original_size / compressed_size if compressed_size > 0 else 0

        logger.info(
            "MCAP conversion completed: {:.2f}s, {:.1f}MB -> {:.1f}MB (ratio: {:.2f}x)",
            conversion_duration,
            original_size / 1024 / 1024,
            compressed_size / 1024 / 1024,
            compression_ratio,
        )

        return ConversionMetadata(
            input_file=str(input_mcap),
            output_file=str(output_mcap),
            camera_topics=used_topics,
            av1_settings=av1_settings,
            conversion_start_time=start_time,
            conversion_end_time=end_time,
            conversion_duration_seconds=conversion_duration,
            original_size_bytes=original_size,
            compressed_size_bytes=compressed_size,
            compression_ratio=compression_ratio,
            frame_count=total_frame_count,
            codec_used="libsvtav1",
        )

    def _generate_output_topic_name(self, input_topic: str) -> str:
        """Generate output topic name by replacing image suffix with 'compressed_video'.

        Args:
            input_topic: Original image topic name

        Returns:
            Output topic name for compressed video
        """
        suffixes_to_replace: list[str] = ["image_raw", "image_rect_raw", "image_rect_color"]

        for suffix in suffixes_to_replace:
            if input_topic.endswith(suffix):
                return input_topic[: -len(suffix)] + "compressed_video"

        # Fallback: append compressed_video
        return input_topic + "/compressed_video"

    def _build_episode_context(self, episode: EpisodeResponse) -> dict[str, Any]:
        """Build stable episode/task provenance metadata for embedding in the MCAP."""
        return {
            "episode_id": str(episode.episode_id),
            "task_id": str(episode.task_id),
            "task_name": episode.task_name,
            "task_description": episode.task_description,
            "task_version": episode.task_version,
            "task_language_instructions": episode.task_language_instructions,
            "task_metadata": episode.task_metadata,
            "station_id": episode.station_id,
        }

    def _copy_metadata_files(self, raw_dir: Path, processed_dir: Path) -> None:
        """Copy metadata files from raw to processed directory.

        Args:
            raw_dir: Raw episode directory
            processed_dir: Processed episode directory
        """
        # Copy MCAP metadata.yaml
        raw_mcap_metadata: Path = raw_dir / "mcap" / "metadata.yaml"
        if raw_mcap_metadata.exists():
            shutil.copy2(raw_mcap_metadata, processed_dir / "mcap" / "metadata.yaml")
            logger.debug("Copied MCAP metadata.yaml")

        # Copy all other top-level YAML files from the raw directory to processed directory
        for yaml_file in raw_dir.glob("*.yaml"):
            try:
                shutil.copy2(yaml_file, processed_dir / yaml_file.name)
                logger.debug("Copied top-level YAML file: {}", yaml_file.name)
            except Exception as e:
                logger.warning("Failed to copy YAML file {}: {}", yaml_file, e)

        # Copy all other top-level JSON files from the raw directory to processed directory
        for json_file in raw_dir.glob("*.json"):
            try:
                shutil.copy2(json_file, processed_dir / json_file.name)
                logger.debug("Copied top-level JSON file: {}", json_file.name)
            except Exception as e:
                logger.warning("Failed to copy JSON file {}: {}", json_file, e)

    # Checksum generation and saving removed per configuration: don't calculate or persist checksums

    def _save_conversion_metadata(self, processed_dir: Path, metadata: ConversionMetadata) -> None:
        """Save conversion metadata to JSON file.

        Args:
            processed_dir: Processed episode directory
            metadata: Conversion metadata
        """
        metadata_file: Path = processed_dir / "conversion_metadata.json"

        with metadata_file.open("w") as f:
            json.dump(metadata.model_dump(), f, indent=2, default=str)

        logger.debug("Saved conversion metadata")

    def _validate_output_files(self, processed_dir: Path, metadata: ConversionMetadata) -> bool:  # noqa: PLR0911
        """Validate that output files were created and are valid.

        Args:
            processed_dir: Processed episode directory
            metadata: Conversion metadata

        Returns:
            True if validation passes, False otherwise
        """
        try:
            # Check if output MCAP file exists and has reasonable size
            output_mcap: Path = Path(metadata.output_file)
            if not output_mcap.exists():
                logger.error("Output MCAP file does not exist: {}", output_mcap)
                return False

            if output_mcap.stat().st_size == 0:
                logger.error("Output MCAP file is empty: {}", output_mcap)
                return False

            # Check if conversion metadata file exists
            metadata_file: Path = processed_dir / "conversion_metadata.json"
            if not metadata_file.exists():
                logger.error("Conversion metadata file missing: {}", metadata_file)
                return False

            # If there was an error in metadata, fail validation
            if hasattr(metadata, "error_message") and metadata.error_message:
                logger.error("Conversion metadata contains error: {}", metadata.error_message)
                return False

            # Basic sanity checks on metadata
            if metadata.compressed_size_bytes == 0 and metadata.original_size_bytes > 0:
                logger.error("Output file size is zero but input was not empty")
                return False

            logger.debug("Output file validation passed for {}", processed_dir)
            return True

        except Exception as e:
            logger.error("Error during output file validation: {}", e)
            return False

    def _delete_raw_episode(self, episode_id: UUID, raw_dir: Path) -> None:
        """Delete raw episode directory.

        Args:
            episode_id: Episode UUID for logging
            raw_dir: Path to raw episode directory
        """
        if raw_dir.exists():
            try:
                raw_size: int = sum(f.stat().st_size for f in raw_dir.rglob("*") if f.is_file())
                shutil.rmtree(raw_dir)
                logger.info("Deleted raw directory for episode {}: {:.2f}MB", episode_id, raw_size / 1024 / 1024)
            except Exception as e:
                logger.warning("Failed to delete raw directory {}: {}", raw_dir, e)
