"""MCAP Writer component for creating output MCAP files with video data."""

import json
from pathlib import Path
from typing import Any

import mcap.writer
from foxglove.schemas import CompressedVideo, Timestamp
from loguru import logger


class MCAPWriter:
    """Handle output MCAP writing with metadata."""

    def __init__(self, output_path: Path) -> None:
        """Initialize the MCAP writer.

        Args:
            output_path: Path where the output MCAP file will be written
        """
        self.output_path: Path = output_path
        self.writer: mcap.writer.Writer | None = None

        # Create output directory if it doesn't exist
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"MCAP Writer initialized for: {output_path}")

    def write_converted_mcap(
        self,
        video_data: dict[str, Any],
        non_image_data: dict[str, Any],
        metadata: dict[str, Any],
        original_metadata: dict[str, Any] | None = None,
    ) -> None:
        """Write the converted MCAP file with video data and preserved non-image topics.

        Args:
            video_data: Converted video data for each topic
            non_image_data: Original non-image messages to preserve
            metadata: Conversion metadata for reversibility
            original_metadata: Original MCAP metadata to preserve (ROS distro, etc.)
        """
        logger.info("Writing converted MCAP file...")

        try:
            with open(self.output_path, "wb") as f:
                self.writer = mcap.writer.Writer(f)
                self.writer.start()

                # Write original metadata first to preserve ROS distro info
                if original_metadata:
                    self._write_original_metadata(original_metadata)

                # Write conversion metadata
                self._write_metadata(metadata)

                # Register and write CompressedVideo topics
                self._write_video_topics(video_data)

                # Write preserved non-image topics
                self._write_preserved_topics(non_image_data)

                self.writer.finish()  # type: ignore[no-untyped-call]
                logger.info(f"MCAP file written successfully: {self.output_path}")

        except Exception as e:
            logger.error(f"Failed to write MCAP file: {e}")
            raise
        finally:
            self.writer = None

    def _write_original_metadata(self, original_metadata: dict[str, Any]) -> None:
        """Write original MCAP metadata to preserve ROS distro and other info."""
        if not self.writer:
            raise RuntimeError("MCAP writer not initialized")

        logger.info("Writing original metadata...")

        for key, value in original_metadata.items():
            self.writer.add_metadata(key, value)
            logger.debug(f"Added original metadata: {key}")

    def _write_metadata(self, metadata: dict[str, Any]) -> None:
        """Write conversion metadata to MCAP file."""
        if not self.writer:
            raise RuntimeError("MCAP writer not initialized")

        logger.info("Writing conversion metadata...")

        # Convert metadata to dictionary format for MCAP
        for key, value in metadata.items():
            # Convert the value to JSON string and store as single key-value pair
            metadata_dict = {"data": json.dumps(value, indent=2)}
            self.writer.add_metadata(key, metadata_dict)
            logger.debug(f"Added metadata: {key}")

    def _write_video_topics(self, video_data: dict[str, Any]) -> None:
        """Write CompressedVideo topics to MCAP file."""
        if not self.writer:
            raise RuntimeError("MCAP writer not initialized")

        logger.info("Writing video topics...")

        # Define CompressedVideo schema
        compressed_video_schema = CompressedVideo.get_schema()
        schema_id = self.writer.register_schema(
            name=compressed_video_schema.name,
            encoding=compressed_video_schema.encoding,
            data=compressed_video_schema.data,
        )

        for topic_name, topic_data in video_data.items():
            logger.info(f"Writing video topic: {topic_name}")

            # Register channel
            channel_id = self.writer.register_channel(
                topic=topic_name, message_encoding="protobuf", schema_id=schema_id
            )

            # Create CompressedVideo message
            video_metadata = topic_data["metadata"]
            video_bytes = topic_data["video_data"]

            # Get timing information
            timestamps = video_metadata["timestamps"]
            ros_timestamps = video_metadata["ros_timestamps"]
            frame_ids = video_metadata["frame_ids"]

            # For CompressedVideo, we create one message containing the entire video
            # with the timestamp of the first frame
            first_ros_timestamp = ros_timestamps[0]
            first_frame_id = frame_ids[0] if frame_ids else ""

            # Create CompressedVideo message with detected format
            # Determine format from codec settings in metadata
            video_format = "h264"  # Default
            if "codec_settings" in video_metadata:
                codec = video_metadata["codec_settings"].get("codec", "libx264")
                if codec == "libsvtav1":
                    video_format = "av01"  # AV1 format identifier for Foxglove

            timestamp = Timestamp(first_ros_timestamp["sec"], first_ros_timestamp["nanosec"])
            compressed_video = CompressedVideo(
                timestamp=timestamp,
                frame_id=first_frame_id,
                data=video_bytes,
                format=video_format,
            )

            # Write the video message with the first frame's timestamp
            self.writer.add_message(
                channel_id=channel_id,
                log_time=timestamps[0],  # Use first frame timestamp
                data=compressed_video.encode(),
                publish_time=timestamps[0],
            )

            logger.info(f"Written video topic: {topic_name} ({len(video_bytes)} bytes)")

    def _write_preserved_topics(self, non_image_data: dict[str, Any]) -> None:
        """Write preserved non-image topics to MCAP file."""
        if not self.writer:
            raise RuntimeError("MCAP writer not initialized")

        logger.info("Writing preserved non-image topics...")

        for topic_name, messages in non_image_data.items():
            if not messages:
                continue

            logger.info(f"Writing preserved topic: {topic_name} ({len(messages)} messages)")

            # Get schema information from first message
            first_message = messages[0]
            schema_info = first_message["schema"]
            message_encoding = first_message.get("message_encoding", schema_info["encoding"])

            # Register schema
            schema_id = self.writer.register_schema(
                name=schema_info["name"], encoding=schema_info["encoding"], data=schema_info["data"]
            )

            # Register channel with preserved message encoding format
            channel_id = self.writer.register_channel(
                topic=topic_name, message_encoding=message_encoding, schema_id=schema_id
            )

            # Write all messages for this topic
            for message in messages:
                self.writer.add_message(
                    channel_id=channel_id,
                    log_time=message["timestamp"],  # Original log_time
                    data=message["data"],
                    publish_time=message.get(
                        "publish_time", message["timestamp"]
                    ),  # Use original publish_time if available
                )

            logger.info(f"Written preserved topic: {topic_name}")

    def close(self) -> None:
        """Close the MCAP writer and clean up resources."""
        if self.writer:
            try:
                self.writer.finish()  # type: ignore[no-untyped-call]
            except Exception as e:
                logger.warning(f"Error finishing MCAP writer: {e}")
            finally:
                self.writer = None

        logger.info("MCAP Writer closed")
