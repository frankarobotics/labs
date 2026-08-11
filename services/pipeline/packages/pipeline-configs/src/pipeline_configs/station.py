"""Station configuration model, shared across the pipeline services."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator, model_validator
from pydantic_yaml import parse_yaml_file_as


class Metadata(BaseModel):
    """Metadata for the station configuration."""

    station_id: str


class ROSMessageType(Enum):
    """Enumeration of supported message types."""

    TWIST_STAMPED = "geometry_msgs/Twist Message"
    JOINT_STATE = "sensor_msgs/JointState"
    FLOAT32 = "std_msgs/Float32"


class Identity(BaseModel):
    """Transformation for the identity input."""

    type: Literal["identity"]


class Noop(BaseModel):
    """Transformation for the noop input."""

    type: Literal["noop"]


class TeleopRobotConfig(BaseModel):
    """Configuration for a teleoperation robot (config field)."""

    model_config = ConfigDict(
        use_enum_values=True,  # Use enum values for serialization
        from_attributes=True,
    )

    namespace: str
    ros_message_type: ROSMessageType
    leader_topic: str
    leader_device: str
    transformations: list[Noop | Identity] | None = None
    follower_topic: str
    follower_device: str
    observer_topics: list[str] | None = None

    def resolve_topic(self, topic: str) -> str:
        """Resolve a topic to an absolute ROS2 topic path.

        Topics in config are namespace-relative (e.g. "leader/gello/joint_states").
        This prepends "/{namespace}/" to produce the full path. If the topic is
        already absolute (starts with "/"), it is returned as-is.
        """
        if not topic:
            return topic
        if topic.startswith("/"):
            return topic
        ns = self.namespace.strip("/")
        return f"/{ns}/{topic}" if ns else f"/{topic}"

    @property
    def resolved_follower_topic(self) -> str:
        """Absolute topic carrying this robot's follower (action) stream."""
        return self.resolve_topic(self.follower_topic)


class TeleopRobot(BaseModel):
    """Configuration for a teleoperation robot in the station (with config key)."""

    id: str
    type: str
    config: TeleopRobotConfig

    @field_validator("config", mode="before")
    @classmethod
    def validate_config(cls, v: dict[str, Any], info: ValidationInfo) -> TeleopRobotConfig:
        """Validate and parse the config field for TeleopRobot."""
        return TeleopRobotConfig.model_validate(v)


class ObserverConfig(BaseModel):
    """Base for observer device configs."""

    model_config = ConfigDict(from_attributes=True)

    @property
    def published_topics(self) -> list[str]:
        """Every ROS topic this device publishes."""
        raise NotImplementedError


class CameraStreamConfig(BaseModel):
    """One camera stream; the field name it is bound to carries the role (rgb, depth, info)."""

    topic: str


class CameraConfig(ObserverConfig):
    """Base for camera observer configs, whose streams are optional named fields."""

    @property
    def published_topics(self) -> list[str]:
        """Every ROS topic this device publishes derived from the declared fields."""
        streams = (getattr(self, name) for name in type(self).model_fields)
        return [stream.topic for stream in streams if isinstance(stream, CameraStreamConfig)]


class RealSenseCameraConfig(CameraConfig):
    """Configuration for a RealSense camera observer device (with optional rgb, depth and info)."""

    rgb: CameraStreamConfig | None = None
    depth: CameraStreamConfig | None = None
    info: CameraStreamConfig | None = None


class ZedCameraConfig(CameraConfig):
    """Configuration for a ZED camera observer device.

    Configure either ``rgb`` for a single rectified stream,
    or ``rgb_left`` and ``rgb_right`` for both stereo streams.
    """

    rgb: CameraStreamConfig | None = None
    rgb_left: CameraStreamConfig | None = None
    rgb_right: CameraStreamConfig | None = None
    info: CameraStreamConfig | None = None

    @model_validator(mode="after")
    def check_stream_config(self) -> ZedCameraConfig:
        """Validate that either rgb or both rgb_left/rgb_right are set, not both."""
        has_mono = self.rgb is not None
        has_stereo = self.rgb_left is not None or self.rgb_right is not None
        if has_mono and has_stereo:
            raise ValueError("Set either 'rgb' or both 'rgb_left'/'rgb_right', not both.")
        if has_stereo and (self.rgb_left is None or self.rgb_right is None):
            raise ValueError("Both 'rgb_left' and 'rgb_right' must be set for stereo.")
        return self


class RobotObserverConfig(ObserverConfig):
    """Configuration for a robot observer device."""

    topics: list[str]

    @property
    def published_topics(self) -> list[str]:
        """Every ROS topic this device publishes."""
        return self.topics


class ObserverDevice(BaseModel):
    """Configuration for an observer device."""

    id: str
    type: str
    config: RealSenseCameraConfig | ZedCameraConfig | RobotObserverConfig

    @field_validator("config", mode="before")
    @classmethod
    def validate_config(
        cls, v: dict[str, str], info: ValidationInfo
    ) -> RealSenseCameraConfig | ZedCameraConfig | RobotObserverConfig:
        """Validate and parse the config field based on the type field."""
        t: str | None = info.data.get("type")
        if t == "REALSENSE_CAMERA":
            return RealSenseCameraConfig.model_validate(v)
        if t == "ZED_CAMERA":
            return ZedCameraConfig.model_validate(v)
        if t == "ROBOT_OBSERVER":
            return RobotObserverConfig.model_validate(v)
        raise ValueError(f"Unknown observer device type: {t}")


class OtherTopicsConfig(BaseModel):
    """Configuration for a plain list of ROS topics (config field)."""

    model_config = ConfigDict(from_attributes=True)

    topics: list[str]


class OtherTopics(BaseModel):
    """Topics bound to no device: recorded as-is and never mapped into a dataset.

    ``ROS_INFRA`` covers the ROS graph topics every station publishes, ``USER_TOPICS``
    anything else a deployment wants in its recordings.
    """

    id: str
    type: Literal["ROS_INFRA", "USER_TOPICS"]
    config: OtherTopicsConfig

    @field_validator("config", mode="before")
    @classmethod
    def validate_config(cls, v: dict[str, Any], info: ValidationInfo) -> OtherTopicsConfig:
        """Validate and parse the config field for OtherTopics."""
        return OtherTopicsConfig.model_validate(v)


class Embodiment(BaseModel):
    """Configuration for the embodiment."""

    teleop_robots: list[TeleopRobot] | None = None
    observer_devices: list[ObserverDevice] | None = None
    other_topics: list[OtherTopics] | None = None

    @staticmethod
    def _validate_ids(ids: list[str], section: str) -> None:
        """Validate that IDs within a section are unique and contain no '-' or whitespace."""
        if len(ids) != len(set(ids)):
            raise ValueError(f"All {section} must have unique IDs.")
        for id_ in ids:
            if "-" in id_ or " " in id_:
                raise ValueError(f"Invalid ID '{id_}': IDs must not contain '-' or whitespace.")

    def _validate_teleop_robot_namespace_pairs(self) -> None:
        """Validate that (namespace, follower_device) pairs are unique across teleop robots."""
        namespace_actuator_pairs: dict[tuple[str, str], str] = {}
        for robot in self.teleop_robots or []:
            pair = (robot.config.namespace, robot.config.follower_device)
            if pair in namespace_actuator_pairs:
                raise ValueError(
                    f"All teleop_robots must have unique (namespace, follower_device) pairs. "
                    f"Robots with IDs '{namespace_actuator_pairs[pair]}' and '{robot.id}' "
                    f"share the same namespace '{pair[0]}' and follower_device '{pair[1]}'."
                )
            namespace_actuator_pairs[pair] = robot.id

    def model_post_init(self, __context: dict[str, Any] | None = None) -> None:
        """Post-initialization validation."""
        if self.teleop_robots:
            self._validate_ids([robot.id for robot in self.teleop_robots], "teleop_robots")
            self._validate_teleop_robot_namespace_pairs()

        if self.observer_devices:
            self._validate_ids([device.id for device in self.observer_devices], "observer_devices")

        if self.other_topics:
            self._validate_ids([entry.id for entry in self.other_topics], "other_topics")


class StationConfig(BaseModel):
    """Configuration for the station."""

    STATION_CONFIG_PATH: str = "config_station.yml"
    metadata: Metadata
    embodiment: Embodiment

    @classmethod
    def from_yaml(cls, file_path: str = STATION_CONFIG_PATH) -> StationConfig:
        """Load station configuration from a YAML file.

        Args:
            file_path: Path to the YAML configuration file. Defaults to STATION_CONFIG_PATH.

        Returns:
            A StationConfig instance loaded from the YAML file.
        """
        return parse_yaml_file_as(cls, file_path)


def load_station_config() -> StationConfig:
    """Load station configuration from a YAML file.

    Returns:
        A StationConfig instance loaded from the YAML file.
    """
    return StationConfig.from_yaml()
