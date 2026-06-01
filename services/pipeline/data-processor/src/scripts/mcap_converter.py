"""MCAP Video Converter - Convert Raw Image messages to H.264 CompressedVideo format.

This script converts MCAP files containing individual Raw Image messages to H.264 compressed
video format using Foxglove's CompressedVideo schema for better storage efficiency and
playback performance.

Architecture:
    - MCAPReader: Handle MCAP file reading and message parsing
    - VideoEncoder: Handle video encoding with FFmpeg integration
    - MetadataManager: Handle reversibility metadata creation and storage
    - MCAPWriter: Handle output MCAP writing with metadata
"""

import argparse
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from services.mcap_reader import MCAPReader
from services.mcap_writer import MCAPWriter
from services.metadata_manager import MetadataManager
from services.video_encoder import VideoEncoder


class MCAPConverter:
    """Main converter class that orchestrates the conversion process."""

    def __init__(
        self,
        input_path: Path,
        output_path: Path,
        camera_topics: list[str],
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the MCAP converter.

        Args:
            input_path: Path to input MCAP file
            output_path: Path to output MCAP file
            camera_topics: List of camera topics to convert
            config: Optional configuration dictionary
        """
        self.input_path: Path = input_path
        self.output_path: Path = output_path
        self.camera_topics: list[str] = camera_topics
        self.config: dict[str, Any] = config or {}

        # Initialize services
        self.mcap_reader = MCAPReader(input_path)
        self.video_encoder = VideoEncoder(self.config.get("codec_settings", {}))
        self.metadata_manager = MetadataManager()
        self.mcap_writer = MCAPWriter(output_path)

        logger.info(f"MCAP Converter initialized: {input_path} -> {output_path}")
        logger.info(f"Camera topics to convert: {camera_topics}")

    def convert(self) -> None:
        """Execute the complete conversion process."""
        logger.info("Starting MCAP conversion process...")

        try:
            # Step 1: Read input MCAP and extract Raw Image messages
            logger.info("Reading input MCAP file...")

            # Read original metadata first (before file gets closed)
            original_metadata: dict[str, Any] = self.mcap_reader.read_original_metadata()

            # Then read messages
            image_data, non_image_data = self.mcap_reader.read_messages(self.camera_topics)

            # Step 2: Process each camera topic
            converted_video_data: dict[str, dict[str, Any]] = {}
            for topic in self.camera_topics:
                if topic in image_data:
                    logger.info(f"Processing camera topic: {topic}")
                    frames: list[dict[str, Any]] = image_data[topic]

                    # Encode frames to H.264 video
                    video_data, encoding_metadata = self.video_encoder.encode_frames(frames, topic)

                    # Generate output topic name
                    output_topic: str = self._generate_output_topic_name(topic)
                    converted_video_data[output_topic] = {
                        "video_data": video_data,
                        "metadata": encoding_metadata,
                        "original_topic": topic,
                    }

                    logger.info(f"Converted {topic} -> {output_topic} ({len(frames)} frames)")
                else:
                    logger.warning(f"Camera topic not found in MCAP: {topic}")

            # Step 3: Generate comprehensive metadata for reversibility
            logger.info("Generating reversibility metadata...")
            conversion_metadata: dict[str, Any] = self.metadata_manager.generate_metadata(
                image_data, converted_video_data, self.config
            )

            # Step 4: Write output MCAP with video data and preserved non-image topics
            logger.info("Writing output MCAP file...")
            self.mcap_writer.write_converted_mcap(
                converted_video_data, non_image_data, conversion_metadata, original_metadata
            )

            # Step 5: Validation
            self._validate_conversion(image_data, converted_video_data)

            logger.info(f"Conversion completed successfully: {self.output_path}")

        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            raise
        finally:
            # Cleanup
            self.mcap_reader.close()
            self.video_encoder.close()
            self.mcap_writer.close()

    def _generate_output_topic_name(self, input_topic: str) -> str:
        """Generate output topic name by replacing image suffix with 'compressed_video'.

        Examples:
            /frame_camera/D455/color/image_raw -> /frame_camera/D455/color/compressed_video
            /zed/zed_node/left/image_rect_color -> /zed/zed_node/left/compressed_video
        """
        # Replace common image suffixes with compressed_video
        suffixes_to_replace: list[str] = ["image_raw", "image_rect_raw", "image_rect_color"]

        for suffix in suffixes_to_replace:
            if input_topic.endswith(suffix):
                return input_topic[: -len(suffix)] + "compressed_video"

        # Fallback: append compressed_video
        return input_topic + "/compressed_video"

    def _validate_conversion(self, image_data: dict[str, Any], video_data: dict[str, Any]) -> None:
        """Validate the conversion process."""
        logger.info("Validating conversion...")

        # Frame count verification
        for topic in self.camera_topics:
            if topic in image_data:
                original_frames: int = len(image_data[topic])
                output_topic: str = self._generate_output_topic_name(topic)

                if output_topic in video_data:
                    converted_metadata = video_data[output_topic]["metadata"]
                    converted_frames = converted_metadata.get("total_frames", 0)

                    if original_frames != converted_frames:
                        logger.error(f"Frame count mismatch for {topic}: {original_frames} -> {converted_frames}")
                        raise ValueError(f"Frame count validation failed for {topic}")
                    logger.info(f"Frame count verified for {topic}: {original_frames} frames")


def load_config(config_path: Path) -> dict[str, Any]:
    """Load configuration from YAML file."""
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with config_path.open() as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        raise ValueError(f"Invalid configuration format in {config_path}")

    logger.info(f"Loaded configuration from {config_path}")
    return config


def main() -> None:
    """Main entry point for the MCAP converter."""
    parser = argparse.ArgumentParser(
        description="Convert MCAP files from Raw Image messages to H.264 CompressedVideo format"
    )
    parser.add_argument("--input", type=Path, required=True, help="Input MCAP file path")
    parser.add_argument("--output", type=Path, required=True, help="Output MCAP file path")
    parser.add_argument("--camera-topics", nargs="+", required=True, help="List of camera topics to convert")
    parser.add_argument("--config", type=Path, help="Configuration file path (YAML format)")

    args: argparse.Namespace = parser.parse_args()

    # Configure logging
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=""),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        level="INFO",
    )

    # Load configuration if provided
    config: dict[str, Any] = {}
    if args.config:
        config = load_config(args.config)
        # Override camera topics from config if not provided via CLI
        if "camera_topics" in config and not args.camera_topics:
            args.camera_topics = config["camera_topics"]

    # Validate inputs
    if not args.input.exists():
        logger.error(f"Input MCAP file not found: {args.input}")
        return

    # Create output directory if it doesn't exist
    args.output.parent.mkdir(parents=True, exist_ok=True)

    # Initialize and run converter
    converter = MCAPConverter(args.input, args.output, args.camera_topics, config)
    converter.convert()


if __name__ == "__main__":
    main()
