"""Metadata Manager component for creating comprehensive reversibility metadata."""

import time
from typing import Any

from loguru import logger


class MetadataManager:
    """Handle reversibility metadata creation and storage."""

    def __init__(self) -> None:
        """Initialize the metadata manager."""
        self.conversion_timestamp: float = time.time()
        logger.info("Metadata Manager initialized")

    def generate_metadata(
        self,
        image_data: dict[str, Any],
        video_data: dict[str, Any],
        config: dict[str, Any],
        episode_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate comprehensive metadata for complete reversibility.

        Args:
            image_data: Original image data from MCAP
            video_data: Converted video data
            config: Conversion configuration
            episode_context: Optional episode/task provenance metadata

        Returns:
            Complete metadata dictionary for MCAP storage
        """
        logger.info("Generating conversion metadata...")

        metadata = {
            "conversion_info": self._generate_conversion_info(image_data, video_data),
            "video_conversion_params": self._generate_video_params(config),
            "reversibility_data": self._generate_reversibility_data(image_data, video_data),
            "original_image_properties": self._generate_image_properties(image_data),
            "conversion_tool_info": self._generate_tool_info(config),
            "video_stream_details": self._generate_stream_details(video_data),
            "topic_schema_info": self._generate_schema_info(image_data),
        }

        if episode_context:
            metadata["episode_context"] = episode_context

        logger.info("Generated complete conversion metadata")
        return metadata

    def _generate_conversion_info(self, image_data: dict[str, Any], video_data: dict[str, Any]) -> dict[str, Any]:
        """Generate basic conversion information."""
        topic_mapping = {}
        frame_boundaries = {}

        for video_topic, video_info in video_data.items():
            original_topic = video_info["original_topic"]
            topic_mapping[original_topic] = video_topic

            # Store frame boundary information
            if original_topic in image_data:
                frame_boundaries[video_topic] = {
                    "total_frames": len(image_data[original_topic]),
                    "frame_timestamps": video_info["metadata"]["timestamps"],
                    "frame_offsets": list(range(len(image_data[original_topic]))),  # Sequential frame indices
                }

        return {
            "topic_mapping": topic_mapping,
            "frame_boundaries": frame_boundaries,
            "conversion_timestamp": self.conversion_timestamp,
        }

    def _generate_video_params(self, config: dict[str, Any]) -> dict[str, Any]:
        """Generate video conversion parameters."""
        codec_settings = config.get("codec_settings", {})

        return {
            "codec": codec_settings.get("codec"),
            "format": "annex_b",
            "preset": codec_settings.get("preset"),
            "pixel_format": codec_settings.get("pixel_format"),
            "gop_size": codec_settings.get("gop_size"),
            "threads": codec_settings.get("threads"),
        }

    def _generate_reversibility_data(self, image_data: dict[str, Any], video_data: dict[str, Any]) -> dict[str, Any]:
        """Generate frame-to-timestamp mapping for exact reconstruction."""
        frame_mappings = {}

        for video_topic, video_info in video_data.items():
            original_topic = video_info["original_topic"]
            if original_topic in image_data:
                frames = image_data[original_topic]

                frame_mappings[video_topic] = {
                    "original_topic": original_topic,
                    "frame_count": len(frames),
                    "timestamp_mapping": [
                        {
                            "frame_index": i,
                            "mcap_timestamp": frame["timestamp"],
                            "ros_timestamp": frame["ros_timestamp"],
                            "frame_id": frame["frame_id"],
                        }
                        for i, frame in enumerate(frames)
                    ],
                }

        return frame_mappings

    def _generate_image_properties(self, image_data: dict[str, Any]) -> dict[str, Any]:
        """Generate original image properties for each topic."""
        properties = {}

        for topic, frames in image_data.items():
            if frames:
                first_frame = frames[0]
                properties[topic] = {
                    "encoding": first_frame["encoding"],
                    "width": first_frame["width"],
                    "height": first_frame["height"],
                    "step": first_frame["step"],
                    "is_bigendian": first_frame["is_bigendian"],
                }

        return properties

    def _generate_tool_info(self, config: dict[str, Any]) -> dict[str, Any]:
        """Generate conversion tool information."""
        return {
            "converter_version": "1.0.0",
            "conversion_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.conversion_timestamp)),
            "ffmpeg_version": "system_installed",  # Could query actual version
            "config_used": config,
        }

    def _generate_stream_details(self, video_data: dict[str, Any]) -> dict[str, Any]:
        """Generate video stream details for each converted topic."""
        stream_details = {}

        for video_topic, video_info in video_data.items():
            metadata = video_info["metadata"]

            stream_details[video_topic] = {
                "total_frames": metadata["total_frames"],
                "duration_ms": metadata["duration_ms"],
                "frame_rate": metadata["frame_rate"],
                "width": metadata["width"],
                "height": metadata["height"],
                "codec_settings": metadata["codec_settings"],
                "video_size_bytes": len(video_info["video_data"]),
            }

        return stream_details

    def _generate_schema_info(self, image_data: dict[str, Any]) -> dict[str, Any]:
        """Generate topic schema information."""
        schema_info = {}

        for topic in image_data:
            schema_info[topic] = {
                "original_message_type": "sensor_msgs/Image",
                "converted_message_type": "foxglove_msgs/CompressedVideo",
            }

        return schema_info
