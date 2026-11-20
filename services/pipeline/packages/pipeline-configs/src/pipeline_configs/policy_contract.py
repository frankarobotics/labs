"""Policy I/O contract model: the flat state/action vector layout shared by the pipeline services."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

import numpy as np
from pydantic import (
    BaseModel,
    ConfigDict,
    PositiveInt,
    StringConstraints,
    model_validator,
)
from pydantic_yaml import parse_yaml_file_as

from pipeline_configs.ros_messages import ROSMessageType

POLICY_CONTRACT_FILE = Path(os.getenv("POLICY_CONTRACT_FILE", "/workspace/config_contract_gr00t.yml"))

# suffixes data-processor rewrites when it re-encodes an image stream, longest match first
_IMAGE_TOPIC_SUFFIXES = ("image_rect_color", "image_rect_raw", "image_raw")
_PROCESSED_VIDEO_SUFFIX = "compressed_video"

# LeRobot names a camera column by its policy_key; the checkpoint's input_features carry that same
# name back into inference, so recording and feeding must derive it from one place
_IMAGE_FEATURE_PREFIX = "observation.images."

# a camera/state/action policy_key reaches LeRobot verbatim, so it must need no sanitizing
SafePolicyKey = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_]+$")]


@dataclass(frozen=True)
class SegmentType:
    """How one ROS message type becomes a flat segment of the state or action vector."""

    elements: tuple[str, ...] = ()
    array_fields: frozenset[str] = frozenset()
    names_field: str = ""
    prefix: str = ""

    @property
    def resolves_by_name(self) -> bool:
        """Whether element names are matched against the message's own name list rather than read as paths."""
        return bool(self.names_field)


# fixed-layout types (elements/prefix) read named attribute paths off the message;
# array types (array_fields/names_field) read a parallel array reordered by matching published names
SEGMENT_TYPES: dict[ROSMessageType, SegmentType] = {
    ROSMessageType.FLOAT32: SegmentType(elements=("data",)),
    ROSMessageType.WRENCH_STAMPED: SegmentType(
        elements=("force.x", "force.y", "force.z", "torque.x", "torque.y", "torque.z"),
        prefix="wrench",
    ),
    ROSMessageType.JOINT_STATE: SegmentType(
        array_fields=frozenset({"position", "velocity", "effort"}),
        names_field="name",
    ),
}


class PolicySettings(BaseModel):
    """Rate and dtype every consumer of the contract shares."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # whole Hz: LeRobot stores fps as an integer and derives every frame timestamp from it
    control_rate_hz: PositiveInt
    dtype: Literal["float32", "float64"] = "float32"


class CameraSegment(BaseModel):
    """One camera input: the live image topic and the frame geometry the policy was trained on."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_key: SafePolicyKey
    topic: str
    shape: tuple[PositiveInt, PositiveInt, PositiveInt]
    # true stretches a differing source to shape, distorting aspect; false rejects it rather than scaling
    resize: bool

    @property
    def height(self) -> int:
        """Frame height the policy is fed."""
        return self.shape[0]

    @property
    def width(self) -> int:
        """Frame width the policy is fed."""
        return self.shape[1]

    @property
    def channels(self) -> int:
        """Channel count the policy is fed."""
        return self.shape[2]

    @property
    def dataset_topic(self) -> str:
        """Where data-processor's re-encode of ``topic`` lands in a processed episode."""
        for suffix in _IMAGE_TOPIC_SUFFIXES:
            if self.topic.endswith(suffix):
                return self.topic[: -len(suffix)] + _PROCESSED_VIDEO_SUFFIX
        return self.topic.rstrip("/") + "/" + _PROCESSED_VIDEO_SUFFIX

    @property
    def dataset_feature_name(self) -> str:
        """LeRobot column this camera records to, and the frame key the checkpoint's input_features expect."""
        return _IMAGE_FEATURE_PREFIX + self.policy_key


class PolicySegment(BaseModel):
    """One contiguous slice of the flat state or action vector, fed by a single topic."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_key: SafePolicyKey
    topic: str
    message_type: ROSMessageType
    field: str | None = None
    element_names: tuple[str, ...]

    @property
    def segment_type(self) -> SegmentType:
        """Layout rules for this segment's message type."""
        return SEGMENT_TYPES[self.message_type]

    @property
    def width(self) -> int:
        """Element count this segment contributes to the flat vector."""
        return len(self.element_names)

    @property
    def names_field(self) -> str:
        """Message member holding the names element_names are matched against, empty where they are paths."""
        return self.segment_type.names_field

    @property
    def resolves_by_name(self) -> bool:
        """Whether element names are matched against the message's own name list rather than read as paths."""
        return self.segment_type.resolves_by_name

    @property
    def element_paths(self) -> tuple[str, ...]:
        """Attribute path of each element from the message root, empty where elements resolve by name."""
        segment_type = self.segment_type
        if segment_type.resolves_by_name:
            return ()
        prefix = f"{segment_type.prefix}." if segment_type.prefix else ""
        return tuple(prefix + name for name in self.element_names)

    @model_validator(mode="before")
    @classmethod
    def _resolve_segment_type(cls, data: Any) -> Any:  # noqa: ANN401 - pydantic before-validator receives raw untyped input
        """A fixed-layout message defines its own elements, so naming them is optional - and a subset selects."""
        if not isinstance(data, dict):
            return data
        try:
            message_type = ROSMessageType(data.get("message_type"))
        except ValueError:
            return data  # an unknown message_type is reported by ordinary field validation
        segment_type = SEGMENT_TYPES.get(message_type)
        if segment_type is None:
            supported = ", ".join(sorted(known.value for known in SEGMENT_TYPES))
            raise ValueError(f"{message_type.value} cannot form a segment (supported: {supported})")
        if segment_type.resolves_by_name or data.get("element_names") is not None:
            return data
        return data | {"element_names": segment_type.elements}

    @model_validator(mode="after")
    def _check_elements_against_message_type(self) -> PolicySegment:
        """Elements a message type cannot supply are rejected rather than silently mis-decoded."""
        segment_type = self.segment_type
        if not self.element_names:
            raise ValueError(f"{self.policy_key!r}: element_names must not be empty")
        if len(set(self.element_names)) != len(self.element_names):
            raise ValueError(f"{self.policy_key!r}: element_names must be unique")

        # `field` picks between parallel arrays, so it applies exactly to types that have them
        if segment_type.array_fields:
            if self.field not in segment_type.array_fields:
                allowed = ", ".join(sorted(segment_type.array_fields))
                raise ValueError(f"{self.policy_key!r}: field must be one of {allowed}, got {self.field!r}")
        elif self.field is not None:
            raise ValueError(f"{self.policy_key!r}: field is meaningless for {self.message_type.value}")

        # names matched against the message are the robot's to define; paths must exist in the message
        if not segment_type.resolves_by_name:
            unknown = [name for name in self.element_names if name not in segment_type.elements]
            if unknown:
                defined = ", ".join(segment_type.elements)
                raise ValueError(
                    f"{self.policy_key!r}: {self.message_type.value} has no element "
                    f"{', '.join(unknown)} (defined: {defined})"
                )
        return self


class Annotation(BaseModel):
    """A non-topic column dataset-builder declares in the generated modality.json."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # not a SafePolicyKey: GR00T's annotation keys are dotted paths (human.action.task_description)
    policy_key: str
    original_key: str | None = None


class PolicyContract(BaseModel):
    """The ordered camera/state/action wiring between station topics and a policy's named arrays."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int
    policy: PolicySettings
    cameras: tuple[CameraSegment, ...]
    state: tuple[PolicySegment, ...]
    action: tuple[PolicySegment, ...]
    annotations: tuple[Annotation, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def _drop_anchor_definitions(cls, data: Any) -> Any:  # noqa: ANN401 - pydantic before-validator receives raw untyped input
        """Underscore-prefixed top-level keys carry YAML anchors only; anything else must be a known key."""
        if isinstance(data, dict):
            return {key: value for key, value in data.items() if not str(key).startswith("_")}
        return data

    @model_validator(mode="after")
    def _check_policy_keys_unique(self) -> PolicyContract:
        """policy_key names a segment in every downstream mapping, so a duplicate is ambiguous."""
        for label, keys in (
            ("cameras", self.camera_keys),
            ("state", self.state_keys),
            ("action", self.action_keys),
            ("annotations", tuple(annotation.policy_key for annotation in self.annotations)),
        ):
            duplicates = sorted({key for key in keys if keys.count(key) > 1})
            if duplicates:
                raise ValueError(f"duplicate {label} policy_key: {', '.join(duplicates)}")
        return self

    @property
    def camera_keys(self) -> tuple[str, ...]:
        """Camera policy keys in declaration order."""
        return tuple(camera.policy_key for camera in self.cameras)

    @property
    def state_keys(self) -> tuple[str, ...]:
        """State policy keys in flat-vector order."""
        return tuple(segment.policy_key for segment in self.state)

    @property
    def action_keys(self) -> tuple[str, ...]:
        """Action policy keys in flat-vector order."""
        return tuple(segment.policy_key for segment in self.action)

    @property
    def state_width(self) -> int:
        """Total length of the flat state vector."""
        return sum(segment.width for segment in self.state)

    @property
    def action_width(self) -> int:
        """Total length of the flat action vector."""
        return sum(segment.width for segment in self.action)

    @property
    def state_slices(self) -> dict[str, slice]:
        """Span of each state segment in the flat vector, in declaration order."""
        return _slices(self.state)

    @property
    def action_slices(self) -> dict[str, slice]:
        """Span of each action segment in the flat vector, in declaration order."""
        return _slices(self.action)

    def flatten_state(self, values_by_key: Mapping[str, Sequence[float] | np.ndarray]) -> np.ndarray:
        """Concatenate per-segment state values into the flat vector ``state_slices`` indexes into."""
        return self._flatten("state", self.state, values_by_key)

    def flatten_action(self, values_by_key: Mapping[str, Sequence[float] | np.ndarray]) -> np.ndarray:
        """Concatenate per-segment action values into the flat vector ``action_slices`` indexes into."""
        return self._flatten("action", self.action, values_by_key)

    def _flatten(
        self,
        label: str,
        segments: Sequence[PolicySegment],
        values_by_key: Mapping[str, Sequence[float] | np.ndarray],
    ) -> np.ndarray:
        """Assemble a flat vector in declaration order; a missing or mis-sized segment is fatal.

        Skipping or truncating one would shift every later segment off the span the checkpoint's
        ``modality.json`` reads it from, feeding the policy silently misaligned values.
        """
        parts: list[np.ndarray] = []
        for segment in segments:
            if segment.policy_key not in values_by_key:
                raise KeyError(f"{label} segment {segment.policy_key!r} declared by the contract is absent")
            vector = np.asarray(values_by_key[segment.policy_key], dtype=self.policy.dtype).reshape(-1)
            if vector.size != segment.width:
                raise ValueError(
                    f"{label} segment {segment.policy_key!r} supplied {vector.size} elements, expected {segment.width}"
                )
            parts.append(vector)
        return np.concatenate(parts) if parts else np.zeros(0, dtype=self.policy.dtype)

    @classmethod
    def from_yaml(cls, file_path: Path | str = POLICY_CONTRACT_FILE) -> PolicyContract:
        """Load and validate a contract from a YAML file."""
        return parse_yaml_file_as(cls, file_path)


def _slices(segments: Sequence[PolicySegment]) -> dict[str, slice]:
    """Concatenate segment widths into the flat vector spans each policy_key owns."""
    spans: dict[str, slice] = {}
    start = 0
    for segment in segments:
        spans[segment.policy_key] = slice(start, start + segment.width)
        start += segment.width
    return spans


def load_policy_contract(file_path: Path | str = POLICY_CONTRACT_FILE) -> PolicyContract:
    """Load the policy contract, defaulting to the POLICY_CONTRACT_FILE location."""
    return PolicyContract.from_yaml(file_path)
