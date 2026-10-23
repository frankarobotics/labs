"""Regression coverage for capture timing, real episode metadata and derived geometry."""

import json
import math
from pathlib import Path

import numpy as np
import pytest
import uuid7
from mcap.reader import make_reader
from mcap_protobuf.decoder import DecoderFactory
from pipeline_configs import PolicyContract
from test_annotations import T0
from test_reference_station import CONTRACT, base_transform, processed_reference_recording, read_prepared

from annotations.cameras import alignment_plan
from annotations.kinematics import flange_transform, orientation_xyzw
from annotations.preparation import RecordingPreparer
from annotations.reference_station import capture_time


def test_saved_episode_task_overrides_inconsistent_embedded_task(tmp_path: Path) -> None:
    source = tmp_path / "episode/mcap/source.mcap"
    source.parent.mkdir(parents=True)
    processed_reference_recording(source)
    identity = uuid7.create()
    (source.parent.parent / "episode_metadata.json").write_text(
        json.dumps({"episode_id": str(identity), "task_description": "Sort plush toys by color"})
    )
    output = tmp_path / "prepared.mcap"
    RecordingPreparer(None, CONTRACT).prepare(source, output, identity)
    spec, signals = read_prepared(output)
    assert spec["recording"]["task"]["instruction"] == "Sort plush toys by color"
    assert spec["source"]["task_metadata_origin"] == "episode_metadata.json"
    assert signals["/nomadic/labs/left_gripper_width_command"][0][1].number == pytest.approx(0.123)
    assert signals["/nomadic/labs/left_gripper_closed"][0][1].number == 0
    assert list(signals["/nomadic/labs/left_arm_torque"][0][1].vector.values) == [0.5] * 7
    assert all("joints" not in part for part in spec["recording"]["platform"]["parts"])


def test_alignment_repeats_a_dropped_frame_and_estimates_camera_phase(tmp_path: Path) -> None:
    source = tmp_path / "source.mcap"
    processed_reference_recording(source, video_frames=4)
    cameras = PolicyContract.from_yaml(CONTRACT).cameras
    stamps = [T0, T0 + 100_000_000, T0 + 300_000_000, T0 + 400_000_000]
    boundaries = {
        camera.dataset_topic: {"frame_timestamps": [stamp + index * 10_000_000 for stamp in stamps]}
        for index, camera in enumerate(cameras)
    }
    views = [{"channel": camera.dataset_topic} for camera in cameras]
    plans = alignment_plan(source, boundaries, views, cameras[0].dataset_topic)
    assert all(plan.indices == [0, 1, 1, 2, 3] for plan in plans.values())
    assert {tuple(plan.timestamps) for plan in plans.values()} == {
        tuple(T0 + index * 100_000_000 for index in range(5))
    }
    assert [plans[camera.dataset_topic].offset_ns for camera in cameras] == [0, 10_000_000, 20_000_000]
    boundaries[cameras[1].dataset_topic]["frame_timestamps"] = [stamp + 20_000_000_000 for stamp in stamps]
    with pytest.raises(ValueError, match="same recording interval"):
        alignment_plan(source, boundaries, views, cameras[0].dataset_topic)


def test_nominal_fr3_flange_geometry_and_quaternion() -> None:
    zero = flange_transform([0.0] * 7)
    np.testing.assert_allclose(zero[:3, 3], [0.088, 0, 0.926], atol=1e-12)
    np.testing.assert_allclose(zero[:3, :3], np.diag([1, -1, -1]), atol=1e-12)
    quaternion = orientation_xyzw(zero)
    assert abs(quaternion[0]) == pytest.approx(1)
    assert sum(value * value for value in quaternion) == pytest.approx(1)
    rotated = flange_transform([math.pi / 2, 0, 0, 0, 0, 0, 0])
    np.testing.assert_allclose(rotated[:3, 3], [0, 0.088, 0.926], atol=1e-12)
    with pytest.raises(ValueError, match="seven finite"):
        flange_transform([float("nan")] * 7)


def test_poses_apply_recorded_base_rotation_and_translation(tmp_path: Path) -> None:
    source, output = tmp_path / "source.mcap", tmp_path / "prepared.mcap"
    half = math.sqrt(0.5)
    processed_reference_recording(
        source,
        base_transforms=[
            base_transform("left"),
            base_transform("right", translation=(0.6, -0.2, 0), rotation=(0, 0, half, half)),
        ],
    )
    _, warnings = RecordingPreparer(None, CONTRACT).prepare(source, output, uuid7.create())
    assert not warnings
    factory = DecoderFactory()
    poses = {}
    with output.open("rb") as handle:
        for schema, channel, message in make_reader(handle).iter_messages():
            if schema and schema.name == "foxglove.PoseInFrame" and channel.topic not in poses:
                decode = factory.decoder_for(channel.message_encoding, schema)
                assert decode is not None
                poses[channel.topic] = decode(message.data)
    assert set(poses) == {f"/nomadic/labs/{side}_flange_pose" for side in ("left", "right")}
    left, right = [poses[f"/nomadic/labs/{side}_flange_pose"] for side in ("left", "right")]
    assert left.frame_id == right.frame_id == "base"
    spec, _ = read_prepared(output)
    bases = spec["source"]["arm_base_transforms"]
    assert bases["right"]["translation_m"] == [0.6, -0.2, 0]
    assert bases["right"]["rotation_xyzw"] == pytest.approx([0, 0, half, half])
    _assert_no_nested_arrays(spec)
    x, y, z = left.pose.position.x, left.pose.position.y, left.pose.position.z
    np.testing.assert_allclose(
        [right.pose.position.x, right.pose.position.y, right.pose.position.z], [0.6 - y, -0.2 + x, z], atol=1e-12
    )
    nominal = flange_transform([i / 10 for i in range(1, 8)])
    rotation = np.array([[0, -1, 0, 0.6], [1, 0, 0, -0.2], [0, 0, 1, 0], [0, 0, 0, 1]])
    quaternion = right.pose.orientation
    np.testing.assert_allclose(
        [quaternion.x, quaternion.y, quaternion.z, quaternion.w], orientation_xyzw(rotation @ nominal), atol=1e-12
    )


def _assert_no_nested_arrays(value: object) -> None:
    """Nomadic persists the spec in a database that rejects arrays directly inside arrays."""
    if isinstance(value, list):
        assert not any(isinstance(item, list) for item in value)
        for item in value:
            _assert_no_nested_arrays(item)
    elif isinstance(value, dict):
        for item in value.values():
            _assert_no_nested_arrays(item)


@pytest.mark.parametrize(
    "transforms,reason",
    [
        ([], "transforms for both"),
        ([base_transform("left"), base_transform("right", parent="other")], "different parents"),
        (
            [base_transform("left"), base_transform("left", translation=(1, 0, 0)), base_transform("right")],
            "Conflicting recorded",
        ),
        ([base_transform("left"), base_transform("right", rotation=(0, 0, 0, 0))], "unit quaternions"),
        ([base_transform("left"), base_transform("right", translation=(float("nan"), 0, 0))], "finite values"),
    ],
)
def test_invalid_recorded_base_frames_fail_before_output(tmp_path: Path, transforms: list[dict], reason: str) -> None:
    source, output = tmp_path / "source.mcap", tmp_path / "prepared.mcap"
    processed_reference_recording(source, base_transforms=transforms)
    with pytest.raises(ValueError, match=reason):
        RecordingPreparer(None, CONTRACT).prepare(source, output, uuid7.create())
    assert not output.exists() and not output.with_suffix(".partial").exists()


def test_camera_grid_matches_fixed_playback_rate_despite_timestamp_jitter(tmp_path: Path) -> None:
    source = tmp_path / "source.mcap"
    processed_reference_recording(source, video_frames=4)
    cameras = PolicyContract.from_yaml(CONTRACT).cameras
    stamps = [T0 + value for value in (0, 100_100_000, 200_200_000, 400_400_000)]
    boundaries = {camera.dataset_topic: {"frame_timestamps": stamps} for camera in cameras}
    plans = alignment_plan(
        source, boundaries, [{"channel": c.dataset_topic} for c in cameras], cameras[0].dataset_topic
    )
    assert all(plan.timestamps == [T0 + i * 100_000_000 for i in range(5)] for plan in plans.values())
    assert all(plan.indices == [0, 1, 2, 2, 3] for plan in plans.values())


def test_headerless_commands_use_recording_time() -> None:
    assert capture_time(object(), T0) == T0
