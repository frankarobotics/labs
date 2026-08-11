from types import SimpleNamespace

from lerobot_conversion.lerobot_mcap_reader import LeRobotMCAPReader, _Extraction
from lerobot_conversion.policy_manifest import PolicyManifest


def _schema(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


def _message(log_time: int = 1_000) -> SimpleNamespace:
    return SimpleNamespace(log_time=log_time, publish_time=log_time)


def _joint_state(names: list[str], **arrays: list[float]) -> SimpleNamespace:
    return SimpleNamespace(name=names, **arrays)


def test_one_message_feeds_every_segment_reading_its_topic(manifest: PolicyManifest) -> None:
    reader = LeRobotMCAPReader(manifest)
    extraction = _Extraction()

    reader._handle_message(
        "/arm/joint_states",
        _schema("sensor_msgs/msg/JointState"),
        _message(),
        _joint_state(["joint2", "joint1"], position=[2.0, 1.0], velocity=[20.0, 10.0]),
        extraction,
    )

    assert extraction.robot_states["arm_position"][0].values == [1.0, 2.0]
    assert extraction.robot_states["arm_velocity"][0].values == [10.0, 20.0]


def test_decoded_values_carry_the_contract_element_names(manifest: PolicyManifest) -> None:
    reader = LeRobotMCAPReader(manifest)
    extraction = _Extraction()

    reader._handle_message(
        "/follower/joint_states",
        _schema("sensor_msgs/msg/JointState"),
        _message(),
        _joint_state(["joint1", "joint2"], position=[1.0, 2.0]),
        extraction,
    )

    assert extraction.actions["arm"][0].names == ["joint1", "joint2"]


def test_a_state_topic_does_not_leak_into_actions(manifest: PolicyManifest) -> None:
    reader = LeRobotMCAPReader(manifest)
    extraction = _Extraction()

    reader._handle_message(
        "/arm/joint_states",
        _schema("sensor_msgs/msg/JointState"),
        _message(),
        _joint_state(["joint1", "joint2"], position=[1.0, 2.0], velocity=[0.0, 0.0]),
        extraction,
    )

    assert not extraction.actions


def test_a_topic_recorded_with_another_schema_is_skipped(manifest: PolicyManifest) -> None:
    reader = LeRobotMCAPReader(manifest)
    extraction = _Extraction()

    reader._handle_message(
        "/arm/joint_states",
        _schema("std_msgs/msg/Float32"),
        _message(),
        SimpleNamespace(data=1.0),
        extraction,
    )

    assert not extraction.robot_states


def test_an_undecodable_segment_does_not_stop_the_others(manifest: PolicyManifest) -> None:
    reader = LeRobotMCAPReader(manifest)
    extraction = _Extraction()

    # velocity is empty, so only arm_position can be decoded from this message
    reader._handle_message(
        "/arm/joint_states",
        _schema("sensor_msgs/msg/JointState"),
        _message(),
        _joint_state(["joint1", "joint2"], position=[1.0, 2.0], velocity=[]),
        extraction,
    )

    assert extraction.robot_states["arm_position"][0].values == [1.0, 2.0]
    assert "arm_velocity" not in extraction.robot_states


def test_video_is_stored_under_the_camera_policy_key(manifest: PolicyManifest) -> None:
    reader = LeRobotMCAPReader(manifest)
    extraction = _Extraction()

    reader._handle_message(
        "/wrist/camera/color/compressed_video",
        _schema("foxglove.CompressedVideo"),
        _message(),
        SimpleNamespace(format="mp4", data=b"payload"),
        extraction,
    )

    assert extraction.compressed_videos["wrist"].data == b"payload"
    assert extraction.compressed_videos["wrist"].format == "mp4"


def test_the_live_image_topic_carries_no_video_in_a_processed_episode(manifest: PolicyManifest) -> None:
    reader = LeRobotMCAPReader(manifest)
    extraction = _Extraction()

    reader._handle_message(
        "/wrist/camera/color/image_raw",
        _schema("sensor_msgs/msg/Image"),
        _message(),
        SimpleNamespace(),
        extraction,
    )

    assert not extraction.compressed_videos


def test_a_topic_outside_the_contract_is_reported_once(manifest: PolicyManifest) -> None:
    reader = LeRobotMCAPReader(manifest)
    extraction = _Extraction()

    for _ in range(3):
        reader._handle_message(
            "/other/topic", _schema("std_msgs/msg/Float32"), _message(), SimpleNamespace(), extraction
        )

    assert reader._logged_topics == {"unconfigured:/other/topic"}


def test_ros_infrastructure_topics_are_never_reported(manifest: PolicyManifest) -> None:
    reader = LeRobotMCAPReader(manifest)

    reader._handle_message("/rosout", _schema("rcl_interfaces/msg/Log"), _message(), SimpleNamespace(), _Extraction())

    assert not reader._logged_topics
