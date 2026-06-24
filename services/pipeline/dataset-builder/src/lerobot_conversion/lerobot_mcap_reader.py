"""LeRobot MCAP Reader for extracting CompressedVideo and robot state data."""

import json
from collections import defaultdict
from collections.abc import Callable
from itertools import pairwise
from pathlib import Path
from typing import Any

import mcap.reader
from foxglove.schemas import CompressedVideo
from geometry_msgs.msg import PoseStamped, TwistStamped, WrenchStamped  # type: ignore[import-not-found]
from loguru import logger
from mcap.records import Channel, Message, Schema
from mcap_protobuf.decoder import DecoderFactory as ProtobufDecoderFactory
from mcap_ros2.decoder import DecoderFactory
from sensor_msgs.msg import JointState  # type: ignore[import-not-found]
from std_msgs.msg import Bool, Float32  # type: ignore[import-not-found]

from lerobot_conversion.topic_manifest import DatasetTopicManifest
from models.compressed_video_info import CompressedVideoInfo
from models.extracted_mcap_data import ExtractedMcapData
from models.mcap_summary import McapSummary
from models.robot_action import RobotAction
from models.robot_state import RobotState
from models.topic_info import TopicInfo
from models.topic_statistics import TopicStatistics


class _DecodeFailed:
    """Sentinel yielded for messages that could not be decoded."""


DECODE_FAILED = _DecodeFailed()


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

    def __init__(self, topic_manifest: DatasetTopicManifest | None = None) -> None:
        """Initialize LeRobot MCAP reader."""
        logger.debug("LeRobot MCAP Reader initialized")
        self.topic_manifest = topic_manifest
        # Topics already reported as "ignored" during the current extraction, so each
        # is logged once instead of per message. Reset at the start of every extract.
        self._logged_ignored_topics: set[str] = set()
        # Topics whose message payload did not match the expected schema, logged once
        # per topic instead of per message. Reset at the start of every extract.
        self._logged_state_extraction_errors: set[str] = set()

    def extract_lerobot_data(self, mcap_path: Path) -> ExtractedMcapData:
        """Extract all data needed for LeRobot conversion."""
        logger.info("Extracting data for LeRobot conversion...")

        compressed_videos: dict[str, CompressedVideoInfo] = {}
        robot_states: dict[str, list[RobotState]] = {}
        actions: dict[str, list[RobotAction]] = {}
        metadata: dict[str, Any] = {}

        # Per-extraction log de-duplication / aggregation to keep logs readable
        # even when many messages are ignored or undecodable.
        self._logged_ignored_topics = set()
        self._logged_state_extraction_errors = set()
        undecodable_counts: defaultdict[str, int] = defaultdict(int)

        try:
            with open(mcap_path, "rb") as f:
                reader = mcap.reader.make_reader(f, decoder_factories=self._build_decoder_factories())
                mcap_summary = self._get_mcap_summary(reader)

                logger.debug(f"Found topics: {list(mcap_summary.topics.keys())}")

                message_count = 0

                for schema, channel, message, ros_message in reader.iter_decoded_messages():
                    message_count += 1

                    if message_count % 5000 == 0:
                        logger.debug(f"Processed {message_count} messages...")

                    topic_name: str = channel.topic

                    if ros_message is DECODE_FAILED:
                        undecodable_counts[topic_name] += 1
                        continue

                    try:
                        self._handle_message(
                            topic_name, schema, message, ros_message, compressed_videos, robot_states, actions
                        )
                    except Exception as e:
                        logger.error(f"Error processing message {message.log_time} on topic {topic_name}: {e}")

                logger.info(f"Extracted {message_count} total messages")

                if undecodable_counts:
                    total_undecodable = sum(undecodable_counts.values())
                    per_topic = ", ".join(f"{topic} ({count})" for topic, count in sorted(undecodable_counts.items()))
                    logger.warning(f"Skipped {total_undecodable} undecodable messages across topics: {per_topic}")

                if self.topic_manifest is not None:
                    compressed_videos = self.topic_manifest.order_image_topics(compressed_videos)
                    robot_states = self.topic_manifest.order_state_topics(robot_states)
                    actions = self.topic_manifest.order_action_topics(actions)

                # Extract original metadata
                metadata = self._extract_metadata(reader)

                robot_state_topics = {topic: self._get_stats(states) for topic, states in robot_states.items()}
                action_topics = {topic: self._get_stats(action) for topic, action in actions.items()}
                video_topics = {
                    topic: self._get_video_stats(topic, video, metadata) for topic, video in compressed_videos.items()
                }

                return ExtractedMcapData(
                    compressed_videos=compressed_videos,
                    video_topics=video_topics,
                    robot_states=robot_states,
                    robot_state_topics=robot_state_topics,
                    actions=actions,
                    action_topics=action_topics,
                    metadata=metadata,
                    mcap_summary=mcap_summary,
                )

        except Exception as e:
            logger.error(f"Failed to extract mcap data from {mcap_path}: {e}")
            raise

    def _handle_message(  # noqa: PLR0913
        self,
        topic_name: str,
        schema: Schema | None,
        message: Message,
        ros_message: Any,  # noqa: ANN401
        compressed_videos: dict[str, CompressedVideoInfo],
        robot_states: dict[str, list[RobotState]],
        actions: dict[str, list[RobotAction]],
    ) -> None:
        if self.topic_manifest is not None:
            self._handle_manifest_message(
                topic_name, schema, message, ros_message, compressed_videos, robot_states, actions
            )
            return

        logger.warning(
            f"No topic manifest provided, processing all topics with best-effort handling. Topic: {topic_name}"
        )
        if self._is_ignored_topic(topic_name, schema):
            pass
        elif self._is_compressed_video(schema):
            self._handle_compressed_video(topic_name, message, ros_message, compressed_videos)
        elif self._is_joint_state(schema):
            self._handle_joint_state(topic_name, message, ros_message, robot_states)
        elif self._is_pose_stamped(schema):
            self._handle_pose_stamped(topic_name, message, ros_message, robot_states)
        elif self._is_twist_stamped(schema):
            self._handle_twist_stamped(topic_name, message, ros_message, actions)
        elif self._is_wrench_stamped(schema):
            self._handle_wrench_stamped(topic_name, message, ros_message, robot_states)
        elif self._is_float_32(schema):
            self._handle_float32(topic_name, message, ros_message, robot_states, actions)
        elif self._is_bool(schema):
            self._handle_bool(topic_name, message, ros_message, robot_states)
        else:
            logger.info(f"Ignoring unsupported topic {topic_name} with schema {schema.name if schema else 'None'}")

    def _handle_manifest_message(  # noqa: PLR0913
        self,
        topic_name: str,
        schema: Schema | None,
        message: Message,
        ros_message: Any,  # noqa: ANN401
        compressed_videos: dict[str, CompressedVideoInfo],
        robot_states: dict[str, list[RobotState]],
        actions: dict[str, list[RobotAction]],
    ) -> None:
        topic_role = self.topic_manifest.classify_topic(topic_name) if self.topic_manifest is not None else None

        if topic_role == "ignored":
            return
        if topic_role == "image":
            if self._is_compressed_video(schema):
                self._handle_compressed_video(topic_name, message, ros_message, compressed_videos)
            return
        if topic_role == "state":
            self._handle_state_topic(topic_name, schema, message, ros_message, robot_states)
            return
        if topic_role == "action":
            self._handle_action_topic(topic_name, schema, message, ros_message, actions)
            return

        if self._is_ignored_topic(topic_name, schema):
            return

        if topic_name not in self._logged_ignored_topics:
            self._logged_ignored_topics.add(topic_name)
            logger.info(
                f"Ignoring topic outside configured manifest {topic_name} "
                f"with schema {schema.name if schema else 'None'}"
            )

    def _handle_state_topic(
        self,
        topic_name: str,
        schema: Schema | None,
        message: Message,
        ros_message: Any,  # noqa: ANN401
        robot_states: dict[str, list[RobotState]],
    ) -> None:
        if self._is_joint_state(schema):
            self._handle_joint_state(topic_name, message, ros_message, robot_states)
        elif self._is_pose_stamped(schema):
            self._handle_pose_stamped(topic_name, message, ros_message, robot_states)
        elif self._is_wrench_stamped(schema):
            self._handle_wrench_stamped(topic_name, message, ros_message, robot_states)
        elif self._is_bool(schema):
            self._handle_bool(topic_name, message, ros_message, robot_states)
        elif self._is_float_32(schema):
            self._handle_float32_state(topic_name, message, ros_message, robot_states)
        else:
            logger.info(
                "Ignoring configured observation topic {} with unsupported schema {}",
                topic_name,
                schema.name if schema else "None",
            )

    def _handle_action_topic(
        self,
        topic_name: str,
        schema: Schema | None,
        message: Message,
        ros_message: Any,  # noqa: ANN401
        actions: dict[str, list[RobotAction]],
    ) -> None:
        if self._is_joint_state(schema):
            self._handle_joint_state_action(topic_name, message, ros_message, actions)
        elif self._is_twist_stamped(schema):
            self._handle_twist_stamped(topic_name, message, ros_message, actions)
        elif self._is_float_32(schema):
            self._handle_gripper_action(topic_name, message, ros_message, actions)
        else:
            logger.info(
                "Ignoring configured action topic {} with unsupported schema {}",
                topic_name,
                schema.name if schema else "None",
            )

    def _is_ignored_topic(self, topic_name: str, schema: Schema | None) -> bool:
        ignored_topics = {"/rosout", "/tf", "/tf_static", "/parameter_events"}
        return topic_name in ignored_topics or (schema is not None and schema.name == "sensor_msgs/msg/CompressedImage")

    def _is_compressed_video(self, schema: Schema | None) -> bool:
        return schema is not None and schema.name == "foxglove.CompressedVideo"

    def _is_joint_state(self, schema: Schema | None) -> bool:
        return schema is not None and schema.name == "sensor_msgs/msg/JointState"

    def _is_pose_stamped(self, schema: Schema | None) -> bool:
        return schema is not None and schema.name == "geometry_msgs/msg/PoseStamped"

    def _is_twist_stamped(self, schema: Schema | None) -> bool:
        return schema is not None and schema.name == "geometry_msgs/msg/TwistStamped"

    def _is_wrench_stamped(self, schema: Schema | None) -> bool:
        return schema is not None and schema.name == "geometry_msgs/msg/WrenchStamped"

    def _is_float_32(self, schema: Schema | None) -> bool:
        return schema is not None and schema.name == "std_msgs/msg/Float32"

    def _is_bool(self, schema: Schema | None) -> bool:
        return schema is not None and schema.name == "std_msgs/msg/Bool"

    def _is_gripper_action(self, topic_name: str) -> bool:
        # /franka_gello/left/gripper/gripper_client/target_gripper_width_percent
        # /franka_gello/right/gripper/gripper_client/target_gripper_width_percent
        # /robotiq_gripper/left/f_30hz/robotiq_2f_gripper/binary_command
        # /robotiq_gripper/right/f_30hz/robotiq_2f_gripper/binary_command
        return "gripper" in topic_name.lower() and (
            "target_gripper_width_percent" in topic_name.lower() or "binary_command" in topic_name.lower()
        )

    def _is_gripper_state(self, topic_name: str) -> bool:
        """Determine if the topic is a gripper state topic."""
        # /robotiq_gripper/right/f_30hz/robotiq_2f_gripper/finger_distance_mm
        return "gripper" in topic_name.lower() and ("finger_distance_mm" in topic_name.lower())

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
            raise Exception("Failed to get MCAP summary")

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

    def _log_extraction_error_once(self, topic_name: str, schema_type: str, error: Exception) -> None:
        """Log a schema-extraction failure once per topic to avoid per-message log spam."""
        if topic_name not in self._logged_state_extraction_errors:
            self._logged_state_extraction_errors.add(topic_name)
            logger.error(
                f"Failed to extract {schema_type} from {topic_name} "
                f"(payload does not match {schema_type} schema, logged once per topic): {error}"
            )

    def _handle_compressed_video(
        self,
        topic_name: str,
        message: Message,
        ros_message: CompressedVideo,
        compressed_videos: dict[str, CompressedVideoInfo],
    ) -> None:
        """Handle CompressedVideo message extraction."""
        try:
            # Extract video data from Foxglove CompressedVideo protobuf
            # Access attributes with getattr for safety since protobuf message structure may vary
            video_format = getattr(ros_message, "format", "unknown")  # Should be "mp4" or similar
            video_data_bytes = getattr(ros_message, "data", b"")  # The actual MP4/AV1 video bytes
            video_data = CompressedVideoInfo(
                timestamp_ns=message.log_time,
                publish_time_ns=message.publish_time,
                format=video_format,
                data=bytes(video_data_bytes),
            )

            compressed_videos[topic_name] = video_data

            logger.info(
                f"Extracted CompressedVideo from {topic_name}: {len(video_data.data)} bytes, "
                f"format: {video_data.format}"
            )

        except Exception as e:
            self._log_extraction_error_once(topic_name, "CompressedVideo", e)

    def _handle_joint_state(
        self,
        topic_name: str,
        message: Message,
        ros_message: JointState,
        robot_states: dict[str, list[RobotState]],
    ) -> None:
        """Handle JointState message extraction."""
        try:
            robot_state = RobotState(
                timestamp_ns=message.log_time,
                publish_time_ns=message.publish_time,
                names=list(ros_message.name),  # Joint names
                values=list(ros_message.position),  # Joint positions
            )

            if topic_name not in robot_states:
                robot_states[topic_name] = []

            robot_states[topic_name].append(robot_state)

        except Exception as e:
            self._log_extraction_error_once(topic_name, "JointState", e)

    def _handle_pose_stamped(
        self,
        topic_name: str,
        message: Message,
        ros_message: PoseStamped,
        robot_states: dict[str, list[RobotState]],
    ) -> None:
        """Handle PoseStamped message extraction."""
        try:
            position = ros_message.pose.position
            orientation = ros_message.pose.orientation

            # Flatten position and orientation into a single list
            pose_values = [
                position.x,
                position.y,
                position.z,
                orientation.x,
                orientation.y,
                orientation.z,
                orientation.w,
            ]

            robot_state = RobotState(
                timestamp_ns=message.log_time,
                publish_time_ns=message.publish_time,
                values=pose_values,
                names=[
                    "position_x",
                    "position_y",
                    "position_z",
                    "orientation_x",
                    "orientation_y",
                    "orientation_z",
                    "orientation_w",
                ],
            )

            if topic_name not in robot_states:
                robot_states[topic_name] = []

            robot_states[topic_name].append(robot_state)

        except Exception as e:
            self._log_extraction_error_once(topic_name, "PoseStamped", e)

    def _handle_joint_state_action(
        self,
        topic_name: str,
        message: Message,
        ros_message: JointState,
        actions: dict[str, list[RobotAction]],
    ) -> None:
        """Handle JointState message extraction for action topics."""
        try:
            action = RobotAction(
                timestamp_ns=message.log_time,
                publish_time_ns=message.publish_time,
                names=list(ros_message.name),
                values=list(ros_message.position),
            )

            if topic_name not in actions:
                actions[topic_name] = []

            actions[topic_name].append(action)

        except Exception as e:
            self._log_extraction_error_once(topic_name, "JointState", e)

    def _handle_twist_stamped(
        self,
        topic_name: str,
        message: Message,
        ros_message: TwistStamped,
        actions: dict[str, list[RobotAction]],
    ) -> None:
        """Handle TwistStamped message extraction."""
        try:
            linear = ros_message.twist.linear
            angular = ros_message.twist.angular

            # Flatten linear and angular into a single list
            twist_values = [
                linear.x,
                linear.y,
                linear.z,
                angular.x,
                angular.y,
                angular.z,
            ]

            action = RobotAction(
                timestamp_ns=message.log_time,
                publish_time_ns=message.publish_time,
                values=twist_values,
                names=[
                    "linear_x",
                    "linear_y",
                    "linear_z",
                    "angular_x",
                    "angular_y",
                    "angular_z",
                ],
            )

            if topic_name not in actions:
                actions[topic_name] = []

            actions[topic_name].append(action)

        except Exception as e:
            self._log_extraction_error_once(topic_name, "TwistStamped", e)

    def _handle_wrench_stamped(
        self,
        topic_name: str,
        message: Message,
        ros_message: WrenchStamped,
        robot_states: dict[str, list[RobotState]],
    ) -> None:
        """Handle WrenchStamped message extraction."""
        try:
            force = ros_message.wrench.force
            torque = ros_message.wrench.torque

            wrench_values = [
                force.x,
                force.y,
                force.z,
                torque.x,
                torque.y,
                torque.z,
            ]

            robot_state = RobotState(
                timestamp_ns=message.log_time,
                publish_time_ns=message.publish_time,
                values=wrench_values,
                names=[
                    "force_x",
                    "force_y",
                    "force_z",
                    "torque_x",
                    "torque_y",
                    "torque_z",
                ],
            )

            if topic_name not in robot_states:
                robot_states[topic_name] = []

            robot_states[topic_name].append(robot_state)

        except Exception as e:
            self._log_extraction_error_once(topic_name, "WrenchStamped", e)

    def _handle_float32(
        self,
        topic_name: str,
        message: Message,
        ros_message: Float32,
        robot_states: dict[str, list[RobotState]],
        actions: dict[str, list[RobotAction]],
    ) -> None:
        """Handle Float32 message extraction."""
        if self._is_gripper_action(topic_name):
            self._handle_gripper_action(topic_name, message, ros_message, actions)
        elif self._is_gripper_state(topic_name):
            self._handle_gripper_state(topic_name, message, ros_message, robot_states)
        else:
            logger.info(f"Ignoring unsupported topic {topic_name} with schema std_msgs/msg/Float32")

    def _handle_float32_state(
        self,
        topic_name: str,
        message: Message,
        ros_message: Float32,
        robot_states: dict[str, list[RobotState]],
    ) -> None:
        """Handle Float32 message extraction for configured observation topics."""
        try:
            if topic_name not in robot_states:
                robot_states[topic_name] = []

            robot_state = RobotState(
                timestamp_ns=message.log_time,
                publish_time_ns=message.publish_time,
                names=["value"],
                values=[float(ros_message.data)],
            )

            robot_states[topic_name].append(robot_state)

        except Exception as e:
            logger.error(f"Failed to extract Float32 state from {topic_name}: {e}")

    def _handle_bool(
        self,
        topic_name: str,
        message: Message,
        ros_message: Bool,
        robot_states: dict[str, list[RobotState]],
    ) -> None:
        """Handle Bool message extraction."""
        try:
            if topic_name not in robot_states:
                robot_states[topic_name] = []

            robot_state = RobotState(
                timestamp_ns=message.log_time,
                publish_time_ns=message.publish_time,
                values=[1.0 if bool(ros_message.data) else -1.0],  # -1.0 for False, 1.0 for True
                names=["value"],  # Use hard coded topic name
            )

            robot_states[topic_name].append(robot_state)

        except Exception as e:
            logger.error(f"Failed to extract Bool state from {topic_name}: {e}")

    def _handle_gripper_action(
        self, topic_name: str, message: Message, ros_message: Float32, actions: dict[str, list[RobotAction]]
    ) -> None:
        """Handle gripper action message extraction."""
        try:
            if topic_name not in actions:
                actions[topic_name] = []

            action = RobotAction(
                timestamp_ns=message.log_time,
                publish_time_ns=message.publish_time,
                values=[float(ros_message.data)],
                names=["value"],
            )

            actions[topic_name].append(action)

        except Exception as e:
            logger.error(f"Failed to extract gripper action from {topic_name}: {e}")

    def _handle_gripper_state(
        self,
        topic_name: str,
        message: Message,
        ros_message: Float32,
        robot_states: dict[str, list[RobotState]],
    ) -> None:
        """Handle gripper state message extraction."""
        try:
            if topic_name not in robot_states:
                robot_states[topic_name] = []

            robot_state = RobotState(
                timestamp_ns=message.log_time,
                publish_time_ns=message.publish_time,
                names=["value"],
                values=[float(ros_message.data)],
            )

            robot_states[topic_name].append(robot_state)

        except Exception as e:
            logger.error(f"Failed to extract gripper state from {topic_name}: {e}")

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

    def _get_video_stats(self, topic: str, video: CompressedVideoInfo, metadata: dict[str, Any]) -> TopicStatistics:
        # This is all quite unstable and depends on the metadata being written correctly
        video_stream_details_json = metadata["video_stream_details"]["data"]
        video_stream_details = json.loads(video_stream_details_json)
        topic_metadata = video_stream_details[topic]
        duration_ms = topic_metadata["duration_ms"]
        duration_ns = int(duration_ms * 1e6)
        fps = topic_metadata["frame_rate"]

        return TopicStatistics(
            message_count=1,
            first_message_time_ns=video.timestamp_ns,
            last_message_time_ns=video.timestamp_ns + duration_ns,
            # We can't calculate gaps here, since we only have a video, not the individual frames
            gaps=[],
            fps=fps,
        )

    def _find_gaps(self, timestamps: list[int], gap_ns: int) -> list[tuple[int, int]]:
        gaps: list[tuple[int, int]] = []
        for prev, curr in pairwise(timestamps):
            if curr - prev > gap_ns:
                gaps.append((prev, curr))
        return gaps
