from types import SimpleNamespace

import pytest
from pipeline_configs import PolicySegment, ROSMessageType

from lerobot_conversion.segment_decoder import MCAP_SCHEMA_NAMES, SegmentDecodeError, decode_segment


def _segment(**overrides: object) -> PolicySegment:
    return PolicySegment.model_validate({"policy_key": "key", "topic": "/topic"} | overrides)


def _joint_state(names: list[str], **arrays: list[float]) -> SimpleNamespace:
    return SimpleNamespace(name=names, **arrays)


def test_joint_state_is_reordered_to_element_names() -> None:
    segment = _segment(
        message_type="sensor_msgs/JointState", field="position", element_names=["joint1", "joint2", "joint3"]
    )
    message = _joint_state(["joint3", "joint1", "joint2"], position=[3.0, 1.0, 2.0])

    assert decode_segment(segment, message) == [1.0, 2.0, 3.0]


def test_field_selects_between_parallel_arrays() -> None:
    message = _joint_state(["joint1", "joint2"], position=[1.0, 2.0], velocity=[10.0, 20.0], effort=[100.0, 200.0])

    for field, expected in (("position", [1.0, 2.0]), ("velocity", [10.0, 20.0]), ("effort", [100.0, 200.0])):
        segment = _segment(message_type="sensor_msgs/JointState", field=field, element_names=["joint1", "joint2"])
        assert decode_segment(segment, message) == expected


def test_element_names_may_select_a_subset() -> None:
    segment = _segment(message_type="sensor_msgs/JointState", field="position", element_names=["joint2"])
    message = _joint_state(["joint1", "joint2", "joint3"], position=[1.0, 2.0, 3.0])

    assert decode_segment(segment, message) == [2.0]


def test_element_name_matches_after_an_underscore_delimited_prefix() -> None:
    """A dual-arm station's franka_robot_state_broadcaster publishes "left_fr3_joint1", not the contract's bare name."""
    segment = _segment(message_type="sensor_msgs/JointState", field="position", element_names=["joint1", "joint2"])
    message = _joint_state(["left_joint2", "left_joint1"], position=[2.0, 1.0])

    assert decode_segment(segment, message) == [1.0, 2.0]


def test_element_name_does_not_match_a_longer_joint_name() -> None:
    segment = _segment(message_type="sensor_msgs/JointState", field="position", element_names=["joint1"])
    message = _joint_state(["joint10"], position=[10.0])

    with pytest.raises(SegmentDecodeError, match="no position for joint1"):
        decode_segment(segment, message)


def test_a_name_matching_more_than_one_published_name_is_reported() -> None:
    segment = _segment(message_type="sensor_msgs/JointState", field="position", element_names=["joint1"])
    message = _joint_state(["left_joint1", "right_joint1"], position=[1.0, 2.0])

    with pytest.raises(SegmentDecodeError, match="matches more than one of"):
        decode_segment(segment, message)


def test_a_missing_joint_is_reported_rather_than_mis_decoded() -> None:
    segment = _segment(message_type="sensor_msgs/JointState", field="position", element_names=["joint1", "gripper"])
    message = _joint_state(["joint1", "joint2"], position=[1.0, 2.0])

    with pytest.raises(SegmentDecodeError, match="no position for gripper"):
        decode_segment(segment, message)


def test_parallel_arrays_of_unequal_length_are_rejected() -> None:
    segment = _segment(message_type="sensor_msgs/JointState", field="velocity", element_names=["joint1", "joint2"])
    message = _joint_state(["joint1", "joint2"], velocity=[])

    with pytest.raises(SegmentDecodeError, match="2 name entries but 0 velocity values"):
        decode_segment(segment, message)


def test_wrench_elements_resolve_as_paths_from_the_message_root() -> None:
    segment = _segment(message_type="geometry_msgs/WrenchStamped")
    message = SimpleNamespace(
        wrench=SimpleNamespace(force=SimpleNamespace(x=1.0, y=2.0, z=3.0), torque=SimpleNamespace(x=4.0, y=5.0, z=6.0))
    )

    assert segment.element_paths == (
        "wrench.force.x",
        "wrench.force.y",
        "wrench.force.z",
        "wrench.torque.x",
        "wrench.torque.y",
        "wrench.torque.z",
    )
    assert decode_segment(segment, message) == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]


def test_a_subset_of_a_fixed_layout_message_keeps_its_declared_order() -> None:
    segment = _segment(message_type="geometry_msgs/WrenchStamped", element_names=["force.z", "force.x"])
    message = SimpleNamespace(wrench=SimpleNamespace(force=SimpleNamespace(x=1.0, y=2.0, z=3.0)))

    assert decode_segment(segment, message) == [3.0, 1.0]


def test_float32_yields_its_single_value() -> None:
    segment = _segment(message_type="std_msgs/Float32")

    assert decode_segment(segment, SimpleNamespace(data=0.75)) == [0.75]


def test_a_payload_of_another_type_is_reported() -> None:
    segment = _segment(message_type="geometry_msgs/WrenchStamped")

    with pytest.raises(SegmentDecodeError, match=r"has no wrench\.force\.x"):
        decode_segment(segment, SimpleNamespace(data=1.0))


def test_decoded_width_always_matches_the_declared_width() -> None:
    segment = _segment(message_type="sensor_msgs/JointState", field="position", element_names=["joint1", "joint2"])
    message = _joint_state(["joint2", "extra", "joint1"], position=[2.0, 9.0, 1.0])

    assert len(decode_segment(segment, message)) == segment.width


def test_mcap_schema_names_are_the_ros2_form_of_every_contract_type() -> None:
    assert MCAP_SCHEMA_NAMES[ROSMessageType.JOINT_STATE] == "sensor_msgs/msg/JointState"
    assert MCAP_SCHEMA_NAMES[ROSMessageType.WRENCH_STAMPED] == "geometry_msgs/msg/WrenchStamped"
    assert set(MCAP_SCHEMA_NAMES) == set(ROSMessageType)
