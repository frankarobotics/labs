from pathlib import Path

import pytest
from pipeline_configs import PolicyContract

from lerobot_conversion.policy_manifest import PolicyManifest, load_policy_manifest


def test_one_topic_feeds_every_segment_that_declares_it(manifest: PolicyManifest) -> None:
    segments = manifest.state_by_topic["/arm/joint_states"]

    assert [segment.policy_key for segment in segments] == ["arm_position", "arm_velocity"]
    assert [segment.field for segment in segments] == ["position", "velocity"]


def test_cameras_are_keyed_by_their_processed_episode_topic(manifest: PolicyManifest) -> None:
    assert set(manifest.cameras_by_topic) == {
        "/head/zed_node/rgb/compressed_video",
        "/wrist/camera/color/compressed_video",
    }
    assert manifest.cameras_by_topic["/head/zed_node/rgb/compressed_video"][0].policy_key == "head"


def test_state_and_action_topics_are_separate(manifest: PolicyManifest) -> None:
    assert "/follower/joint_states" in manifest.action_by_topic
    assert "/follower/joint_states" not in manifest.state_by_topic
    assert "/arm/joint_states" not in manifest.action_by_topic


def test_keys_follow_contract_declaration_order(manifest: PolicyManifest) -> None:
    assert manifest.camera_keys == ("head", "wrist")
    assert manifest.state_keys == ("arm_position", "arm_velocity", "arm_wrench")
    assert manifest.action_keys == ("arm", "gripper")


def test_ordering_restores_contract_order_and_drops_unknown_keys(manifest: PolicyManifest) -> None:
    extracted = {"arm_wrench": 3, "arm_velocity": 2, "arm_position": 1, "not_in_contract": 9}

    assert list(manifest.order_state(extracted)) == ["arm_position", "arm_velocity", "arm_wrench"]


def test_ordering_keeps_absent_keys_absent(manifest: PolicyManifest) -> None:
    assert manifest.order_action({"gripper": 1}) == {"gripper": 1}


def test_camera_for_resolves_by_policy_key(manifest: PolicyManifest) -> None:
    assert manifest.camera_for("wrist").topic == "/wrist/camera/color/image_raw"

    with pytest.raises(KeyError):
        manifest.camera_for("no_such_camera")


def test_load_policy_manifest_reports_a_missing_contract(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Policy contract not found"):
        load_policy_manifest(tmp_path / "config_contract_gr00t.yml")


def test_deployment_contract_reuses_topics_across_segments(deployment_manifest: PolicyManifest) -> None:
    contract: PolicyContract = deployment_manifest.contract
    duplicated = {topic for topic, segments in deployment_manifest.state_by_topic.items() if len(segments) > 1}

    # position and velocity of both arms come from one measured_joint_states topic each
    assert duplicated == {
        "/left/franka_robot_state_broadcaster/measured_joint_states",
        "/right/franka_robot_state_broadcaster/measured_joint_states",
    }
    assert len(deployment_manifest.state_keys) == len(contract.state)
    assert sum(len(segments) for segments in deployment_manifest.state_by_topic.values()) == len(contract.state)


def test_deployment_cameras_point_at_reencoded_streams(deployment_manifest: PolicyManifest) -> None:
    assert all(topic.endswith("/compressed_video") for topic in deployment_manifest.cameras_by_topic)
    assert deployment_manifest.camera_keys == ("head", "wrist_left", "wrist_right")
