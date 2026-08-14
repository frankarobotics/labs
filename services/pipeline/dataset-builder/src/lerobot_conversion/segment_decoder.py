"""Decoding of one policy-contract segment out of a recorded ROS message."""

from typing import Any

from pipeline_configs import PolicySegment, ROSMessageType

# MCAP schema names are fully qualified (sensor_msgs/msg/JointState); the contract uses the short form
MCAP_SCHEMA_NAMES: dict[ROSMessageType, str] = {
    message_type: message_type.value.replace("/", "/msg/", 1) for message_type in ROSMessageType
}

COMPRESSED_VIDEO_SCHEMA_NAME = "foxglove.CompressedVideo"


class SegmentDecodeError(ValueError):
    """Raised when a recorded message cannot supply a segment's declared elements."""


def decode_segment(segment: PolicySegment, message: Any) -> list[float]:  # noqa: ANN401 - decoded ROS message
    """Read a segment's elements out of a decoded ROS message, in flat-vector order."""
    if segment.resolves_by_name:
        return _decode_by_name(segment, message)
    return [float(_resolve_path(segment, message, path)) for path in segment.element_paths]


def _decode_by_name(segment: PolicySegment, message: Any) -> list[float]:  # noqa: ANN401
    """Reorder one of a message's parallel arrays to the segment's element order."""
    if segment.field is None:  # the contract model pairs `field` with every names_field type
        raise SegmentDecodeError(f"{segment.policy_key!r}: {segment.message_type.value} needs a field to read")

    published_names = [str(name) for name in _resolve_path(segment, message, segment.names_field)]
    values = list(_resolve_path(segment, message, segment.field))
    if len(values) != len(published_names):
        raise SegmentDecodeError(
            f"{segment.policy_key!r}: {segment.topic} published {len(published_names)} "
            f"{segment.names_field} entries but {len(values)} {segment.field} values"
        )

    # Publishers may prefix contract names with an underscore-delimited robot namespace.
    matches_by_name = {
        name: [
            index
            for index, published in enumerate(published_names)
            if published == name or published.endswith(f"_{name}")
        ]
        for name in segment.element_names
    }
    missing = [name for name, matches in matches_by_name.items() if not matches]
    if missing:
        raise SegmentDecodeError(
            f"{segment.policy_key!r}: {segment.topic} published no {segment.field} for "
            f"{', '.join(missing)} (published: {', '.join(published_names)})"
        )
    ambiguous = [name for name, matches in matches_by_name.items() if len(matches) > 1]
    if ambiguous:
        raise SegmentDecodeError(
            f"{segment.policy_key!r}: {segment.topic} name {', '.join(ambiguous)} matches more than one of "
            f"{', '.join(published_names)}"
        )
    return [float(values[matches_by_name[name][0]]) for name in segment.element_names]


def _resolve_path(segment: PolicySegment, message: Any, path: str) -> Any:  # noqa: ANN401
    """Walk a dotted attribute path from the message root."""
    node = message
    for attribute in path.split("."):
        try:
            node = getattr(node, attribute)
        except AttributeError as exc:
            raise SegmentDecodeError(
                f"{segment.policy_key!r}: {segment.topic} payload has no {path}, "
                f"so it is not the declared {segment.message_type.value}"
            ) from exc
    return node
