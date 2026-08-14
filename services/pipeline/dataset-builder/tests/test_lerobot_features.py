from typing import Any

import pytest
from pipeline_configs import PolicyContract

from lerobot_conversion.lerobot_features import build_features, build_modality_config

VIDEO_INFOS: dict[str, dict[str, Any]] = {
    "head": {"video.height": 480, "video.width": 640, "video.channels": 3, "video.codec": "av1"},
    "wrist": {"video.height": 480, "video.width": 640, "video.channels": 3, "video.codec": "av1"},
}


@pytest.fixture
def features(contract: PolicyContract) -> dict[str, Any]:
    return build_features(contract, VIDEO_INFOS)


def test_every_state_segment_gets_a_feature_of_its_own_width(
    features: dict[str, Any], contract: PolicyContract
) -> None:
    for segment in contract.state:
        feature = features[f"observation.state.{segment.policy_key}"]
        assert feature.shape == (segment.width,)
        assert feature.names == list(segment.element_names)


def test_flat_features_match_the_contract_widths(features: dict[str, Any], contract: PolicyContract) -> None:
    assert features["observation.state"].shape == (contract.state_width,)
    assert features["action"].shape == (contract.action_width,)
    assert len(features["observation.state"].names) == contract.state_width
    assert len(features["action"].names) == contract.action_width


def test_flat_feature_names_are_prefixed_by_their_segment(features: dict[str, Any]) -> None:
    assert features["observation.state"].names[:3] == [
        "arm_position_joint1",
        "arm_position_joint2",
        "arm_velocity_joint1",
    ]
    assert features["action"].names == ["arm_joint1", "arm_joint2", "gripper_data"]


def test_policy_columns_use_the_contract_dtype(features: dict[str, Any]) -> None:
    assert features["observation.state"].dtype == "float32"
    assert features["action"].dtype == "float32"
    assert features["observation.state.arm_wrench"].dtype == "float32"


def test_cameras_become_video_features(features: dict[str, Any]) -> None:
    assert features["observation.images.head"].dtype == "video"
    assert features["observation.images.wrist"].shape == (480, 640, 3)


def test_annotations_come_from_the_contract(features: dict[str, Any]) -> None:
    assert features["annotation.human.action.task_description"].dtype == "int64"
    assert features["annotation.human.validity"].shape == (1,)


def test_modality_state_spans_are_contiguous_and_cover_the_vector(contract: PolicyContract) -> None:
    modality = build_modality_config(contract)

    assert [(seg.name, seg.start, seg.end) for seg in modality.state_segments] == [
        ("arm_position", 0, 2),
        ("arm_velocity", 2, 4),
        ("arm_wrench", 4, 10),
    ]
    assert modality.total_state_dims == contract.state_width


def test_modality_action_spans_follow_the_contract(contract: PolicyContract) -> None:
    modality = build_modality_config(contract)

    assert [(seg.name, seg.start, seg.end) for seg in modality.action_segments] == [
        ("arm", 0, 2),
        ("gripper", 2, 3),
    ]
    assert modality.total_action_dims == contract.action_width


def test_modality_video_entries_point_at_the_parquet_feature_names(contract: PolicyContract) -> None:
    modality = build_modality_config(contract)

    assert {entry.key: entry.original_key for entry in modality.video_entries} == {
        "head": "observation.images.head",
        "wrist": "observation.images.wrist",
    }


def test_modality_round_trips_through_the_wire_format(contract: PolicyContract) -> None:
    serialized = build_modality_config(contract).to_dict()

    assert serialized["state"]["arm_velocity"] == {"start": 2, "end": 4}
    assert serialized["annotation"] == {
        "human.action.task_description": {"original_key": "task_index"},
        "human.validity": {},
    }
