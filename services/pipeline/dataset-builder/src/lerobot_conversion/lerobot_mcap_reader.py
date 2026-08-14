"""MCAP reader that extracts exactly the cameras, state and action segments a policy contract declares."""

import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any

import mcap.reader
from loguru import logger
from mcap.records import Channel, Message, Schema
from mcap_protobuf.decoder import DecoderFactory as ProtobufDecoderFactory
from mcap_ros2.decoder import DecoderFactory
from pipeline_configs import PolicySegment

from lerobot_conversion.policy_manifest import PolicyManifest
from lerobot_conversion.segment_decoder import (
    COMPRESSED_VIDEO_SCHEMA_NAME,
    MCAP_SCHEMA_NAMES,
    SegmentDecodeError,
    decode_segment,
)
from models.compressed_video_info import CompressedVideoInfo
from models.extracted_mcap_data import ExtractedMcapData
from models.mcap_summary import McapSummary
from models.robot_action import RobotAction
from models.robot_state import RobotState
from models.topic_info import TopicInfo
from models.topic_statistics import TopicStatistics

# recorded alongside the contract's topics and never part of a dataset
IGNORED_TOPICS = frozenset({"/rosout", "/tf", "/tf_static", "/parameter_events"})
IGNORED_SCHEMA_NAMES = frozenset({"sensor_msgs/msg/CompressedImage"})

PROGRESS_LOG_INTERVAL = 5000


class _DecodeFailed:
    """Sentinel yielded for messages that could not be decoded."""


DECODE_FAILED = _DecodeFailed()


@dataclass
class _Extraction:
    """Per-file accumulator, keyed by the policy_key each contract segment owns."""

    compressed_videos: dict[str, CompressedVideoInfo] = field(default_factory=dict)
    robot_states: defaultdict[str, list[RobotState]] = field(default_factory=lambda: defaultdict(list))
    actions: defaultdict[str, list[RobotAction]] = field(default_factory=lambda: defaultdict(list))


class ResilientDecoderFactory:
    """Wraps a decoder factory so a single message's decode error is non-fatal.

    The mcap library still owns decoding and per-channel decoder caching via
    ``iter_decoded_messages``; this decorator only intercepts the per-message
    decode call so a malformed message yields :data:`DECODE_FAILED` instead of
    raising and aborting iteration over the rest of the file.
    """

    def __init__(self, inner: Any) -> None:  # noqa: ANN401 - mcap DecoderFactory protocol
        """Wrap an existing decoder factory to make per-message decode failures non-fatal."""
        self._inner = inner

    def decoder_for(self, message_encoding: str, schema: Schema | None) -> Callable[[bytes], Any] | None:
        """Return a safe decoder that yields `DECODE_FAILED` instead of raising on bad messages."""
        decoder = self._inner.decoder_for(message_encoding, schema)
        if decoder is None:
            return None

        def safe_decoder(data: bytes) -> Any:  # noqa: ANN401
            try:
                return decoder(data)
            except Exception as e:
                schema_name = schema.name if schema else "None"
                # Per-message detail is logged at DEBUG to avoid flooding the logs;
                # the reader emits an aggregated per-topic summary at INFO/WARNING.
                logger.debug(f"Failed to decode message (schema={schema_name}, encoding={message_encoding}): {e}")
                return DECODE_FAILED

        return safe_decoder


class LeRobotMCAPReader:
    """MCAP reader specialized for LeRobot dataset conversion."""

    def __init__(self, manifest: PolicyManifest) -> None:
        """Initialize the reader for one policy contract."""
        self.manifest = manifest
        # Topics already reported during the current extraction, so each is logged once
        # instead of per message. Reset at the start of every extract.
        self._logged_topics: set[str] = set()
        logger.debug("LeRobot MCAP Reader initialized")

    def extract_lerobot_data(self, mcap_path: Path) -> ExtractedMcapData:
        """Extract all data the contract declares from one MCAP file."""
        logger.info("Extracting data for LeRobot conversion...")

        self._logged_topics = set()
        undecodable_counts: defaultdict[str, int] = defaultdict(int)
        extraction = _Extraction()

        try:
            with open(mcap_path, "rb") as f:
                reader = mcap.reader.make_reader(f, decoder_factories=self._build_decoder_factories())
                mcap_summary = self._get_mcap_summary(reader)

                logger.debug(f"Found topics: {list(mcap_summary.topics.keys())}")

                message_count = 0
                for schema, channel, message, ros_message in reader.iter_decoded_messages():
                    message_count += 1

                    if message_count % PROGRESS_LOG_INTERVAL == 0:
                        logger.debug(f"Processed {message_count} messages...")

                    if ros_message is DECODE_FAILED:
                        undecodable_counts[channel.topic] += 1
                        continue

                    try:
                        # mutates extraction in place, accumulating this message into its segment's list
                        self._handle_message(channel.topic, schema, message, ros_message, extraction)
                    except Exception as e:
                        logger.error(f"Error processing message {message.log_time} on topic {channel.topic}: {e}")

                logger.info(f"Extracted {message_count} total messages")
                self._log_undecodable(undecodable_counts)

                return self._build_extracted_data(extraction, self._extract_metadata(reader), mcap_summary)

        except Exception as e:
            logger.error(f"Failed to extract mcap data from {mcap_path}: {e}")
            raise

    def _build_extracted_data(
        self, extraction: _Extraction, metadata: dict[str, Any], mcap_summary: McapSummary
    ) -> ExtractedMcapData:
        """Order every modality by the contract and pair it with its timing statistics."""
        compressed_videos = self.manifest.order_cameras(extraction.compressed_videos)
        robot_states = self.manifest.order_state(dict(extraction.robot_states))
        actions = self.manifest.order_action(dict(extraction.actions))

        return ExtractedMcapData(
            compressed_videos=compressed_videos,
            video_stats={key: self._get_video_stats(key, video, metadata) for key, video in compressed_videos.items()},
            robot_states=robot_states,
            state_stats={key: self._get_stats(states) for key, states in robot_states.items()},
            actions=actions,
            action_stats={key: self._get_stats(action) for key, action in actions.items()},
            metadata=metadata,
            mcap_summary=mcap_summary,
        )

    def _handle_message(
        self,
        topic_name: str,
        schema: Schema | None,
        message: Message,
        ros_message: Any,  # noqa: ANN401 - decoded ROS or protobuf message
        extraction: _Extraction,
    ) -> None:
        """Feed one message into every contract segment that reads its topic."""
        cameras = self.manifest.cameras_by_topic.get(topic_name, ())
        state_segments = self.manifest.state_by_topic.get(topic_name, ())
        action_segments = self.manifest.action_by_topic.get(topic_name, ())

        if not (cameras or state_segments or action_segments):
            self._log_unconfigured_topic(topic_name, schema)
            return

        if cameras and self._schema_matches(topic_name, schema, COMPRESSED_VIDEO_SCHEMA_NAME):
            for camera in cameras:
                self._handle_compressed_video(camera.policy_key, message, ros_message, extraction)

        for segment in state_segments:
            values = self._decode(segment, topic_name, schema, ros_message)
            if values is not None:
                extraction.robot_states[segment.policy_key].append(
                    RobotState(
                        timestamp_ns=message.log_time,
                        publish_time_ns=message.publish_time,
                        names=list(segment.element_names),
                        values=values,
                    )
                )

        for segment in action_segments:
            values = self._decode(segment, topic_name, schema, ros_message)
            if values is not None:
                extraction.actions[segment.policy_key].append(
                    RobotAction(
                        timestamp_ns=message.log_time,
                        publish_time_ns=message.publish_time,
                        names=list(segment.element_names),
                        values=values,
                    )
                )

    def _decode(
        self,
        segment: PolicySegment,
        topic_name: str,
        schema: Schema | None,
        ros_message: Any,  # noqa: ANN401
    ) -> list[float] | None:
        """Decode one segment, or return None after reporting why the message cannot supply it."""
        if not self._schema_matches(topic_name, schema, MCAP_SCHEMA_NAMES[segment.message_type]):
            return None
        try:
            return decode_segment(segment, ros_message)
        except SegmentDecodeError as e:
            if self._first_report(f"decode:{segment.policy_key}"):
                logger.error(str(e))
            return None

    def _schema_matches(self, topic_name: str, schema: Schema | None, expected: str) -> bool:
        """Whether a topic carries the schema the contract declared for it."""
        actual = schema.name if schema else "None"
        if actual == expected:
            return True
        if self._first_report(f"schema:{topic_name}"):
            logger.error(f"Contract declares {expected} for {topic_name} but it was recorded as {actual}; skipping it")
        return False

    def _handle_compressed_video(
        self,
        policy_key: str,
        message: Message,
        ros_message: Any,  # noqa: ANN401 - foxglove.CompressedVideo
        extraction: _Extraction,
    ) -> None:
        """Store the single CompressedVideo message a processed episode carries per camera."""
        video_format = getattr(ros_message, "format", "unknown")
        video_data = CompressedVideoInfo(
            timestamp_ns=message.log_time,
            publish_time_ns=message.publish_time,
            format=video_format,
            data=bytes(getattr(ros_message, "data", b"")),
        )
        extraction.compressed_videos[policy_key] = video_data

        logger.info(
            f"Extracted CompressedVideo for {policy_key}: {len(video_data.data)} bytes, format: {video_data.format}"
        )

    def _log_unconfigured_topic(self, topic_name: str, schema: Schema | None) -> None:
        """Report a recorded topic no contract segment reads, once per topic."""
        schema_name = schema.name if schema else "None"
        if topic_name in IGNORED_TOPICS or schema_name in IGNORED_SCHEMA_NAMES:
            return
        if self._first_report(f"unconfigured:{topic_name}"):
            logger.info(f"Ignoring topic outside the policy contract {topic_name} with schema {schema_name}")

    def _first_report(self, key: str) -> bool:
        """Whether a per-topic diagnostic still has to be emitted; keeps per-message findings out of the logs."""
        if key in self._logged_topics:
            return False
        self._logged_topics.add(key)
        return True

    def _log_undecodable(self, undecodable_counts: dict[str, int]) -> None:
        if not undecodable_counts:
            return
        total = sum(undecodable_counts.values())
        per_topic = ", ".join(f"{topic} ({count})" for topic, count in sorted(undecodable_counts.items()))
        logger.warning(f"Skipped {total} undecodable messages across topics: {per_topic}")

    def _build_decoder_factories(self) -> list[Any]:
        """Build fresh decoder factories for a single MCAP file.

        Factories cache decoders by ``schema.id``, which is only unique within one
        file. Reusing a factory across files can return the wrong decoder when ids
        collide, so each file gets its own.
        """
        return [
            ResilientDecoderFactory(DecoderFactory()),
            ResilientDecoderFactory(ProtobufDecoderFactory()),
        ]

    def _get_mcap_summary(self, reader: mcap.reader.McapReader) -> McapSummary:
        summary = reader.get_summary()

        if not summary:
            raise ValueError("Failed to get MCAP summary")

        channels = summary.channels
        statistics = summary.statistics
        channel_message_counts = statistics.channel_message_counts if statistics else {}
        schemas = summary.schemas

        topics = {
            channel.topic: self._get_topic_info_from_channel(
                channel, channel_message_counts.get(channel_id), schemas.get(channel_id)
            )
            for channel_id, channel in channels.items()
        }

        return McapSummary(topics=topics, statistics=statistics)

    def _get_topic_info_from_channel(
        self, channel: Channel, channel_message_count: int | None, schema: Schema | None
    ) -> TopicInfo:
        return TopicInfo(
            schema_name=schema.name if schema else "unknown",
            encoding=schema.encoding if schema else "unknown",
            message_encoding=channel.message_encoding,
            message_count=channel_message_count or 0,
        )

    def _extract_metadata(self, reader: mcap.reader.McapReader) -> dict[str, Any]:
        """Extract original MCAP metadata."""
        metadata = {}

        try:
            for meta in reader.iter_metadata():
                metadata[meta.name] = dict(meta.metadata)

        except Exception as e:
            logger.warning(f"Failed to extract metadata: {e}")

        return metadata

    def _get_stats(self, states: list[RobotState] | list[RobotAction]) -> TopicStatistics:
        timestamps = [state.timestamp_ns for state in states]

        if not timestamps:
            raise ValueError("Cannot compute topic statistics for an empty message list")

        min_timestamp = min(timestamps)
        max_timestamp = max(timestamps)
        duration_ns = max_timestamp - min_timestamp
        duration_s = duration_ns / 1e9
        message_count = len(timestamps)
        average_frequency_hz = (message_count / duration_s) if duration_s > 0 else 0.0

        frequency_interval_in_ns = int(1e9 / average_frequency_hz) if average_frequency_hz > 0 else 0

        # gap is defined as twice the expected interval
        gap_ns = frequency_interval_in_ns * 2
        gaps = self._find_gaps(sorted(timestamps), gap_ns)

        return TopicStatistics(
            message_count=message_count,
            first_message_time_ns=min_timestamp,
            last_message_time_ns=max_timestamp,
            gaps=gaps,
            fps=average_frequency_hz,
        )

    def _get_video_stats(
        self, policy_key: str, video: CompressedVideoInfo, metadata: dict[str, Any]
    ) -> TopicStatistics:
        """Read a camera's duration and frame rate from the episode's video_stream_details metadata."""
        dataset_topic = self.manifest.camera_for(policy_key).dataset_topic
        try:
            video_stream_details = json.loads(metadata["video_stream_details"]["data"])
            topic_metadata = video_stream_details[dataset_topic]
        except KeyError as exc:
            raise ValueError(
                f"Episode metadata has no video_stream_details for {dataset_topic} (camera {policy_key!r}); "
                "the contract's camera topic does not match what data-processor encoded"
            ) from exc

        duration_ns = int(topic_metadata["duration_ms"] * 1e6)

        return TopicStatistics(
            message_count=1,
            first_message_time_ns=video.timestamp_ns,
            last_message_time_ns=video.timestamp_ns + duration_ns,
            # We can't calculate gaps here, since we only have a video, not the individual frames
            gaps=[],
            fps=topic_metadata["frame_rate"],
        )

    def _find_gaps(self, timestamps: list[int], gap_ns: int) -> list[tuple[int, int]]:
        gaps: list[tuple[int, int]] = []
        for prev, curr in pairwise(timestamps):
            if curr - prev > gap_ns:
                gaps.append((prev, curr))
        return gaps
