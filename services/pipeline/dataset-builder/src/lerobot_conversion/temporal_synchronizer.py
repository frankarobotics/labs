"""Temporal Synchronizer for aligning video, robot states, and actions at a target FPS."""

from typing import Any

import numpy as np
from loguru import logger
from scipy import interpolate

from models.extracted_mcap_data import ExtractedMcapData
from models.observation import Observation
from models.observation_action import ObservationAction
from models.observation_image import ObservationImage
from models.observation_state import ObservationState
from models.robot_action import RobotAction
from models.robot_state import RobotState
from models.topic_statistics import TopicStatistics
from models.video_frame import VideoFrame

START_TIME_TOLERANCE_NS = int(1 * 1e9)  # 1 second
END_TIME_TOLERANCE_NS = int(1 * 1e9)  # 1 second


class SynchronizationError(RuntimeError):
    """Raised when the multi-modal data cannot be temporally aligned."""


class TemporalSynchronizer:
    """Synchronize multi-modal data to a common target-FPS timebase."""

    def __init__(self, target_fps: float = 20.0) -> None:
        """Initialize temporal synchronizer.

        Args:
            target_fps: Target sampling frequency in Hz
        """
        self.target_fps: float = target_fps
        self.frame_interval_ns = int(1e9 / target_fps)  # Nanoseconds between frames

        logger.info(f"TemporalSynchronizer initialized at {target_fps} Hz ({self.frame_interval_ns}ns intervals)")

    def synchronize_episode_data(
        self,
        videos: dict[str, list[VideoFrame]],
        extracted_data: ExtractedMcapData,
    ) -> list[Observation]:
        """Synchronize all modalities to target-FPS aligned timestamps.

        Args:
            videos: Dict of topic names to lists of video frames with timestamps.
            extracted_data: ExtractedMcapData object containing robot states and actions.

        Returns:
            List of synchronized observation/action pairs at target FPS
        """
        logger.info("Starting temporal synchronization...")

        start_time_ns = self._get_start_time_ns(
            extracted_data.video_topics, extracted_data.robot_state_topics, extracted_data.action_topics
        )

        first_message_time_ns = self._get_first_message_time_ns(
            extracted_data.video_topics, extracted_data.robot_state_topics, extracted_data.action_topics
        )

        self._check_start_time(start_time_ns, first_message_time_ns)

        end_time_ns = self._get_end_time_ns(
            extracted_data.video_topics, extracted_data.robot_state_topics, extracted_data.action_topics
        )

        last_message_time_ns = self._get_last_message_time_ns(
            extracted_data.video_topics, extracted_data.robot_state_topics, extracted_data.action_topics
        )

        self._check_end_time(end_time_ns, last_message_time_ns)

        duration_ns = end_time_ns - start_time_ns

        logger.info(f"Time bounds: {start_time_ns} to {end_time_ns} ({duration_ns / 1e9:.3f}s)")

        # Generate target-FPS timestamp grid
        num_samples: int = int(duration_ns / self.frame_interval_ns) + 1
        target_timestamps_ns = np.linspace(start_time_ns, end_time_ns, num_samples, dtype=np.int64)

        logger.info(f"Generating {len(target_timestamps_ns)} samples at {self.target_fps} Hz")

        # Synchronize each modality
        sync_videos = self._synchronize_videos(videos, target_timestamps_ns)
        sync_robot_states = self._synchronize_robot_states(extracted_data.robot_states, target_timestamps_ns)
        sync_actions = self._synchronize_actions(extracted_data.actions, target_timestamps_ns)

        # Combine into unified data structure
        synchronized_data: list[Observation] = []

        for i, timestamp_ns in enumerate(target_timestamps_ns):
            # Add video frame

            image = {}
            for topic, video in sync_videos.items():
                if i < len(video):
                    image[topic] = video[i]

            state = {}

            # Add robot states
            for topic, states in sync_robot_states.items():
                if i < len(states):
                    state[topic] = states[i]

            action = {}

            # Add actions
            for topic, topic_actions in sync_actions.items():
                if i < len(topic_actions):
                    action[topic] = topic_actions[i]

            observation = Observation(
                timestamp_ns=timestamp_ns - target_timestamps_ns[0],  # Relative to start of episode
                frame_index=i,
                episode_index=0,  # Will be set by caller
                image=image,
                state=state,
                action=action,
            )

            synchronized_data.append(observation)

        logger.info(f"Generated {len(synchronized_data)} synchronized observations")
        return synchronized_data

    def _get_start_time_ns(
        self,
        video_stats: dict[str, TopicStatistics],
        robot_state_stats: dict[str, TopicStatistics],
        action_stats: dict[str, TopicStatistics],
    ) -> int:
        """Get the earliest timestamp from which all topics started to send data."""
        start_times: list[int] = []

        if video_stats:
            start_times.append(max(stats.first_message_time_ns for stats in video_stats.values() if stats))
        if robot_state_stats:
            start_times.append(max(stats.first_message_time_ns for stats in robot_state_stats.values() if stats))
        if action_stats:
            start_times.append(max(stats.first_message_time_ns for stats in action_stats.values() if stats))

        if not start_times:
            raise SynchronizationError("No topic statistics available to determine start time")

        return max(start_times)

    def _get_first_message_time_ns(
        self,
        video_stats: dict[str, TopicStatistics],
        robot_state_stats: dict[str, TopicStatistics],
        action_stats: dict[str, TopicStatistics],
    ) -> int:
        """Get the absolute earliest timestamp from any topic."""
        first_times: list[int] = []

        if video_stats:
            first_times.append(min(stats.first_message_time_ns for stats in video_stats.values() if stats))
        if robot_state_stats:
            first_times.append(min(stats.first_message_time_ns for stats in robot_state_stats.values() if stats))
        if action_stats:
            first_times.append(min(stats.first_message_time_ns for stats in action_stats.values() if stats))

        if not first_times:
            raise SynchronizationError("No topic statistics available to determine first message time")

        return min(first_times)

    def _check_start_time(self, start_time_ns: int, first_message_time_ns: int) -> None:
        if abs(start_time_ns - first_message_time_ns) > START_TIME_TOLERANCE_NS:
            logger.error(
                f"Synchronized start time {start_time_ns} is more than 1s after first message time "
                f"{first_message_time_ns}"
                f" (difference: {(start_time_ns - first_message_time_ns) / 1e9:.3f} s)"
            )

            raise SynchronizationError("Synchronized start time is too far from first message time")

    def _get_end_time_ns(
        self,
        video_stats: dict[str, TopicStatistics],
        robot_state_stats: dict[str, TopicStatistics],
        action_stats: dict[str, TopicStatistics],
    ) -> int:
        """Get the earliest timestamp from which all topics stopped to send data."""
        end_times: list[int] = []

        if video_stats:
            end_times.append(min(stats.last_message_time_ns for stats in video_stats.values() if stats))
        if robot_state_stats:
            end_times.append(min(stats.last_message_time_ns for stats in robot_state_stats.values() if stats))
        if action_stats:
            end_times.append(min(stats.last_message_time_ns for stats in action_stats.values() if stats))

        if not end_times:
            raise SynchronizationError("No topic statistics available to determine end time")

        return min(end_times)

    def _get_last_message_time_ns(
        self,
        video_stats: dict[str, TopicStatistics],
        robot_state_stats: dict[str, TopicStatistics],
        action_stats: dict[str, TopicStatistics],
    ) -> int:
        """Get the absolute latest timestamp from any topic."""
        last_times: list[int] = []

        if video_stats:
            last_times.append(max(stats.last_message_time_ns for stats in video_stats.values() if stats))
        if robot_state_stats:
            last_times.append(max(stats.last_message_time_ns for stats in robot_state_stats.values() if stats))
        if action_stats:
            last_times.append(max(stats.last_message_time_ns for stats in action_stats.values() if stats))

        if not last_times:
            raise SynchronizationError("No topic statistics available to determine last message time")

        return max(last_times)

    def _check_end_time(self, end_time_ns: int, last_message_time_ns: int) -> None:
        if abs(end_time_ns - last_message_time_ns) > END_TIME_TOLERANCE_NS:
            logger.error(
                f"Synchronized end time {end_time_ns} is more than 1s before last message time "
                f"{last_message_time_ns}"
                f" (difference: {(end_time_ns - last_message_time_ns) / 1e9:.3f} s)"
            )

            raise SynchronizationError("Synchronized end time is too far from last message time")

    def _synchronize_videos(
        self, videos: dict[str, list[VideoFrame]], target_timestamps_ns: np.ndarray
    ) -> dict[str, list[ObservationImage]]:
        """Synchronize multiple video streams to target timestamps.

        Args:
            videos: Dict of topic names to original video frames
            target_timestamps_ns: Target timestamp grid

        Returns:
            Dict of topic names to synchronized frame data
        """
        synchronized_videos: dict[str, list[ObservationImage]] = {}

        for topic, frames in videos.items():
            logger.info(f"Synchronizing video topic: {topic} ({len(frames)} frames)")
            sync_frames = self._synchronize_frames(frames, target_timestamps_ns)
            synchronized_videos[topic] = sync_frames

        return synchronized_videos

    def _synchronize_frames(self, frames: list[VideoFrame], target_timestamps_ns: np.ndarray) -> list[ObservationImage]:
        """Synchronize video frames to target timestamps.

        Args:
            frames: Original video frames
            target_timestamps_ns: Target timestamp grid

        Returns:
            Synchronized frame data
        """
        if not frames:
            return []

        # Extract frame timestamps
        frame_times = np.array([frame.timestamp_ns for frame in frames])

        synchronized_frames: list[ObservationImage] = []

        for target_timestamp_ns in target_timestamps_ns:
            # Find closest frame by timestamp
            closest_idx = np.argmin(np.abs(frame_times - target_timestamp_ns))

            # Use closest frame (no interpolation for images)
            sync_frame = ObservationImage(
                image=frames[closest_idx].image,
                width=frames[closest_idx].width,
                height=frames[closest_idx].height,
                original_timestamp_ns=frames[closest_idx].timestamp_ns,
                sync_timestamp_ns=target_timestamp_ns,
                time_diff_ms=abs(target_timestamp_ns - frames[closest_idx].timestamp_ns) / 1e6,
            )

            synchronized_frames.append(sync_frame)

        return synchronized_frames

    def _synchronize_robot_states(
        self, robot_states: dict[str, list[RobotState]], target_timestamps_ns: np.ndarray
    ) -> dict[str, list[ObservationState]]:
        """Synchronize robot state data using interpolation.

        Args:
            robot_states: Robot state data by topic
            target_timestamps_ns: Target timestamp grid

        Returns:
            Synchronized robot state data
        """
        synchronized_states: dict[str, list[ObservationState]] = {}

        for topic, states in robot_states.items():
            logger.info(f"Synchronizing robot state topic: {topic} ({len(states)} samples)")

            # Extract timestamps
            state_times = np.array([state.timestamp_ns for state in states])

            # Interpolate values (joint positions, orientation, etc)
            # Collect values into a typed list first, then convert to numpy array
            values: list[list[float]] = []
            for state in states:
                # state.values is expected to be an iterable of numeric types
                values.append([float(x) for x in state.values])

            values_array = np.array(values, dtype=float)

            # Create interpolators for each value dimension
            interpolators = []
            for values_idx in range(values_array.shape[1]):
                values_at_idx = values_array[:, values_idx]
                interp = interpolate.interp1d(
                    state_times,
                    values_at_idx,
                    kind="linear",
                    bounds_error=False,
                    fill_value=(values_at_idx[0], values_at_idx[-1]),
                )
                interpolators.append(interp)

            # Interpolate to target timestamps
            sync_states: list[ObservationState] = []
            for target_timestamp_ns in target_timestamps_ns:
                interpolated_positions: list[float] = [float(interp(target_timestamp_ns)) for interp in interpolators]

                sync_state = ObservationState(
                    timestamp_ns=target_timestamp_ns,
                    values=interpolated_positions,
                    names=states[0].names if states else [],
                )
                sync_states.append(sync_state)

            synchronized_states[topic] = sync_states

        return synchronized_states

    def _synchronize_actions(
        self, actions: dict[str, list[RobotAction]], target_timestamps_ns: np.ndarray
    ) -> dict[str, list[ObservationAction]]:
        """Synchronize action data using interpolation.

        Args:
            actions: Action data by topic
            target_timestamps_ns: Target timestamp grid

        Returns:
            Synchronized action data
        """
        synchronized_actions: dict[str, list[ObservationAction]] = {}

        for topic, topic_actions in actions.items():
            logger.info(f"Synchronizing action topic: {topic} ({len(topic_actions)} samples)")

            # Extract timestamps and action values
            action_times = np.array([action.timestamp_ns for action in topic_actions])
            action_values: list[list[float]] = []
            for action in topic_actions:
                action_values.append([float(x) for x in action.values])
            action_values_array = np.array(action_values, dtype=float)

            # Create interpolators for each value dimension
            interpolators = []
            for values_idx in range(action_values_array.shape[1]):
                values_at_idx = action_values_array[:, values_idx]
                interp = interpolate.interp1d(
                    action_times,
                    values_at_idx,
                    kind="linear",
                    bounds_error=False,
                    fill_value=(values_at_idx[0], values_at_idx[-1]),
                )
                interpolators.append(interp)

            # Interpolate to target timestamps
            sync_actions: list[ObservationAction] = []
            for target_timestamp_ns in target_timestamps_ns:
                interpolated_values = [float(interp(target_timestamp_ns)) for interp in interpolators]
                sync_action = ObservationAction(
                    timestamp_ns=target_timestamp_ns,
                    values=interpolated_values,
                    names=topic_actions[0].names if topic_actions else [],
                )
                sync_actions.append(sync_action)

            synchronized_actions[topic] = sync_actions

        return synchronized_actions

    def calculate_synchronization_stats(self, observations: list[Observation]) -> dict[str, Any]:
        """Calculate statistics about synchronization quality.

        Args:
            observations: List of synchronized observations

        Returns:
            Synchronization quality statistics
        """
        if not observations:
            return {}

        stats: dict[str, Any] = {
            "total_samples": len(observations),
            "duration_seconds": (observations[-1].timestamp_ns - observations[0].timestamp_ns) / 1e9,
            "actual_fps": len(observations) / ((observations[-1].timestamp_ns - observations[0].timestamp_ns) / 1e9),
            "target_fps": self.target_fps,
        }

        image_time_diffs: dict[str, list[float]] = {}
        for observation in observations:
            for topic in observation.image:
                if topic not in image_time_diffs:
                    image_time_diffs[topic] = []
                image = observation.image[topic]
                time_diff_ms = image.time_diff_ms
                image_time_diffs[topic].append(time_diff_ms)

        stats["image_sync"] = {
            topic: {
                "mean_error_ms": float(np.mean(diffs)),
                "max_error_ms": float(np.max(diffs)),
                "std_error_ms": float(np.std(diffs)),
            }
            for topic, diffs in image_time_diffs.items()
        }

        logger.info(f"Synchronization stats: {stats}")
        return stats
