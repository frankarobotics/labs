"""Check the adapter against the checked-in station, ROS schemas and real LABS converter."""

import ast
import json
from pathlib import Path
from typing import Any

import pytest
import uuid7
from mcap.reader import make_reader
from mcap.writer import Writer
from mcap_protobuf.decoder import DecoderFactory
from mcap_ros2.writer import Writer as ROSWriter
from pipeline_configs import PolicyContract, StationConfig
from test_annotations import T0, processed_recording

from annotations.preparation import RecordingPreparer, file_digest
from annotations.reference_station import KNUCKLE_MAX_RADIANS, KNUCKLE_NAME, ReferenceStationMapping

REPO = Path(__file__).resolve().parents[4]
CONTRACT = REPO / "deployments/fr3_duo_example/config_contract_gr00t.yml"
STATION = REPO / "deployments/fr3_duo_example/config_station.yml"
HEADER = """
================================================================================
MSG: std_msgs/Header
builtin_interfaces/Time stamp
string frame_id
================================================================================
MSG: builtin_interfaces/Time
int32 sec
uint32 nanosec
"""
JOINTS = "std_msgs/Header header\nstring[] name\nfloat64[] position\nfloat64[] velocity\nfloat64[] effort\n" + HEADER
IMAGE = (
    "std_msgs/Header header\nuint32 height\nuint32 width\nstring encoding\n"
    "uint8 is_bigendian\nuint32 step\nuint8[] data\n" + HEADER
)
WRENCH = (
    """std_msgs/Header header
geometry_msgs/Wrench wrench
================================================================================
MSG: geometry_msgs/Wrench
geometry_msgs/Vector3 force
geometry_msgs/Vector3 torque
================================================================================
MSG: geometry_msgs/Vector3
float64 x
float64 y
float64 z
"""
    + HEADER
)
TRANSFORMS = (
    """geometry_msgs/TransformStamped[] transforms
================================================================================
MSG: geometry_msgs/TransformStamped
std_msgs/Header header
string child_frame_id
geometry_msgs/Transform transform
================================================================================
MSG: geometry_msgs/Transform
geometry_msgs/Vector3 translation
geometry_msgs/Quaternion rotation
================================================================================
MSG: geometry_msgs/Vector3
float64 x
float64 y
float64 z
================================================================================
MSG: geometry_msgs/Quaternion
float64 x
float64 y
float64 z
float64 w
"""
    + HEADER
)


def base_transform(
    side: str,
    *,
    parent: str = "base",
    translation: tuple[float, float, float] = (0, 0, 0),
    rotation: tuple[float, float, float, float] = (0, 0, 0, 1),
) -> dict[str, Any]:
    seconds, nanos = divmod(T0, 1_000_000_000)
    return {
        "header": {"stamp": {"sec": seconds, "nanosec": nanos}, "frame_id": parent},
        "child_frame_id": f"{side}_fr3_link0",
        "transform": {
            "translation": dict(zip("xyz", translation, strict=True)),
            "rotation": dict(zip("xyzw", rotation, strict=True)),
        },
    }


def raw_reference_recording(
    path: Path,
    *,
    bad_joint: bool = False,
    gripper_angle: float | None = None,
    base_transforms: list[dict[str, Any]] | None = None,
) -> None:
    """Generate ROS 2 CDR data from the actual reference contract, without a ROS installation."""
    contract = PolicyContract.from_yaml(CONTRACT)
    with ROSWriter(str(path)) as writer:
        joint_schema = writer.register_msgdef("sensor_msgs/msg/JointState", JOINTS)
        wrench_schema = writer.register_msgdef("geometry_msgs/msg/WrenchStamped", WRENCH)
        image_schema = writer.register_msgdef("sensor_msgs/msg/Image", IMAGE)
        command_schema = writer.register_msgdef("std_msgs/msg/Float32", "float32 data\n")
        tf_schema = writer.register_msgdef("tf2_msgs/msg/TFMessage", TRANSFORMS)
        transforms = (
            base_transforms if base_transforms is not None else [base_transform("left"), base_transform("right")]
        )
        writer.write_message(
            "/tf_static",
            tf_schema,
            {"transforms": transforms},
            log_time=T0,
            publish_time=T0,
        )
        for index in range(3):
            timestamp = T0 + index * 100_000_000
            seconds, nanos = divmod(timestamp, 1_000_000_000)
            header = {"stamp": {"sec": seconds, "nanosec": nanos}, "frame_id": "fixture"}
            topics = {segment.topic for segment in contract.state}
            for topic in sorted(topics):
                segments = [segment for segment in contract.state if segment.topic == topic]
                side = "left" if topic.startswith("/left/") else "right"
                if "wrench" in topic:
                    payload = {
                        "header": header,
                        "wrench": {
                            "force": {"x": 1.0, "y": 2.0, "z": 3.0},
                            "torque": {"x": 4.0, "y": 5.0, "z": 6.0},
                        },
                    }
                    schema = wrench_schema
                else:
                    names = list(reversed(segments[0].element_names))
                    names = [f"{side}_{name}" for name in names]
                    if bad_joint and "measured_joint_states" in topic:
                        names[0] = "unrecognized_joint"
                    angle = (index if side == "left" else 2 - index) * 0.4
                    if gripper_angle is not None:
                        angle = gripper_angle
                    payload = {
                        "header": header,
                        "name": names,
                        "position": [angle] if "gripper" in topic else [i / 10 + index / 100 for i in range(7, 0, -1)],
                        "velocity": [0.01] * len(names),
                        "effort": [0.5] * len(names),
                    }
                    schema = joint_schema
                writer.write_message(
                    topic, schema, payload, log_time=timestamp, publish_time=timestamp + 7, sequence=index
                )
            for camera in contract.cameras:
                writer.write_message(
                    camera.topic,
                    image_schema,
                    {
                        "header": header,
                        "height": 64,
                        "width": 64,
                        "encoding": "bgr8",
                        "is_bigendian": 0,
                        "step": 64 * 3,
                        "data": bytes([index * 20]) * (64 * 64 * 3),
                    },
                    log_time=timestamp,
                    publish_time=timestamp + 7,
                    sequence=index,
                )
            # Commands intentionally disagree with measured state. They must not drive the grip slot.
            for side in ("left", "right"):
                writer.write_message(
                    f"/{side}/follower/gripper/gripper_client/target_gripper_width_percent",
                    command_schema,
                    {"data": 0.123},
                    log_time=timestamp,
                    publish_time=timestamp,
                    sequence=index,
                )


def processed_reference_recording(path: Path, *, video_frames: int = 3, **kwargs: Any) -> None:  # noqa: ANN401 -- Fixture overrides.
    """Combine real ROS messages with small whole-video streams for fast adapter tests."""
    contract = PolicyContract.from_yaml(CONTRACT)
    raw, video = path.with_suffix(".raw.mcap"), path.with_suffix(".video.mcap")
    raw_reference_recording(raw, **kwargs)
    times = processed_recording(video, frame_count=video_frames, timestamp_count=video_frames)
    with path.open("wb") as output:
        writer = Writer(output)
        writer.start()
        with video.open("rb") as source:
            schema, _, message = next(make_reader(source).iter_messages(topics=["/camera/head/video"]))
            assert schema is not None
            schema_id = writer.register_schema(schema.name, schema.encoding, schema.data)
            for camera in contract.cameras:
                channel = writer.register_channel(camera.dataset_topic, "protobuf", schema_id)
                writer.add_message(channel, message.log_time, message.data, publish_time=message.publish_time)
        schemas, channels = {}, {}
        with raw.open("rb") as source:
            for schema, channel, message in make_reader(source).iter_messages():
                if channel.topic in {camera.topic for camera in contract.cameras}:
                    continue
                target = RecordingPreparer._register(writer, schema, channel, schemas, channels)
                writer.add_message(
                    target, message.log_time, message.data, publish_time=message.publish_time, sequence=message.sequence
                )
        writer.add_metadata(
            "conversion_info",
            {
                "data": json.dumps(
                    {
                        "frame_boundaries": {
                            camera.dataset_topic: {"frame_timestamps": times} for camera in contract.cameras
                        }
                    }
                )
            },
        )
        writer.add_metadata("episode_context", {"data": json.dumps({"task_description": "Place both cubes in bowls"})})
        writer.finish()


def read_prepared(path: Path) -> tuple[dict[str, Any], dict[str, list[tuple[int, Any]]]]:
    with path.open("rb") as handle:
        reader = make_reader(handle)
        spec = next(
            json.loads(record.metadata["spec"]) for record in reader.iter_metadata() if record.name == "nomadic_spec"
        )
        factory = DecoderFactory()
        values: dict[str, list[tuple[int, Any]]] = {}
        for schema, channel, message in reader.iter_messages():
            if schema and schema.name == "nomadic.Signal":
                decode = factory.decoder_for(channel.message_encoding, schema)
                assert decode is not None
                values.setdefault(channel.topic, []).append((message.log_time, decode(message.data)))
    return spec, values


def test_mapping_uses_the_checked_in_station_and_driver() -> None:
    contract, station = PolicyContract.from_yaml(CONTRACT), StationConfig.from_yaml(str(STATION))
    recorded = {
        topic for device in station.embodiment.observer_devices or [] for topic in device.config.published_topics
    }
    assert {segment.topic for segment in contract.state} <= recorded
    assert {camera.topic for camera in contract.cameras} <= recorded
    source = (
        REPO
        / "services/actuators/robotiq-gripper/src/robotiq_gripper_bringup"
        / "robotiq_gripper_bringup/robotiq_gripper_client.py"
    )
    constants = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in ast.parse(source.read_text()).body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"KNUCKLE_JOINT_NAME", "KNUCKLE_JOINT_MAX_POSITION"}
    }
    assert constants == {"KNUCKLE_JOINT_NAME": KNUCKLE_NAME, "KNUCKLE_JOINT_MAX_POSITION": KNUCKLE_MAX_RADIANS}


def test_reference_preparation_converts_measurements_and_preserves_ros(tmp_path: Path) -> None:
    source, output = tmp_path / "source.mcap", tmp_path / "prepared.mcap"
    processed_reference_recording(source)
    original_hash = file_digest(source)
    _, warnings = RecordingPreparer(None, CONTRACT).prepare(source, output, uuid7.create())
    assert warnings == ["Recorded arm bases coincide; trajectories show nominal placement, not calibrated arm spacing."]
    assert file_digest(source) == original_hash
    spec, signals = read_prepared(output)
    assert len(spec["views"]) == 3 and len(spec["signals"]) == 18
    assert spec["recording"]["task"]["instruction"] == "Place both cubes in bowls"
    assert [row.number for _, row in signals["/nomadic/labs/left_gripper_closed"]] == [0, 0.5, 1]
    assert [row.number for _, row in signals["/nomadic/labs/right_gripper_closed"]] == [1, 0.5, 0]
    assert [part["grip"]["signal"] for part in spec["recording"]["platform"]["parts"]] == [
        "left_gripper_closed",
        "right_gripper_closed",
    ]
    assert list(signals["/nomadic/labs/left_arm_position"][0][1].vector.values) == pytest.approx(
        [i / 10 for i in range(1, 8)]
    )
    assert list(signals["/nomadic/labs/right_arm_external_wrench"][0][1].vector.values) == [1, 2, 3, 4, 5, 6]
    assert all([time for time, _ in rows] == [T0, T0 + 100_000_000, T0 + 200_000_000] for rows in signals.values())
    for path in (source, output):
        with path.open("rb") as handle:
            rows = [
                (channel.topic, message.log_time, message.publish_time, message.sequence, message.data)
                for _, channel, message in make_reader(handle).iter_messages()
                if channel.message_encoding == "cdr"
            ]
        if path == source:
            originals = rows
        else:
            assert rows == originals


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        ({"bad_joint": True}, "exactly one recorded joint"),
        ({"gripper_angle": 1.2}, "0-0.8 rad range"),
        ({"gripper_angle": float("nan")}, "not finite"),
    ],
)
def test_reference_rejects_ambiguous_or_invalid_measurements(
    tmp_path: Path, kwargs: dict[str, Any], reason: str
) -> None:
    source, output = tmp_path / "bad.mcap", tmp_path / "prepared.mcap"
    processed_reference_recording(source, **kwargs)
    with pytest.raises(ValueError, match=reason):
        RecordingPreparer(None, CONTRACT).prepare(source, output, uuid7.create())
    assert not output.exists() and not output.with_suffix(".partial").exists()


def test_reference_rejects_a_missing_recorded_topic() -> None:
    with pytest.raises(ValueError, match="missing channels"):
        ReferenceStationMapping(CONTRACT, set())


def test_spec_alone_cannot_relabel_ros_as_nomadic_signals(tmp_path: Path) -> None:
    source, spec_file = tmp_path / "source.mcap", tmp_path / "spec.json"
    processed_reference_recording(source)
    spec = {
        "spec_version": "1.1",
        "recording": {"platform": {"kind": "manipulator", "parts": []}},
        "views": [],
        "signals": [{"channel": "/left/franka_robot_state_broadcaster/measured_joint_states"}],
    }
    spec_file.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match=r"mapped telemetry must use nomadic\.Signal"):
        RecordingPreparer(spec_file).prepare(source, tmp_path / "output.mcap", uuid7.create())


def test_actual_labs_processor_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("foxglove", reason="Install the data-processor media dependencies for this integration check")
    pytest.importorskip("ffmpeg")
    monkeypatch.syspath_prepend(str(REPO / "services/pipeline/data-processor/src"))
    from scripts.mcap_converter import MCAPConverter  # noqa: PLC0415 -- Optional upstream processor dependencies.

    raw, processed, prepared = (tmp_path / name for name in ("raw.mcap", "processed.mcap", "prepared.mcap"))
    raw_reference_recording(raw)
    contract = PolicyContract.from_yaml(CONTRACT)
    converter = MCAPConverter(
        raw,
        processed,
        [camera.topic for camera in contract.cameras],
        {
            "codec_settings": {"codec": "libsvtav1", "preset": 12, "threads": 1, "cpu_affinity": [], "gop_size": 3},
        },
    )
    converter.convert()
    RecordingPreparer(None, CONTRACT).prepare(processed, prepared, uuid7.create())
    spec, signals = read_prepared(prepared)
    assert len(spec["views"]) == 3 and len(signals) == 18
    assert [row.number for _, row in signals["/nomadic/labs/left_gripper_closed"]] == [0, 0.5, 1]
