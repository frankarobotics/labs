from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from pipeline_configs.policy_contract import CameraSegment, PolicyContract, PolicySegment, load_policy_contract

DEPLOYMENT_CONTRACT = Path(__file__).parents[5] / "deployments/fr3_duo_example/config_contract_gr00t.yml"

FR3_JOINTS = [f"fr3_joint{index}" for index in range(1, 8)]


def _segment(**overrides: Any) -> PolicySegment:
    return PolicySegment.model_validate({"policy_key": "k", "topic": "/t"} | overrides)


def _camera(**overrides: Any) -> CameraSegment:
    defaults = {"policy_key": "cam", "topic": "/cam/color/image_raw", "shape": [480, 640, 3], "resize": False}
    return CameraSegment.model_validate(defaults | overrides)


def _minimal_contract() -> dict[str, Any]:
    return {
        "version": 1,
        "policy": {"control_rate_hz": 20, "dtype": "float32"},
        "cameras": [{"policy_key": "head", "topic": "/cam/color/image_raw", "shape": [480, 640, 3], "resize": False}],
        "state": [
            {
                "policy_key": "arm_position",
                "topic": "/arm/joint_states",
                "message_type": "sensor_msgs/JointState",
                "field": "position",
                "element_names": FR3_JOINTS,
            }
        ],
        "action": [{"policy_key": "gripper", "topic": "/gripper/target", "message_type": "std_msgs/Float32"}],
    }


def test_deployment_contract_loads() -> None:
    contract = PolicyContract.from_yaml(DEPLOYMENT_CONTRACT)

    assert contract.state_width == 56
    assert contract.action_width == 16
    assert len(contract.cameras) == 3


def test_load_policy_contract_accepts_an_explicit_path() -> None:
    assert load_policy_contract(DEPLOYMENT_CONTRACT).version == 1


@pytest.mark.parametrize("group", ["state", "action"])
def test_deployment_slices_are_contiguous_and_ordered(group: str) -> None:
    contract = PolicyContract.from_yaml(DEPLOYMENT_CONTRACT)
    segments: tuple[PolicySegment, ...] = getattr(contract, group)
    spans: dict[str, slice] = getattr(contract, f"{group}_slices")

    expected_start = 0
    for segment in segments:
        span = spans[segment.policy_key]
        assert span.start == expected_start
        assert span.stop - span.start == segment.width
        expected_start = span.stop
    assert expected_start == getattr(contract, f"{group}_width")


@pytest.mark.parametrize(
    ("message_type", "extra", "expected_width"),
    [
        ("std_msgs/Float32", {}, 1),
        ("geometry_msgs/WrenchStamped", {}, 6),
        ("sensor_msgs/JointState", {"field": "effort", "element_names": FR3_JOINTS}, 7),
    ],
)
def test_width_is_derived_from_message_type(message_type: str, extra: dict[str, Any], expected_width: int) -> None:
    assert _segment(message_type=message_type, **extra).width == expected_width


def test_width_cannot_be_declared() -> None:
    with pytest.raises(ValidationError, match="width"):
        _segment(message_type="std_msgs/Float32", width=1)


def test_fixed_layout_element_names_default_to_the_whole_message() -> None:
    segment = _segment(message_type="geometry_msgs/WrenchStamped")

    assert segment.element_names == ("force.x", "force.y", "force.z", "torque.x", "torque.y", "torque.z")


def test_fixed_layout_element_names_may_select_a_subset() -> None:
    segment = _segment(message_type="geometry_msgs/WrenchStamped", element_names=["force.x", "force.y", "force.z"])

    assert segment.width == 3
    assert segment.element_paths == ("wrench.force.x", "wrench.force.y", "wrench.force.z")


def test_fixed_layout_rejects_an_element_the_message_does_not_define() -> None:
    with pytest.raises(ValidationError, match="has no element force.w"):
        _segment(message_type="geometry_msgs/WrenchStamped", element_names=["force.w"])


def test_field_rejected_on_fixed_layout_types() -> None:
    with pytest.raises(ValidationError, match="meaningless"):
        _segment(message_type="geometry_msgs/WrenchStamped", field="position")


def test_name_resolved_segments_expose_the_names_field_and_no_paths() -> None:
    segment = _segment(message_type="sensor_msgs/JointState", field="position", element_names=FR3_JOINTS)

    assert segment.names_field == "name"
    assert segment.element_paths == ()


@pytest.mark.parametrize("message_type", ["std_msgs/Float32", "geometry_msgs/WrenchStamped"])
def test_path_resolved_segments_have_no_names_field(message_type: str) -> None:
    assert _segment(message_type=message_type).names_field == ""


def test_joint_state_requires_element_names() -> None:
    with pytest.raises(ValidationError, match="element_names"):
        _segment(message_type="sensor_msgs/JointState", field="position")


def test_joint_state_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError, match="field must be one of"):
        _segment(message_type="sensor_msgs/JointState", field="acceleration", element_names=FR3_JOINTS)


def test_joint_state_requires_explicit_field() -> None:
    with pytest.raises(ValidationError, match="field must be one of"):
        _segment(message_type="sensor_msgs/JointState", element_names=FR3_JOINTS)


def test_duplicate_element_names_rejected() -> None:
    with pytest.raises(ValidationError, match="unique"):
        _segment(message_type="sensor_msgs/JointState", field="position", element_names=["fr3_joint1", "fr3_joint1"])


def test_empty_element_names_rejected() -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        _segment(message_type="sensor_msgs/JointState", field="position", element_names=[])


def test_message_type_without_a_segment_layout_is_rejected() -> None:
    with pytest.raises(ValidationError, match="cannot form a segment"):
        _segment(message_type="geometry_msgs/TwistStamped")


def test_unknown_message_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _segment(message_type="sensor_msgs/Imu")


def test_anchor_definitions_are_ignored() -> None:
    raw = _minimal_contract()
    raw["_definitions"] = {"fr3_joints": FR3_JOINTS}

    assert PolicyContract.model_validate(raw).state_width == 7


def test_unknown_top_level_key_is_rejected() -> None:
    raw = _minimal_contract()
    raw["observation_adapter"] = {}

    with pytest.raises(ValidationError, match="observation_adapter"):
        PolicyContract.model_validate(raw)


def test_duplicate_policy_key_is_rejected() -> None:
    raw = _minimal_contract()
    raw["action"] = raw["action"] * 2

    with pytest.raises(ValidationError, match="duplicate action policy_key"):
        PolicyContract.model_validate(raw)


@pytest.mark.parametrize(
    ("topic", "expected"),
    [
        ("/cam/color/image_raw", "/cam/color/compressed_video"),
        ("/zed/zed_node/rgb/image_rect_color", "/zed/zed_node/rgb/compressed_video"),
        ("/cam/color/image_rect_raw", "/cam/color/compressed_video"),
        ("/cam/color/frames", "/cam/color/frames/compressed_video"),
    ],
)
def test_dataset_topic_derivation(topic: str, expected: str) -> None:
    assert _camera(topic=topic).dataset_topic == expected


def test_camera_shape_is_height_width_channels() -> None:
    camera = _camera(shape=[360, 640, 3], resize=True)

    assert (camera.height, camera.width, camera.channels) == (360, 640, 3)


def test_camera_rejects_non_positive_shape() -> None:
    with pytest.raises(ValidationError):
        _camera(shape=[0, 640, 3])


def test_deployment_contract_declares_no_widths() -> None:
    raw = yaml.safe_load(DEPLOYMENT_CONTRACT.read_text())

    for group in ("state", "action"):
        assert all("width" not in segment for segment in raw[group])
