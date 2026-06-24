#!/usr/bin/env python3
"""MCAP Video Extractor - Extract MP4 videos and display metadata from converted MCAP files."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import ffmpeg  # type: ignore[import-untyped]
import mcap.reader
from loguru import logger
from mcap_ros2.decoder import DecoderFactory


class MCAPVideoExtractor:
    """Extract MP4 videos and metadata from converted MCAP files."""

    def __init__(self, mcap_path: Path, output_dir: Path | None = None) -> None:
        """Initialize the MCAP video extractor.

        Args:
            mcap_path: Path to the converted MCAP file
            output_dir: Output directory for extracted videos (defaults to same directory as MCAP)
        """
        self.mcap_path: Path = mcap_path
        self.output_dir: Path = output_dir or mcap_path.parent
        self.reader: mcap.reader.McapReader | None = None

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info("MCAP Video Extractor initialized")
        logger.info(f"Input MCAP: {mcap_path}")
        logger.info(f"Output directory: {self.output_dir}")

    def extract_videos_and_metadata(self) -> dict[str, Any]:
        """Extract all CompressedVideo topics as MP4 files and return metadata.

        Returns:
            Dictionary containing all metadata from the MCAP file
        """
        logger.info("Starting video extraction and metadata parsing...")

        all_metadata = {}
        video_topics = []

        try:
            with open(self.mcap_path, "rb") as f:
                # Use default reader - Foxglove messages should be decodable by default
                self.reader = mcap.reader.make_reader(f)

                # First, extract all metadata
                logger.info("Reading MCAP metadata...")
                for metadata in self.reader.iter_metadata():
                    logger.info(f"Found metadata: {metadata.name}")
                    try:
                        # Parse the JSON data from the metadata
                        metadata_dict = json.loads(metadata.metadata["data"])
                        all_metadata[metadata.name] = metadata_dict
                    except Exception as e:
                        logger.warning(f"Failed to parse metadata {metadata.name}: {e}")
                        all_metadata[metadata.name] = {"raw_data": metadata.metadata}

                # Then, find and extract video topics
                logger.info("Searching for CompressedVideo topics...")
                message_count = 0

                # Use raw message iteration to avoid decoder issues with non-video topics
                for schema, channel, message in self.reader.iter_messages():
                    message_count += 1

                    if message_count % 10000 == 0:
                        logger.debug(f"Processed {message_count} messages...")

                    # Check if this is a CompressedVideo topic
                    if schema and schema.name == "foxglove.CompressedVideo":
                        topic_name: str = channel.topic
                        logger.info(f"Found CompressedVideo topic: {topic_name}")

                        if topic_name not in video_topics:
                            video_topics.append(topic_name)

                            # Decode the CompressedVideo message using protobuf
                            try:
                                # Parse CompressedVideo protobuf message
                                video_data, video_format, frame_id, timestamp_info = self._decode_compressed_video(
                                    message.data
                                )

                                logger.info(f"Extracting video: {topic_name}")
                                logger.info(f"  Format: {video_format}")
                                logger.info(f"  Data size: {len(video_data)} bytes")
                                logger.info(f"  Frame ID: {frame_id}")
                                logger.info(f"  Timestamp info: {timestamp_info}")

                                # Generate output filename
                                safe_topic_name = topic_name.replace("/", "_").strip("_")
                                output_file = self.output_dir / f"{safe_topic_name}.mp4"

                                # Convert video data to MP4 using FFmpeg
                                self._convert_to_mp4(video_data, output_file, video_format)

                            except Exception as e:
                                logger.error(f"Failed to extract video from message: {e}")
                                logger.exception("Full error details:")
                                continue

                logger.info(f"Processed {message_count} total messages")
                logger.info(f"Found {len(video_topics)} video topics: {video_topics}")

        except Exception as e:
            logger.error(f"Failed to extract videos: {e}")
            raise

        return all_metadata

    def _decode_compressed_video(self, message_data: bytes) -> tuple[bytes, str, str, str]:  # noqa: C901, PLR0912, PLR0915
        """Decode CompressedVideo protobuf message.

        Args:
            message_data: Raw protobuf message bytes

        Returns:
            Tuple of (video_data, video_format, frame_id, timestamp_info)
        """
        # For now, use a simple approach - manually parse the protobuf
        # The CompressedVideo message structure (based on Foxglove schema):
        # - timestamp (nested message)
        # - frame_id (string)
        # - data (bytes)
        # - format (string)

        # This is a simplified decoder - in production you'd want to use proper protobuf parsing
        try:
            wire_type_varint = 0
            wire_type_fixed64 = 1
            wire_type_length_delimited = 2
            wire_type_fixed32 = 5
            max_string_field_len = 100

            # Try to find the data field which should contain the video bytes (H.264 or AV1)
            # Protobuf uses varint encoding, so we need to parse carefully

            # For now, let's use a heuristic approach:
            # Look for a large bytes field that likely contains the video data
            pos = 0
            video_data = b""
            video_format = "h264"  # Default, will be detected from protobuf if available
            frame_id = ""
            timestamp_info = "unknown"

            while pos < len(message_data):
                try:
                    # Simple protobuf parsing - look for wire type 2 (length-delimited)
                    if pos >= len(message_data):
                        break

                    tag_byte = message_data[pos]
                    pos += 1

                    wire_type = tag_byte & 0x07

                    if wire_type == wire_type_length_delimited:  # Length-delimited (string, bytes, nested messages)
                        # Read length
                        length = 0
                        shift = 0
                        while pos < len(message_data):
                            byte = message_data[pos]
                            pos += 1
                            length |= (byte & 0x7F) << shift
                            if (byte & 0x80) == 0:
                                break
                            shift += 7

                        # Read data
                        if pos + length <= len(message_data):
                            field_data = message_data[pos : pos + length]
                            pos += length

                            # Heuristic: the largest field is likely the video data
                            if len(field_data) > len(video_data):
                                video_data = field_data

                            # Try to decode as string for format/frame_id
                            try:
                                field_str = field_data.decode("utf-8")
                                if field_str in ["h264", "h265", "av1", "av01"]:
                                    video_format = field_str
                                elif len(field_str) < max_string_field_len:  # Likely frame_id
                                    frame_id = field_str
                            except Exception:
                                logger.debug(
                                    "Non-string/undecodable field while parsing CompressedVideo metadata: {exc}"
                                )
                                pass  # Not a string field
                        else:
                            break
                    # Skip other wire types
                    elif wire_type == wire_type_varint:  # Varint
                        while pos < len(message_data) and (message_data[pos] & 0x80):
                            pos += 1
                        pos += 1
                    elif wire_type == wire_type_fixed64:  # Fixed64
                        pos += 8
                    elif wire_type == wire_type_fixed32:  # Fixed32
                        pos += 4
                    else:
                        break

                except Exception:
                    break

            if not video_data:
                raise ValueError("Could not find video data in protobuf message")

            logger.debug(f"Decoded protobuf: format={video_format}, frame_id={frame_id}, data_size={len(video_data)}")

            return video_data, video_format, frame_id, timestamp_info

        except Exception as e:
            logger.error(f"Failed to parse protobuf message: {e}")
            # Fallback: assume the entire message is video data (default to h264)
            return message_data, "h264", "", "unknown"

    def _convert_to_mp4(self, video_data: bytes, output_path: Path, video_format: str) -> None:
        """Convert video data to MP4 file using FFmpeg.

        Args:
            video_data: Raw video data (H.264 or AV1)
            output_path: Path for output MP4 file
            video_format: Video format ('h264', 'av01', etc.)
        """
        try:
            logger.info(f"Converting {len(video_data)} bytes of {video_format} data to MP4...")

            # Handle different video formats
            if video_format.lower() == "h264":
                # H.264 Annex B stream to MP4 container
                process = (
                    ffmpeg.input("pipe:", format="h264")
                    .output(str(output_path), vcodec="copy", movflags="faststart")
                    .overwrite_output()
                    .run_async(pipe_stdin=True, pipe_stdout=True, pipe_stderr=True, quiet=True)
                )
            elif video_format.lower() in ["av01", "av1"]:
                # AV1 data is already in MP4 container, copy directly
                with open(output_path, "wb") as f:
                    f.write(video_data)
                logger.info(f"Successfully created MP4: {output_path}")
                logger.info(f"   File size: {output_path.stat().st_size / 1024:.1f} KB")
                return
            else:
                logger.warning(f"Unexpected video format: {video_format}, attempting H.264 conversion")
                # Fallback to H.264 conversion
                process = (
                    ffmpeg.input("pipe:", format="h264")
                    .output(str(output_path), vcodec="copy", movflags="faststart")
                    .overwrite_output()
                    .run_async(pipe_stdin=True, pipe_stdout=True, pipe_stderr=True, quiet=True)
                )

            # Execute FFmpeg process for H.264
            stdout, stderr = process.communicate(input=video_data)

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
                logger.error(f"FFmpeg conversion failed: {error_msg}")
                raise RuntimeError(f"FFmpeg conversion failed: {error_msg}")

            logger.info(f"Successfully created MP4: {output_path}")
            logger.info(f"   File size: {output_path.stat().st_size / 1024:.1f} KB")

        except Exception as e:
            logger.error(f"Failed to convert video to MP4: {e}")
            raise

    def save_metadata_to_file(self, metadata: dict[str, Any]) -> Path:
        """Save metadata to a JSON file.

        Args:
            metadata: Metadata dictionary extracted from MCAP

        Returns:
            Path to the created metadata JSON file
        """
        if not metadata:
            logger.warning("No metadata to save")
            return Path()

        # Generate metadata filename based on input MCAP file
        mcap_basename: str = self.mcap_path.stem
        metadata_file: Path = self.output_dir / f"{mcap_basename}_metadata.json"

        try:
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            logger.info(f"Metadata saved to: {metadata_file}")
            logger.info(f"File size: {metadata_file.stat().st_size / 1024:.1f} KB")
            return metadata_file

        except Exception as e:
            logger.error(f"Failed to save metadata to file: {e}")
            return Path()

    def print_metadata(self, metadata: dict[str, Any]) -> None:
        """Print formatted metadata information.

        Args:
            metadata: Metadata dictionary extracted from MCAP
        """
        logger.info("=" * 80)
        logger.info("MCAP CONVERSION METADATA")
        logger.info("=" * 80)

        if not metadata:
            logger.info("No metadata found in MCAP file")
            return

        for key, value in metadata.items():
            logger.info(f"\n{key.upper()}:")
            logger.info("-" * 40)

            if isinstance(value, dict):
                self._print_dict(value, indent=1)
            else:
                logger.info(f"  {value}")

        logger.info("\n" + "=" * 80)

    def _print_dict(self, data: dict[str, Any], indent: int = 0) -> None:
        """Recursively print dictionary data with proper formatting.

        Args:
            data: Dictionary to print
            indent: Current indentation level
        """
        prefix = "  " * indent

        for key, value in data.items():
            if isinstance(value, dict):
                logger.info(f"{prefix}{key}:")
                self._print_dict(value, indent + 1)
            elif isinstance(value, list):
                logger.info(f"{prefix}{key}: [{len(value)} items]")
                max_preview_items = 10
                if len(value) <= max_preview_items:  # Show first N items
                    for i, item in enumerate(value):
                        if isinstance(item, dict | list):
                            logger.info(f"{prefix}  [{i}]: {type(item).__name__} with {len(item)} items")
                        else:
                            logger.info(f"{prefix}  [{i}]: {item}")
                else:
                    logger.info(f"{prefix}  [0]: {value[0]}")
                    logger.info(f"{prefix}  ...")
                    logger.info(f"{prefix}  [{len(value) - 1}]: {value[-1]}")
            # Format different data types appropriately
            elif key == "duration_ms" and isinstance(value, int | float):
                logger.info(f"{prefix}{key}: {value:.1f}ms ({value / 1000:.1f}s)")
            elif key == "file_size_bytes" and isinstance(value, int | float):
                logger.info(f"{prefix}{key}: {value:,} bytes ({value / 1024 / 1024:.1f} MB)")
            else:
                logger.info(f"{prefix}{key}: {value}")

    def close(self) -> None:
        """Close the extractor and clean up resources."""
        if self.reader:
            self.reader = None
        logger.info("MCAP Video Extractor closed")


def main() -> None:
    """Main function for command-line usage."""
    parser = argparse.ArgumentParser(
        description="Extract MP4 videos and display metadata from converted MCAP files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract videos and show metadata
  python mcap_video_extractor.py input.mcap

  # Extract to specific directory
  python mcap_video_extractor.py input.mcap --output-dir /path/to/videos

  # Only show metadata (no video extraction)
  python mcap_video_extractor.py input.mcap --metadata-only

Usage Notes:
  - Input MCAP file should be created by mcap_converter.py
  - Output MP4 files will be named after their topic names
  - All conversion metadata will be displayed in formatted output
  - Requires FFmpeg to be installed for video extraction
        """,
    )

    parser.add_argument("input", type=Path, help="Input MCAP file (converted with video data)")
    parser.add_argument(
        "--output-dir", "-o", type=Path, help="Output directory for MP4 files (default: same as input file)"
    )
    parser.add_argument(
        "--metadata-only", "-m", action="store_true", help="Only display metadata, skip video extraction"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    args: argparse.Namespace = parser.parse_args()

    # Configure logging
    log_level = "DEBUG" if args.verbose else "INFO"
    logger.remove()  # Remove default handler
    logger.add(
        lambda msg: print(msg, end=""),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        level=log_level,
    )

    # Validate input file
    if not args.input.exists():
        logger.error(f"Input file not found: {args.input}")
        sys.exit(1)

    if args.input.suffix.lower() != ".mcap":
        logger.error(f"Input file must be an MCAP file: {args.input}")
        sys.exit(1)

    try:
        # Initialize extractor
        extractor = MCAPVideoExtractor(args.input, args.output_dir)

        # Extract videos and metadata
        if args.metadata_only:
            logger.info("Metadata-only mode: Skipping video extraction")

            # Just read metadata
            metadata: dict[str, Any] = {}
            with open(args.input, "rb") as f:
                decoder_factories: list[DecoderFactory] = [DecoderFactory()]
                reader: mcap.reader.McapReader = mcap.reader.make_reader(f, decoder_factories=decoder_factories)

                for mcap_metadata in reader.iter_metadata():
                    try:
                        metadata_dict = json.loads(mcap_metadata.metadata["data"])
                        metadata[mcap_metadata.name] = metadata_dict
                    except Exception as e:
                        logger.warning(f"Failed to parse metadata {mcap_metadata.name}: {e}")
                        metadata[mcap_metadata.name] = {"raw_data": mcap_metadata.metadata}
        else:
            # Extract videos and get metadata
            metadata = extractor.extract_videos_and_metadata()

        # Save metadata to JSON file
        metadata_file = extractor.save_metadata_to_file(metadata)

        # Display metadata
        extractor.print_metadata(metadata)

        # Summary
        logger.info("\nProcessing completed successfully!")
        if not args.metadata_only:
            logger.info(f"Output directory: {extractor.output_dir}")
        if metadata_file.exists():
            logger.info(f"Metadata file: {metadata_file}")
        logger.info(f"Metadata sections: {len(metadata)}")

        extractor.close()

    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
