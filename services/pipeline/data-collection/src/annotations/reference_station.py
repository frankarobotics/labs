"""Map the FR3 Duo reference station using its existing policy I/O contract.

Camera topic rewriting and named joint selection follow dataset-builder's
CameraSegment.dataset_topic and segment_decoder conventions. Robot commands
remain in the recording but are never substituted for measured state.
"""

import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from foxglove_schemas_protobuf.PoseInFrame_pb2 import PoseInFrame
from mcap.reader import make_reader
from mcap.records import Channel, Message, Schema
from mcap.writer import Writer
from mcap_protobuf.schema import register_schema
from mcap_ros2.decoder import DecoderFactory
from numpy.typing import NDArray
from pipeline_configs import PolicyContract, PolicySegment, ROSMessageType

from annotations.frames import recorded_arm_bases
from annotations.kinematics import flange_transform, orientation_xyzw
from annotations.signals import signal_type

# robotiq_gripper_client.py documents this joint's URDF range: 0 open, 0.8 closed.
KNUCKLE_MAX_RADIANS = 0.8
KNUCKLE_NAME = "robotiq_85_left_knuckle_joint"
CAMERA_ROLES = {"head": "front", "wrist_left": "wrist_left", "wrist_right": "wrist_right"}
STATE_UNITS = {
    "arm_position": "rad",
    "arm_velocity": "rad/s",
    "gripper_position": "rad",
    "arm_external_joint_torque": "N*m",
    "arm_external_wrench": None,  # Mixed units: force is N; torque is N*m.
}
STATE_FIELDS = {
    "arm_position": "position",
    "arm_velocity": "velocity",
    "gripper_position": "position",
    "arm_external_joint_torque": "effort",
    "arm_external_wrench": None,
}


@dataclass(frozen=True)
class SignalBinding:
    """One measured contract segment and its destination in the prepared copy."""

    segment: PolicySegment
    closedness: bool = False
    label: str | None = None
    unit: str | None = None
    scalar: bool = False
    command: bool = False

    @property
    def name(self) -> str:
        """Keep the measured angle distinct from normalized gripper closedness."""
        if self.label:
            return self.label
        if self.segment.policy_key.endswith("gripper_position"):
            suffix = "gripper_closed" if self.closedness else "gripper_angle"
            return self.segment.policy_key.replace("gripper_position", suffix)
        return self.segment.policy_key

    @property
    def channel(self) -> str:
        """Namespace converted measurements under /nomadic/labs/."""
        return f"/nomadic/labs/{self.name}"

    def declaration(self) -> dict[str, Any]:
        """Declare signal dimensions, components and measurement units."""
        declaration: dict[str, Any] = {"name": self.name, "channel": self.channel}
        if self.closedness:
            return declaration | {
                "type": "float",
                "unit": "1",
                "note": "Measured Robotiq closedness: angle_rad / 0.8; 0 fully open, 1 fully closed.",
            }
        suffix = self.segment.policy_key.split("_", 1)[1]
        components = list(self.segment.element_names)
        if self.segment.message_type == ROSMessageType.WRENCH_STAMPED:
            components = ["fx", "fy", "fz", "tx", "ty", "tz"]
        if self.scalar or "gripper" in self.segment.policy_key:
            declaration.update(type="float")
        else:
            declaration.update(type="vector", dim=self.segment.width, components=components)
        if unit := self.unit or STATE_UNITS.get(suffix):
            declaration["unit"] = unit
        origin = "Commanded" if self.command else "Measured"
        declaration["note"] = (
            f"{origin} {self.segment.topic}; field {self.segment.field or 'wrench'}; capture timestamp where available."
        )
        if suffix == "arm_external_wrench":
            declaration["note"] += " Force in N, torque in N*m; retained in the source stiffness frame."
        return declaration


def _values(segment: PolicySegment, message: Any) -> list[float]:  # noqa: ANN401 -- Decoded ROS payload.
    """Select by contract names, including the broadcaster's underscore namespace prefix."""
    if segment.resolves_by_name:
        names, values = list(message.name), list(getattr(message, str(segment.field)))
        if len(names) != len(values):
            raise ValueError(f"{segment.policy_key}: joint names and {segment.field} lengths differ.")
        result = []
        for name in segment.element_names:
            matches = [i for i, published in enumerate(names) if published == name or published.endswith(f"_{name}")]
            if len(matches) != 1:
                raise ValueError(f"{segment.policy_key}: expected exactly one recorded joint matching {name}.")
            result.append(float(values[matches[0]]))
    else:
        result = []
        for path in segment.element_paths:
            value = message
            for attribute in path.split("."):
                value = getattr(value, attribute)
            result.append(float(value))
    if not all(math.isfinite(value) for value in result):
        raise ValueError(f"{segment.policy_key}: a measurement is not finite.")
    return result


class ReferenceStationMapping:
    """Convert explicitly declared FR3 Duo measurements, retaining their original clocks."""

    def __init__(self, contract_path: Path, source_topics: set[str]) -> None:
        """Read the existing reference contract; reject incompatible layouts before writing."""
        self.contract = PolicyContract.from_yaml(contract_path)
        self.bindings = self._bindings()
        self._add_available_signals(source_topics)
        cameras = {camera.policy_key: camera for camera in self.contract.cameras}
        if set(cameras) != set(CAMERA_ROLES):
            raise ValueError("The FR3 Duo mapping requires head, wrist_left and wrist_right contract cameras.")
        self.spec: dict[str, Any] = {
            "spec_version": "1.1",
            "recording": {
                "platform": {"kind": "manipulator", "embodiment": "franka_fr3_bimanual", "parts": self._parts()}
            },
            "primary_view": cameras["head"].dataset_topic,
            "views": [
                {"channel": camera.dataset_topic, "role": CAMERA_ROLES[camera.policy_key]}
                for camera in self.contract.cameras
            ],
            "signals": [binding.declaration() for binding in self.bindings],
            "source": {
                "pose_note": "Derived nominal FR3 flange poses, not measured gripper TCP poses.",
                "geometry_note": "Arm-base placement follows recorded /tf_static; physical calibration is unverified.",
                "timestamp_note": "ROS capture stamps; MCAP log_time for messages without a header.",
            },
        }
        required = {camera.dataset_topic for camera in self.contract.cameras}
        required.update(binding.segment.topic for binding in self.bindings)
        if missing := required - source_topics:
            raise ValueError(
                f"Recording does not match the configured LABS contract; missing channels: {', '.join(sorted(missing))}"
            )
        if source_topics & {binding.channel for binding in self.bindings}:
            raise ValueError("The recording already contains reference signal channels; use its embedded Nomadic spec.")
        self._by_topic: dict[str, list[SignalBinding]] = defaultdict(list)
        for binding in self.bindings:
            self._by_topic[binding.segment.topic].append(binding)
        self._decoder = DecoderFactory()
        self._signal: Any = signal_type()
        self._channels: dict[str, int] = {}
        self._counts: dict[str, int] = defaultdict(int)
        self._times: dict[str, int] = {}
        self._schema_id: int | None = None
        self._pose_schema: int | None = None
        self._pose_channels: dict[str, int] = {}
        self._base_frame = ""
        self._base_transforms: dict[str, NDArray[np.float64]] = {}

    def configure_frames(self, source: Path) -> list[str]:
        """Express both poses in their recorded common frame, retaining calibration limits."""
        self._base_frame, self._base_transforms = recorded_arm_bases(source)
        self.spec["source"].update(
            arm_base_frame=self._base_frame,
            arm_base_transforms={
                side: {"translation_m": matrix[:3, 3].tolist(), "rotation_xyzw": orientation_xyzw(matrix)}
                for side, matrix in self._base_transforms.items()
            },
            arm_base_calibration="unverified",
            geometry_note=(
                f"Flange poses use recorded /tf_static transforms in {self._base_frame!r}; "
                "physical arm placement and camera extrinsics are unverified."
            ),
        )
        if np.allclose(self._base_transforms["left"], self._base_transforms["right"], rtol=0, atol=1e-9):
            return ["Recorded arm bases coincide; trajectories show nominal placement, not calibrated arm spacing."]
        return []

    def _bindings(self) -> list[SignalBinding]:
        by_key = {segment.policy_key: segment for segment in self.contract.state}
        expected = {f"{side}_{suffix}" for side in ("left", "right") for suffix in STATE_UNITS}
        if set(by_key) != expected:
            raise ValueError("The configured contract is not the supported FR3 Duo reference state layout.")
        bindings = []
        for segment in self.contract.state:
            suffix = segment.policy_key.split("_", 1)[1]
            is_wrench = segment.policy_key.endswith("external_wrench")
            expected_type = ROSMessageType.WRENCH_STAMPED if is_wrench else ROSMessageType.JOINT_STATE
            if segment.message_type != expected_type:
                raise ValueError(f"{segment.policy_key}: unexpected ROS message type for the FR3 Duo mapping.")
            if segment.field != STATE_FIELDS[suffix]:
                raise ValueError(f"{segment.policy_key}: expected measured field {STATE_FIELDS[suffix]}.")
            if suffix in {
                "arm_position",
                "arm_velocity",
                "arm_external_joint_torque",
            } and segment.element_names != tuple(f"fr3_joint{i}" for i in range(1, 8)):
                raise ValueError(f"{segment.policy_key}: the reference arm requires its seven named FR3 joints.")
            if is_wrench and segment.element_names != (
                "force.x",
                "force.y",
                "force.z",
                "torque.x",
                "torque.y",
                "torque.z",
            ):
                raise ValueError(f"{segment.policy_key}: the full reference wrench is required.")
            if "gripper" in segment.policy_key and segment.element_names != (KNUCKLE_NAME,):
                raise ValueError("The reference gripper mapping requires the Robotiq 2F-85 knuckle joint.")
            bindings.append(SignalBinding(segment))
            if "gripper" in segment.policy_key:
                bindings.append(SignalBinding(segment, closedness=True))
        return bindings

    def _parts(self) -> list[dict[str, Any]]:
        return [
            {
                "name": f"{side}_arm",
                "type": "arm",
                "side": side,
                "end_pose": {"channel": f"/nomadic/labs/{side}_flange_pose"},
                "grip": {"signal": f"{side}_gripper_closed"},
                "force": {"signal": f"{side}_arm_external_wrench"},
            }
            for side in ("left", "right")
        ]

    def copy_signals(self, writer: Writer, schema: Schema | None, channel: Channel, message: Message) -> None:
        """Add converted measurements alongside the unchanged ROS messages."""
        bindings = self._by_topic.get(channel.topic)
        if not bindings:
            return
        expected = bindings[0].segment.message_type.value.replace("/", "/msg/", 1)
        if schema is None or schema.name != expected or channel.message_encoding != "cdr":
            raise ValueError(f"{channel.topic}: expected {expected} with ROS 2 CDR encoding.")
        decode = self._decoder.decoder_for(channel.message_encoding, schema)
        if decode is None:
            raise ValueError(f"{channel.topic}: the recorded ROS schema cannot be decoded.")
        decoded = decode(message.data)
        timestamp = capture_time(decoded, message.log_time)
        if timestamp <= self._times.get(channel.topic, -1):
            raise ValueError(f"{channel.topic}: capture timestamps must be strictly increasing.")
        self._times[channel.topic] = timestamp
        if self._schema_id is None:
            self._schema_id = register_schema(writer, self._signal)
        for binding in bindings:
            values = _values(binding.segment, decoded)
            signal = self._signal_value(binding, values, timestamp)
            if binding.name not in self._channels:
                self._channels[binding.name] = writer.register_channel(binding.channel, "protobuf", self._schema_id)
            writer.add_message(
                self._channels[binding.name],
                timestamp,
                signal.SerializeToString(),
                publish_time=message.publish_time,
                sequence=message.sequence,
            )
            self._counts[binding.name] += 1
            if binding.name.endswith("_arm_position"):
                self._write_pose(writer, binding.name.split("_", 1)[0], values, timestamp)

    def _signal_value(self, binding: SignalBinding, values: list[float], timestamp: int) -> Any:  # noqa: ANN401 -- Dynamic protobuf.
        """Encode measured values; Nomadic's grip consumer expects larger values for closure."""
        signal = self._signal()
        signal.timestamp.seconds, signal.timestamp.nanos = divmod(timestamp, 1_000_000_000)
        if binding.closedness:
            if not 0 <= values[0] <= KNUCKLE_MAX_RADIANS:
                raise ValueError(
                    f"{binding.segment.topic}: measured angle is outside the reference Robotiq 0-0.8 rad range."
                )
            signal.number = values[0] / KNUCKLE_MAX_RADIANS
        elif binding.scalar or "gripper" in binding.segment.policy_key:
            signal.number = values[0]
        else:
            signal.vector.values.extend(values)
        if binding.command and binding.scalar and not 0 <= values[0] <= 1:
            raise ValueError(f"{binding.segment.topic}: commanded opening must be between 0 and 1.")
        return signal

    def _add_available_signals(self, topics: set[str]) -> None:
        """Include recorded state extras and contract commands as separate signals."""
        for segment in self.contract.state:
            if segment.policy_key.endswith("arm_position"):
                self.bindings.append(
                    SignalBinding(
                        segment.model_copy(update={"field": "effort"}),
                        label=segment.policy_key.replace("position", "torque"),
                        unit="N*m",
                    )
                )
            elif segment.policy_key.endswith("gripper_position"):
                self.bindings.append(
                    SignalBinding(
                        segment.model_copy(update={"field": "velocity"}),
                        label=segment.policy_key.replace("position", "velocity"),
                        unit="rad/s",
                        scalar=True,
                    )
                )
        for segment in self.contract.action:
            if segment.topic in topics:
                gripper = "gripper" in segment.policy_key
                name = segment.policy_key.replace("gripper_position", "gripper_width") + "_command"
                self.bindings.append(
                    SignalBinding(segment, label=name, unit="1" if gripper else "rad", scalar=gripper, command=True)
                )

    def _write_pose(self, writer: Writer, side: str, joints: list[float], timestamp: int) -> None:
        if self._pose_schema is None:
            self._pose_schema = register_schema(writer, PoseInFrame)
        if side not in self._pose_channels:
            self._pose_channels[side] = writer.register_channel(
                f"/nomadic/labs/{side}_flange_pose", "protobuf", self._pose_schema
            )
        if not self._base_frame:
            raise ValueError("Recorded arm-base transforms must be configured before writing flange poses.")
        transform = self._base_transforms[side] @ flange_transform(joints)
        pose = PoseInFrame(frame_id=self._base_frame)
        pose.timestamp.seconds, pose.timestamp.nanos = divmod(timestamp, 1_000_000_000)
        pose.pose.position.x, pose.pose.position.y, pose.pose.position.z = map(float, transform[:3, 3])
        pose.pose.orientation.x, pose.pose.orientation.y, pose.pose.orientation.z, pose.pose.orientation.w = (
            orientation_xyzw(transform)
        )
        writer.add_message(self._pose_channels[side], timestamp, pose.SerializeToString(), publish_time=timestamp)

    def validate_complete(self) -> None:
        """Require samples for every declared measurement."""
        if missing := [binding.name for binding in self.bindings if not self._counts[binding.name]]:
            raise ValueError(f"The recording has no samples for declared measurements: {', '.join(missing)}")

    def write_signals(self, writer: Writer, source: Path) -> None:
        """Read only mapped ROS channels and append measured signals in timestamp order."""
        with source.open("rb") as handle:
            for schema, channel, message in make_reader(handle).iter_messages(topics=sorted(self._by_topic)):
                self.copy_signals(writer, schema, channel, message)
        self.validate_complete()


def capture_time(message: Any, fallback: int) -> int:  # noqa: ANN401
    """Use capture time where present, and recorder time for headerless commands."""
    header = getattr(message, "header", None)
    if header is None:
        return fallback
    stamp = header.stamp
    timestamp = int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)
    if timestamp <= 0 or not 0 <= stamp.nanosec < 1_000_000_000:  # noqa: PLR2004
        raise ValueError("ROS capture timestamps must be positive and valid.")
    return timestamp
