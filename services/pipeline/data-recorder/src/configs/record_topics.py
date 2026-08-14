"""Derive the recorder's topic set from the station embodiment.

Station is the single source of truth for which topics exist; this module only flattens the
embodiment into the list ``ros2 bag record`` subscribes to. Teleop inputs are remapped from each
leader topic to its follower target topic, so only the forwarded follower_topic is recorded.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pipeline_configs.station import StationConfig

_STATION_CONFIG_FILE = Path(os.getenv("STATION_CONFIG_FILE", "/workspace/config_station.yml"))


def _dedupe(topics: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for topic in topics:
        if topic not in seen:
            seen.add(topic)
            ordered.append(topic)
    return ordered


def build_record_topics(station: StationConfig) -> list[str]:
    """Compute the recording topic set from the station embodiment."""
    topics: list[str] = []
    embodiment = station.embodiment

    for entry in embodiment.other_topics or []:
        topics.extend(entry.config.topics)

    for robot in embodiment.teleop_robots or []:
        topics.append(robot.config.resolved_follower_topic)

    for device in embodiment.observer_devices or []:
        topics.extend(device.config.published_topics)

    return _dedupe(topics)


@lru_cache
def load_record_topics() -> list[str]:
    """Load the station config and derive the recording topic set; empty if no station config is mounted."""
    if not _STATION_CONFIG_FILE.exists():
        return []
    return build_record_topics(StationConfig.from_yaml(str(_STATION_CONFIG_FILE)))
