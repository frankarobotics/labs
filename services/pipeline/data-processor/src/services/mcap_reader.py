"""MCAP Reader component for reading and parsing MCAP files."""

from pathlib import Path
from typing import Any, Protocol

import mcap.reader
from loguru import logger
from mcap_ros2.decoder import DecoderFactory


class _Schema(Protocol):
    name: str | None
    encoding: str | None
    data: bytes | None


class _Channel(Protocol):
    topic: str
    message_encoding: str


class _Message(Protocol):
    log_time: int
    publish_time: int
    data: bytes


class _Stamp(Protocol):
    sec: int
    nanosec: int


class _Header(Protocol):
    stamp: _Stamp
    frame_id: str


class _RosImage(Protocol):
    header: _Header
    width: int
    height: int
    encoding: str
    is_bigendian: int
    step: int
    data: Any  # ROS2 message field can be bytes/array-like; keep flexible here


class MCAPReader:
    """Handle MCAP file reading and message parsing."""

    def __init__(self, mcap_path: Path) -> None:
        """Initialize the MCAP reader.

        Args:
            mcap_path: Path to the MCAP file to read
        """
        self.mcap_path: Path = mcap_path
        self.reader: mcap.reader.McapReader | None = None

        logger.info(f"MCAP Reader initialized for: {mcap_path}")

    def read_messages(
        self, camera_topics: list[str]
    ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
        """Read messages from MCAP file and separate image data from non-image data.

        Args:
            camera_topics: List of camera topics to extract as image data

        Returns:
            Tuple of (image_data, non_image_data) where:
            - image_data: Dict mapping topic names to lists of frame data
            - non_image_data: Dict mapping topic names to lists of message data
        """
        image_data: dict[str, list[dict[str, Any]]] = {}
        non_image_data: dict[str, list[dict[str, Any]]] = {}

        # Initialize empty lists for camera topics
        for topic in camera_topics:
            image_data[topic] = []

        try:
            with open(self.mcap_path, "rb") as f:
                # Create ROS 2 decoder factory for CDR messages
                decoder_factories: list[DecoderFactory] = [DecoderFactory()]
                self.reader = mcap.reader.make_reader(f, decoder_factories=decoder_factories)

                logger.info("Reading MCAP file...")
                message_count = 0

                # Read all messages from MCAP with ROS 2 CDR decoding
                for schema, channel, message, ros_message in self.reader.iter_decoded_messages():
                    message_count += 1

                    if message_count % 1000 == 0:
                        logger.debug(f"Processed {message_count} messages...")

                    topic_name: str = channel.topic

                    if topic_name in camera_topics:
                        # Delegate image parsing to helper
                        self._handle_image_message(schema, channel, message, ros_message, image_data)
                    else:
                        # Delegate non-image message handling to helper
                        self._handle_non_image_message(schema, channel, message, non_image_data)

                logger.info(f"Read {message_count} messages from MCAP")

                # Log statistics
                for topic, frames in image_data.items():
                    if frames:
                        logger.info(f"{topic}: {len(frames)} image frames")
                    else:
                        logger.warning(f"{topic}: No image frames found")

                for topic, messages in non_image_data.items():
                    logger.info(f"{topic}: {len(messages)} messages")

        except Exception as e:
            logger.error(f"Failed to read MCAP file: {e}")
            raise

        # Sort image frames by timestamp for each topic
        for topic, frames in image_data.items():
            frames.sort(key=lambda x: x["timestamp"])
            logger.info(f"Sorted {len(frames)} frames by timestamp for {topic}")

        # Filter out topics with no messages
        non_image_data = {topic: messages for topic, messages in non_image_data.items() if len(messages) > 0}

        return image_data, non_image_data

    def _handle_image_message(
        self,
        schema: _Schema,
        channel: _Channel,
        message: _Message,
        ros_message: _RosImage | None,
        image_data: dict[str, list[dict[str, Any]]],
    ) -> None:
        """Handle a decoded image message and append frame data to image_data."""
        try:
            topic_name = channel.topic
            if getattr(schema, "name", None) != "sensor_msgs/msg/Image" or ros_message is None:
                logger.warning(
                    "Expected Image message for %s, got schema %s",
                    topic_name,
                    getattr(schema, "name", None),
                )
                return

            frame_data = {
                "timestamp": message.log_time,
                "publish_time": message.publish_time,
                "ros_timestamp": {
                    "sec": ros_message.header.stamp.sec,
                    "nanosec": ros_message.header.stamp.nanosec,
                },
                "frame_id": ros_message.header.frame_id,
                "width": ros_message.width,
                "height": ros_message.height,
                "encoding": ros_message.encoding,
                "is_bigendian": ros_message.is_bigendian,
                "step": ros_message.step,
                "data": ros_message.data,
            }
            if topic_name not in image_data:
                image_data[topic_name] = []
            image_data[topic_name].append(frame_data)
        except Exception as e:
            logger.error("Failed to parse Image message for %s: %s", channel.topic, e)

    def _handle_non_image_message(
        self,
        schema: _Schema,
        channel: _Channel,
        message: _Message,
        non_image_data: dict[str, Any],
    ) -> None:
        """Handle a non-image message and append raw data to non_image_data."""
        try:
            topic_name = channel.topic
            message_data = {
                "timestamp": message.log_time,
                "publish_time": message.publish_time,
                "topic": topic_name,
                "schema": {
                    "name": getattr(schema, "name", None),
                    "encoding": getattr(schema, "encoding", None),
                    "data": getattr(schema, "data", None),
                },
                "message_encoding": channel.message_encoding,
                "data": message.data,
            }
            if topic_name not in non_image_data:
                non_image_data[topic_name] = []
            non_image_data[topic_name].append(message_data)
        except Exception as e:
            logger.error("Failed to record non-image message for %s: %s", getattr(channel, "topic", "<unknown>"), e)

    def discover_image_topics(self) -> list[str]:
        """Scan the MCAP file and return a list of topics that contain Image messages.

        Returns:
            list[str]: Sorted list of topic names where schema.name == 'sensor_msgs/msg/Image'
        """
        topics: set[str] = set()

        try:
            with open(self.mcap_path, "rb") as f:
                reader: mcap.reader.McapReader = mcap.reader.make_reader(f)
                # Use raw message iteration to avoid requiring decoder factories for discovery.
                # iter_messages() yields (schema, channel, message) without attempting to decode payloads.
                for schema, channel, _message in reader.iter_messages():
                    try:
                        if getattr(schema, "name", None) == "sensor_msgs/msg/Image":
                            topics.add(channel.topic)
                    except Exception as exc:
                        # Ignore malformed message entries while discovering topics, but log at debug level
                        logger.debug("Malformed MCAP entry during discovery: %s", exc)
        except Exception as e:
            logger.error(f"Failed to discover image topics from MCAP: {e}")

        return sorted(topics)

    def read_original_metadata(self) -> dict[str, Any]:
        """Read original MCAP metadata to preserve it in converted file."""
        original_metadata = {}

        try:
            # Open a fresh file handle to read metadata independently
            with open(self.mcap_path, "rb") as f:
                reader: mcap.reader.McapReader = mcap.reader.make_reader(f)
                # Extract metadata from original MCAP
                for metadata in reader.iter_metadata():
                    original_metadata[metadata.name] = dict(metadata.metadata)
        except Exception as e:
            logger.warning(f"Failed to read original metadata: {e}")

        return original_metadata

    def close(self) -> None:
        """Close the MCAP reader and clean up resources."""
        if self.reader:
            # McapReader doesn't require explicit closing, but we can clear the reference
            self.reader = None
        logger.info("MCAP Reader closed")
