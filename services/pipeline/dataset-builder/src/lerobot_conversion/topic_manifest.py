"""Config-driven topic manifest for dataset extraction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypeVar

import yaml
from loguru import logger

TopicRole = Literal["image", "state", "action", "ignored"]
TopicMappedData = TypeVar("TopicMappedData")


@dataclass(frozen=True)
class DatasetTopicManifest:
    """Ordered topic manifest derived from station and recorder configs."""

    observation_image_topics: tuple[str, ...]
    observation_state_topics: tuple[str, ...]
    action_topics: tuple[str, ...]
    observation_image_aliases: dict[str, str]
    observation_state_aliases: dict[str, str]
    ignored_topics: frozenset[str]
    recorder_topics: frozenset[str]

    def classify_topic(self, topic_name: str) -> TopicRole | None:
        """Return the dataset role for a topic if it is part of the manifest."""
        if topic_name in self.ignored_topics:
            return "ignored"
        if topic_name in self.observation_image_topics:
            return "image"
        if topic_name in self.observation_state_topics:
            return "state"
        if topic_name in self.action_topics:
            return "action"
        return None

    def order_topics(
        self,
        values_by_topic: dict[str, TopicMappedData],
        ordered_topics: tuple[str, ...],
    ) -> dict[str, TopicMappedData]:
        """Return a dict ordered by the manifest topic order, keeping only configured topics."""
        return {topic: values_by_topic[topic] for topic in ordered_topics if topic in values_by_topic}

    def order_image_topics(self, values_by_topic: dict[str, TopicMappedData]) -> dict[str, TopicMappedData]:
        """Order image topics according to the manifest."""
        return self.order_topics(values_by_topic, self.observation_image_topics)

    def order_state_topics(self, values_by_topic: dict[str, TopicMappedData]) -> dict[str, TopicMappedData]:
        """Order observation state topics according to the manifest."""
        return self.order_topics(values_by_topic, self.observation_state_topics)

    def order_action_topics(self, values_by_topic: dict[str, TopicMappedData]) -> dict[str, TopicMappedData]:
        """Order action topics according to the manifest."""
        return self.order_topics(values_by_topic, self.action_topics)

    def get_image_alias(self, topic_name: str) -> str:
        """Return the configured alias for an image topic."""
        return self.observation_image_aliases.get(topic_name, _to_safe_name(topic_name))

    def get_state_alias(self, topic_name: str) -> str:
        """Return the configured alias for an observation state topic."""
        return self.observation_state_aliases.get(topic_name, _to_safe_name(topic_name))


def load_topic_manifest(  # noqa: C901
    station_config_path: Path | None,
    recorder_config_path: Path | None,
) -> DatasetTopicManifest | None:
    """Load an ordered topic manifest from station and recorder configs."""
    if station_config_path is None:
        if recorder_config_path is not None:
            logger.warning("Recorder config provided without station config; falling back to schema heuristics")
        return None

    station_config = _load_yaml_file(station_config_path)
    recorder_topics = _load_recorder_topics(recorder_config_path)

    embodiment = station_config.get("embodiment", {})
    teleop_robots = embodiment.get("teleop_robots") or []
    observer_devices = embodiment.get("observer_devices") or []

    observation_image_topics: list[str] = []
    observation_state_topics: list[str] = []
    action_topics: list[str] = []
    ignored_topics: list[str] = []
    observation_image_aliases: dict[str, str] = {}
    observation_state_aliases: dict[str, str] = {}

    for observer in observer_devices:
        observer_id = str(observer.get("id", "observer"))
        observer_type = observer.get("type")
        config = observer.get("config", {})

        if observer_type in {"REALSENSE_CAMERA", "ZED_CAMERA"}:
            image_topics_with_aliases = _extract_image_topics(config, observer_id)
            for topic, alias in image_topics_with_aliases:
                observation_image_topics.append(topic)
                observation_image_aliases.setdefault(topic, alias)
        elif observer_type == "ROBOT_OBSERVER":
            for topic in config.get("topics") or []:
                observation_state_topics.append(topic)
                observation_state_aliases.setdefault(str(topic), _build_state_alias(observer_id, str(topic)))

    for teleop_robot in teleop_robots:
        config = teleop_robot.get("config", {})
        namespace = config.get("namespace")

        leader_topic = config.get("leader_topic")
        if leader_topic:
            ignored_topics.append(_apply_namespace(namespace, str(leader_topic)))

        follower_topic = config.get("follower_topic")
        if follower_topic:
            action_topics.append(_apply_namespace(namespace, str(follower_topic)))

        for observer_topic in config.get("observer_topics") or []:
            namespaced_topic = _apply_namespace(namespace, str(observer_topic))
            observation_state_topics.append(namespaced_topic)
            observation_state_aliases.setdefault(namespaced_topic, _to_safe_name(namespaced_topic))

    observation_image_topics = _deduplicate_preserve_order(observation_image_topics)
    observation_state_topics = _deduplicate_preserve_order(observation_state_topics)
    action_topics = _deduplicate_preserve_order(action_topics)
    ignored_topics = _deduplicate_preserve_order(ignored_topics)

    if recorder_topics:
        observation_image_topics = _filter_recorded_topics(
            observation_image_topics, recorder_topics, "observation image"
        )
        observation_state_topics = _filter_recorded_topics(
            observation_state_topics, recorder_topics, "observation state"
        )
        action_topics = _filter_recorded_topics(action_topics, recorder_topics, "action")

    observation_image_topic_pairs = [
        (_to_processed_video_topic(topic), observation_image_aliases[topic]) for topic in observation_image_topics
    ]
    observation_image_topics = _deduplicate_preserve_order([topic for topic, _ in observation_image_topic_pairs])
    observation_image_aliases = {
        topic: alias for topic, alias in observation_image_topic_pairs if topic in observation_image_topics
    }
    observation_state_aliases = {
        topic: observation_state_aliases[topic]
        for topic in observation_state_topics
        if topic in observation_state_aliases
    }

    return DatasetTopicManifest(
        observation_image_topics=tuple(observation_image_topics),
        observation_state_topics=tuple(observation_state_topics),
        action_topics=tuple(action_topics),
        observation_image_aliases=observation_image_aliases,
        observation_state_aliases=observation_state_aliases,
        ignored_topics=frozenset(ignored_topics),
        recorder_topics=frozenset(recorder_topics),
    )


def _load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, encoding="utf-8") as file_handle:
        raw = yaml.safe_load(file_handle) or {}

    if not isinstance(raw, dict):
        raise ValueError(f"Expected mapping at top level for config file: {path}")

    return raw


def _load_recorder_topics(path: Path | None) -> set[str]:
    if path is None:
        return set()

    recorder_config = _load_yaml_file(path)
    ros_topics = recorder_config.get("ros_topics") or []

    if not isinstance(ros_topics, list):
        raise ValueError(f"Expected ros_topics to be a list in recorder config: {path}")

    return {str(topic) for topic in ros_topics}


def _extract_image_topics(config: dict[str, Any], observer_id: str) -> list[tuple[str, str]]:
    topic_configs: list[tuple[str, str]] = []
    for config_name, value in config.items():
        if isinstance(value, dict) and isinstance(value.get("topic"), str):
            topic_configs.append((value["topic"], _build_camera_alias(observer_id, str(config_name), config)))
    return topic_configs


def _deduplicate_preserve_order(topics: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered_topics: list[str] = []
    for topic in topics:
        if topic not in seen:
            seen.add(topic)
            ordered_topics.append(topic)
    return ordered_topics


def _filter_recorded_topics(topics: list[str], recorder_topics: set[str], label: str) -> list[str]:
    filtered_topics: list[str] = []
    for topic in topics:
        if topic in recorder_topics:
            filtered_topics.append(topic)
        else:
            logger.warning(f"Skipping configured {label} topic not present in recorder config: {topic}")
    return filtered_topics


def _apply_namespace(namespace: str | None, topic: str) -> str:
    """Resolve a teleop topic to its absolute, namespaced form.

    Teleop ``leader_topic``/``follower_topic`` entries are relative (e.g.
    ``follower/gello/joint_states``) and rely on the robot's ``namespace`` to
    form the recorded topic (e.g. ``/left/follower/gello/joint_states``).
    Topics that are already absolute are returned unchanged.
    """
    topic = topic.strip()
    if topic.startswith("/"):
        return topic
    if not namespace:
        return f"/{topic}"
    return f"/{namespace.strip('/')}/{topic}"


def _build_camera_alias(observer_id: str, config_name: str, config: dict[str, Any]) -> str:
    image_config_names = [
        name for name, value in config.items() if isinstance(value, dict) and isinstance(value.get("topic"), str)
    ]
    if len(image_config_names) == 1:
        return _to_safe_name(observer_id)
    return _to_safe_name(f"{observer_id}_{config_name}")


def _build_state_alias(observer_id: str, topic_name: str) -> str:
    topic_suffix = topic_name.rstrip("/").rsplit("/", maxsplit=1)[-1]
    return _to_safe_name(f"{observer_id}_{topic_suffix}")


def _to_processed_video_topic(topic_name: str) -> str:
    suffixes_to_replace = ("image_raw", "image_rect_raw", "image_rect_color")

    for suffix in suffixes_to_replace:
        if topic_name.endswith(suffix):
            return topic_name[: -len(suffix)] + "compressed_video"

    return topic_name.rstrip("/") + "/compressed_video"


def _to_safe_name(value: str) -> str:
    return value.lstrip("/").replace("/", "_").replace(".", "_")
