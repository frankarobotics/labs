"""Annotation integration tests using generated recordings and mock SDK responses."""

import importlib
import io
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar
from unittest.mock import Mock
from uuid import UUID

import av
import pytest
import requests
import uuid7
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory, timestamp_pb2
from google.protobuf.message import Message
from mcap.reader import make_reader
from mcap.writer import Writer
from mcap_protobuf.decoder import DecoderFactory
from pydantic import SecretStr

from annotations.config import AnnotationConfig, get_annotation_config
from annotations.episodes import episode_directory, recording_path
from annotations.models import AnnotationEvent, AnnotationJob
from annotations.nomadic_client import NomadicGateway, annotation_events, primary_video, workbench_url
from annotations.preparation import RecordingPreparer
from annotations.router import router
from annotations.service import AnnotationConflictError, AnnotationService, get_annotation_service
from annotations.store import JobStore
from models.episode import EpisodeMetadata, EpisodeProcessed, EpisodeStatus

T0 = 1_700_000_000_000_000_000


@pytest.fixture(autouse=True)
def no_live_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Tests must never call a live service")

    monkeypatch.setattr(requests.sessions.Session, "request", reject)


@pytest.fixture
def config(tmp_path: Path) -> AnnotationConfig:
    return AnnotationConfig(
        enabled=True,
        api_key=SecretStr("test-key-never-send"),
        state_path=tmp_path / "annotations",
        processed_episodes_path=tmp_path / "processed",
        spec_path=tmp_path / "spec.json",
        timeout_seconds=1,
    )


def schema_and_class(*, image: bool = False) -> tuple[bytes, type[Message]]:
    file = descriptor_pb2.FileDescriptorProto(name="test_video.proto", package="foxglove", syntax="proto3")
    file.dependency.append("google/protobuf/timestamp.proto")
    name = "CompressedImage" if image else "CompressedVideo"
    msg = file.message_type.add(name=name)
    msg.field.add(name="timestamp", number=1, type=11, type_name=".google.protobuf.Timestamp")
    msg.field.add(name="frame_id", number=4 if image else 2, type=9)
    msg.field.add(name="data", number=2 if image else 3, type=12)
    msg.field.add(name="format", number=3 if image else 4, type=9)
    pool = descriptor_pool.DescriptorPool()
    pool.AddSerializedFile(timestamp_pb2.DESCRIPTOR.serialized_pb)
    pool.Add(file)
    cls = message_factory.GetMessageClass(pool.FindMessageTypeByName(f"foxglove.{name}"))
    descriptors = descriptor_pb2.FileDescriptorSet()
    descriptors.file.add().ParseFromString(timestamp_pb2.DESCRIPTOR.serialized_pb)
    descriptors.file.add().CopyFrom(file)
    return descriptors.SerializeToString(), cls


def processed_recording(
    path: Path, *, codec: str = "libx264", frame_count: int = 3, timestamp_count: int = 3, with_metadata: bool = True
) -> list[int]:
    buffer = io.BytesIO()
    with av.open(buffer, "w", format="h264" if codec == "libx264" else "mp4") as container:
        stream = container.add_stream(codec, rate=10)
        stream.width = stream.height = 64
        stream.pix_fmt = "yuv420p"
        stream.codec_context.thread_count = 1
        for _ in range(frame_count):
            frame = av.VideoFrame(64, 64, "yuv420p")
            for plane in frame.planes:
                plane.update(bytes([128]) * plane.buffer_size)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    schema, cls = schema_and_class()
    message = cls(data=buffer.getvalue(), format="av01" if codec != "libx264" else "h264")
    times = [T0 + index * 100_000_000 for index in range(timestamp_count)]
    with path.open("wb") as output:
        writer = Writer(output)
        writer.start()
        sid = writer.register_schema("foxglove.CompressedVideo", "protobuf", schema)
        camera = writer.register_channel("/camera/head/video", "protobuf", sid)
        telemetry = writer.register_channel("/joints", "json", 0)
        writer.add_message(camera, T0, message.SerializeToString(), publish_time=T0)
        writer.add_message(telemetry, T0, b'{"position":[0.1,0.2]}', publish_time=T0 + 1, sequence=37)
        writer.add_attachment(T0, T0, "robot.urdf", "application/xml", b'<robot name="fixture"/>')
        if with_metadata:
            writer.add_metadata(
                "conversion_info",
                {
                    "data": json.dumps(
                        {
                            "frame_boundaries": {
                                "/camera/head/video": {"frame_timestamps": times},
                            }
                        }
                    )
                },
            )
        writer.finish()
    return times


def mapped_spec(config: AnnotationConfig) -> dict[str, Any]:
    spec = {
        "spec_version": "1.0",
        "recording": {"platform": {"mount": "robot_arm", "embodiment": "franka"}},
        "primary_view": "/camera/head/video",
        "views": [{"channel": "/camera/head/video", "role": "front"}],
        "signals": [],
    }
    assert config.spec_path is not None
    config.spec_path.write_text(json.dumps(spec))
    return spec


def saved_episode(config: AnnotationConfig) -> tuple[UUID, Path]:
    episode = uuid7.create()
    folder = episode_directory(config.processed_episodes_path, episode)
    folder.mkdir(parents=True)
    metadata = EpisodeMetadata(
        episode_id=episode,
        status=EpisodeStatus.SAVED,
        label=None,
        processed=EpisodeProcessed.SUCCESS,
        task_id=uuid7.create(),
        task_name="Move cup",
        task_description="Move the cup to the tray",
        station_id="test",
    )
    (folder / "episode_metadata.json").write_text(metadata.model_dump_json())
    (folder / ".processing_complete").touch()
    path = folder / "recording.mcap"
    processed_recording(path)
    mapped_spec(config)
    return episode, path


def test_preparation_preserves_frame_times_and_telemetry(tmp_path: Path, config: AnnotationConfig) -> None:
    episode, source = saved_episode(config)
    output = tmp_path / "prepared.mcap"
    digest, warnings = RecordingPreparer(config.spec_path).prepare(source, output, episode)
    assert len(digest) == 64
    assert "Trajectory evidence is unavailable" in warnings[0]
    with output.open("rb") as handle:
        reader = make_reader(handle)
        messages = list(reader.iter_messages())
        metadata = {record.name: record.metadata for record in reader.iter_metadata()}
        attachments = list(reader.iter_attachments())
    cameras = [(schema, channel, msg) for schema, channel, msg in messages if channel.topic.endswith("/video")]
    assert [msg.log_time for _, _, msg in cameras] == [T0, T0 + 100_000_000, T0 + 200_000_000]
    decode = DecoderFactory().decoder_for("protobuf", cameras[0][0])
    assert all(decode(msg.data).format == "h264" for _, _, msg in cameras)
    decoder = av.CodecContext.create("h264", "r")
    frames = [frame for _, _, msg in cameras for frame in decoder.decode(av.Packet(decode(msg.data).data))]
    frames.extend(decoder.decode(None))
    assert len(frames) == 3
    joints = [msg for _, channel, msg in messages if channel.topic == "/joints"]
    assert joints[0].data == b'{"position":[0.1,0.2]}'
    assert joints[0].publish_time == T0 + 1
    assert joints[0].sequence == 37
    assert attachments[0].name == "robot.urdf" and attachments[0].data == b'<robot name="fixture"/>'
    spec = json.loads(metadata["nomadic_spec"]["spec"])
    assert spec["recording"]["id"] == str(episode)
    assert spec["recording"]["t0_ns"] == T0
    assert recording_path(config, episode) == source


def test_frame_mismatch_fails_without_output(tmp_path: Path, config: AnnotationConfig) -> None:
    source = tmp_path / "bad.mcap"
    processed_recording(source, timestamp_count=4)
    mapped_spec(config)
    output = tmp_path / "output.mcap"
    with pytest.raises(ValueError, match="counts differ"):
        RecordingPreparer(config.spec_path).prepare(source, output, uuid7.create())
    assert not output.exists() and not output.with_suffix(".partial").exists()


def test_missing_mapping_fails_before_conversion(tmp_path: Path, config: AnnotationConfig) -> None:
    source = tmp_path / "source.mcap"
    processed_recording(source)
    with pytest.raises(ValueError, match="NOMADIC_SPEC_PATH"):
        RecordingPreparer(None).prepare(source, tmp_path / "output.mcap", uuid7.create())


def test_preparation_failure_never_uploads(config: AnnotationConfig) -> None:
    episode, _ = saved_episode(config)
    spec = mapped_spec(config)
    spec["views"][0]["channel"] = "/missing-camera"
    spec["primary_view"] = "/missing-camera"
    assert config.spec_path is not None
    config.spec_path.write_text(json.dumps(spec))
    FakeGateway.calls = []
    service = AnnotationService(config, FakeGateway)
    try:
        service.submit(episode)
        failed = wait_for_job(service, episode, "failed")
        assert "missing MCAP channels" in failed.message
        assert failed.remote_started is False and FakeGateway.calls == []
    finally:
        service.close()


def test_recording_status_and_paths_are_checked(config: AnnotationConfig) -> None:
    episode, source = saved_episode(config)
    metadata = source.parent / "episode_metadata.json"
    data = json.loads(metadata.read_text())
    data["status"] = "RECORDING"
    metadata.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Only saved"):
        recording_path(config, episode)
    with pytest.raises(ValueError, match="UUIDv7"):
        recording_path(config, UUID(int=0))


def test_whole_video_without_frame_times_is_rejected(tmp_path: Path, config: AnnotationConfig) -> None:
    source = tmp_path / "no-times.mcap"
    processed_recording(source, with_metadata=False)
    mapped_spec(config)
    with pytest.raises(ValueError, match="original frame timestamps"):
        RecordingPreparer(config.spec_path).prepare(source, tmp_path / "output.mcap", uuid7.create())


def test_episode_cannot_resolve_a_recording_outside_its_directory(config: AnnotationConfig, tmp_path: Path) -> None:
    episode, source = saved_episode(config)
    outside = tmp_path / "unrelated.mcap"
    source.rename(outside)
    source.symlink_to(outside)
    with pytest.raises(ValueError, match="inside its episode directory"):
        recording_path(config, episode)


def raw_analysis() -> dict[str, Any]:
    return {
        "analysis": {
            "status": "completed",
            "events": [
                {
                    "event_id": "event-123",
                    "time": "t=0.125",
                    "end_time": "t=0.375",
                    "description": "Left gripper moves the cup",
                    "type": "Pick",
                    "data": {
                        "structured_output": {
                            "acting_hand": "left",
                            "action_classes": ["pick", "transport"],
                            "objects_interacted_with": ["cup"],
                            "gripper_transitions": ["close"],
                            "object_interactions": ["left: pick — cup"],
                            "additional_evidence": {"contacts": [1, None], "verified": False},
                        }
                    },
                }
            ],
        }
    }


def test_event_contract_keeps_subseconds_ids_hands_and_objects() -> None:
    event = annotation_events(raw_analysis(), "analysis-1")[0]
    assert (event.start_seconds, event.end_seconds) == (0.125, 0.375)
    assert event.event_id == "event-123" and event.acting_hand == "left"
    assert event.category == "pick" and event.objects == ["cup"]
    payload = raw_analysis()
    payload["analysis"]["events"][0]["end_time"] = "t=0.1"
    with pytest.raises(ValueError, match="invalid action window"):
        annotation_events(payload, "analysis-1")


@pytest.mark.parametrize("source", ["structured_output", "data", "facets"])
def test_structured_output_is_preserved_from_each_supported_source(source: str) -> None:
    payload = raw_analysis()
    raw = payload["analysis"]["events"][0]
    fields = raw.pop("data")["structured_output"]
    raw[source] = {"structured_output": fields} if source == "data" else fields
    event = annotation_events(payload, "analysis-1")[0]
    assert event.action_classes == ["pick", "transport"]
    assert event.category == "pick"
    assert event.gripper_transitions == ["close"]
    assert event.object_interactions == ["left: pick — cup"]
    assert event.structured_output == fields
    assert AnnotationEvent.model_validate_json(event.model_dump_json()).structured_output == fields


def test_caption_segments_keep_structured_interactions() -> None:
    interaction = {"hand": "left", "operation": "transport", "object_name": "cup"}
    payload = {
        "status": "completed",
        "indexing_caption": {
            "segments": [
                {
                    "start_time": 0.25,
                    "end_time": 1.75,
                    "description": "Move cup",
                    "facets": {"action_classes": ["Transport"]},
                    "object_interactions": [interaction],
                }
            ]
        },
    }
    event = annotation_events(payload, "analysis-1")[0]
    assert event.object_interactions == [interaction]
    assert event.structured_output == {"action_classes": ["Transport"]}


def test_older_saved_events_default_to_empty_details() -> None:
    event = AnnotationEvent.model_validate(
        {
            "event_id": "older-event",
            "start_seconds": 0,
            "end_seconds": 1,
            "description": "Move cup",
        }
    )
    assert event.action_classes == event.gripper_transitions == event.object_interactions == []
    assert event.structured_output == {}


class FakeGateway(NomadicGateway):
    uploaded = threading.Event()
    finish = threading.Event()
    calls: ClassVar[list[str]] = []

    def __init__(self, config: AnnotationConfig) -> None:
        pass

    def upload(self, path: str) -> dict[str, Any]:
        self.calls.append("upload")
        assert Path(path).exists()
        self.uploaded.set()
        assert self.finish.wait(5)
        return {"mcap_ingest_id": "ingest-1"}

    def ingest(self, ingest_id: str) -> dict[str, Any]:
        assert ingest_id == "ingest-1"
        return {"status": "completed", "primary_view_id": "main-view"}

    def index(self, video_id: str) -> dict[str, Any]:
        self.calls.append("index")
        assert video_id == "main-view"
        return {"status": "completed", "batch_id": "batch-1", "analysis_id": "analysis-1"}

    def analysis(self, video_id: str, analysis_id: str) -> dict[str, Any]:
        return raw_analysis()

    def batch(self, batch_id: str) -> dict[str, Any]:
        return {
            "results": [{"video_id": "main-view", "analysis_id": "analysis-1"}],
        }

    def close(self) -> None:
        pass


def wait_for_job(service: AnnotationService, episode: UUID, state: str) -> AnnotationJob:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job = service.status(episode).job
        if job and job.state == state:
            return job
        time.sleep(0.01)
    pytest.fail(f"Job did not reach {state}")


def test_full_job_is_background_deduplicated_persisted_and_downloadable(config: AnnotationConfig) -> None:
    episode, _ = saved_episode(config)
    FakeGateway.calls = []
    FakeGateway.uploaded.clear()
    FakeGateway.finish.clear()
    service = AnnotationService(config, FakeGateway)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_annotation_service] = lambda: service
    try:
        with TestClient(app) as client:
            uri = f"/api/v1/episodes/{episode}/annotations"
            first = client.post(uri)
            assert first.status_code == 202
            assert FakeGateway.uploaded.wait(5)
            second = client.post(uri)
            assert second.json()["job_id"] == first.json()["job_id"]
            FakeGateway.finish.set()
            completed = wait_for_job(service, episode, "completed")
            assert completed.ingest_id == "ingest-1" and completed.batch_id == "batch-1"
            assert FakeGateway.calls == ["upload", "index"]
            assert client.post(uri).status_code == 409
            download = client.get(uri + "/download")
            assert download.status_code == 200
            assert download.json()["events"][0]["start_seconds"] == 0.125
            downloaded_event = download.json()["events"][0]
            expected_fields = raw_analysis()["analysis"]["events"][0]["data"]["structured_output"]
            assert downloaded_event["structured_output"] == expected_fields
            assert downloaded_event["action_classes"] == ["pick", "transport"]
            assert downloaded_event["gripper_transitions"] == ["close"]
            assert downloaded_event["object_interactions"] == ["left: pick — cup"]
            assert service.store is not None
            restored = JobStore(config.state_path).latest(episode)
            assert restored is not None and restored.events[0].structured_output == expected_fields
            assert config.api_key.get_secret_value() not in download.text
            assert "attachment" in download.headers["content-disposition"]
    finally:
        FakeGateway.finish.set()
        service.close()


def test_disabled_service_never_initializes_storage_or_sdk(tmp_path: Path) -> None:
    service = AnnotationService(AnnotationConfig(enabled=False, state_path=tmp_path / "state"))
    assert service.status(uuid7.create()).enabled is False
    assert not service.config.state_path.exists()


def test_recovery_retains_remote_ids_and_blocks_duplicate_upload(config: AnnotationConfig) -> None:
    episode, _ = saved_episode(config)
    store = JobStore(config.state_path)
    interrupted = AnnotationJob(
        job_id=uuid7.create(),
        episode_id=episode,
        state="indexing",
        remote_started=True,
        video_id="main-view",
        ingest_id="ingest-1",
    )
    store.save(interrupted)
    service = AnnotationService(config, FakeGateway)
    try:
        job = service.status(episode).job
        assert job.state == "interrupted" and job.video_id == "main-view"
        with pytest.raises(AnnotationConflictError, match="remote work"):
            service.submit(episode)
    finally:
        service.close()


def test_worker_ownership_is_exclusive(config: AnnotationConfig) -> None:
    first, second = AnnotationService(config), AnnotationService(config)
    first.start()
    try:
        with pytest.raises(AnnotationConflictError, match="Another annotation worker"):
            second.start()
    finally:
        first.close()
        second.close()


def test_remote_failure_is_redacted_and_cannot_duplicate_submission(config: AnnotationConfig) -> None:
    class FailingGateway(FakeGateway):
        def index(self, video_id: str) -> dict[str, Any]:
            raise RuntimeError(f"Authorization: {config.api_key.get_secret_value()}")

    episode, _ = saved_episode(config)
    FakeGateway.finish.set()
    service = AnnotationService(config, FailingGateway)
    try:
        service.submit(episode)
        interrupted = wait_for_job(service, episode, "interrupted")
        assert interrupted.video_id == "main-view" and interrupted.ingest_id == "ingest-1"
        assert config.api_key.get_secret_value() not in interrupted.model_dump_json()
        with pytest.raises(AnnotationConflictError):
            service.submit(episode)
    finally:
        service.close()


def test_primary_view_is_not_guessed() -> None:
    with pytest.raises(ValueError, match="primary camera"):
        primary_video({"status": "completed", "video_ids": ["left-wrist", "right-wrist"]})


def test_refresh_never_reuploads_or_reindexes(config: AnnotationConfig) -> None:
    episode = uuid7.create()
    store = JobStore(config.state_path)
    job = AnnotationJob(
        job_id=uuid7.create(),
        episode_id=episode,
        state="interrupted",
        remote_started=True,
        video_id="main-view",
        batch_id="batch-1",
    )
    store.save(job)
    FakeGateway.calls = []
    service = AnnotationService(config, FakeGateway)
    try:
        assert service.refresh(episode).job_id == job.job_id
        result = wait_for_job(service, episode, "completed")
        assert result.analysis_id == "analysis-1" and result.viewer_url is not None
        assert FakeGateway.calls == []
    finally:
        service.close()


def test_av1_whole_stream_is_converted(tmp_path: Path, config: AnnotationConfig) -> None:
    source = tmp_path / "av1.mcap"
    processed_recording(source, codec="libsvtav1")
    mapped_spec(config)
    output = tmp_path / "prepared.mcap"
    RecordingPreparer(config.spec_path).prepare(source, output, uuid7.create())
    with output.open("rb") as handle:
        cameras = [
            (schema, message)
            for schema, channel, message in make_reader(handle).iter_messages()
            if channel.topic.endswith("/video")
        ]
    assert len(cameras) == 3
    decode = DecoderFactory().decoder_for("protobuf", cameras[0][0])
    assert decode(cameras[0][1].data).format == "h264"


def test_existing_sdk_sends_robotics_mode(config: AnnotationConfig, monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = NomadicGateway(config)
    transport = Mock(
        side_effect=[
            Mock(json=lambda: {"run_id": "batch-1", "results": {}}),
            Mock(
                json=lambda: {"results": {"main": {"status": "completed", "batch_id": "batch-1", "analysis_id": "a1"}}}
            ),
        ]
    )
    monkeypatch.setattr(gateway.client, "_make_request", transport)
    try:
        result = gateway.index("main")
        assert result["status"] == "completed" and result["analysis_id"] == "a1"
        assert transport.call_args_list[0].args == ("POST", "/api/videos/index")
        assert transport.call_args_list[0].kwargs["json_data"] == {"video_ids": ["main"], "mode": "robotics"}
        assert transport.call_args_list[1].args == ("POST", "/api/videos/index/status")
    finally:
        gateway.close()


def image_recording(path: Path, payload: bytes, image_format: str = "jpeg") -> None:
    schema, cls = schema_and_class(image=True)
    with path.open("wb") as output:
        writer = Writer(output)
        writer.start()
        sid = writer.register_schema("foxglove.CompressedImage", "protobuf", schema)
        channel = writer.register_channel("/camera/head/video", "protobuf", sid)
        for index in range(3):
            stamp = T0 + index * 100_000_000
            image = cls(data=payload, format=image_format)
            image.timestamp.seconds, image.timestamp.nanos = divmod(stamp, 1_000_000_000)
            writer.add_message(channel, stamp, image.SerializeToString(), publish_time=stamp, sequence=index)
        writer.finish()


def test_compressed_images_preserve_payloads_and_timestamps(config: AnnotationConfig, tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with av.open(buffer, "w", format="image2pipe") as container:
        stream = container.add_stream("mjpeg", rate=10)
        stream.width = stream.height = 64
        stream.pix_fmt = "yuvj420p"
        stream.codec_context.thread_count = 1
        frame = av.VideoFrame(64, 64, "yuv420p")
        for plane in frame.planes:
            plane.update(bytes([128]) * plane.buffer_size)
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    source, prepared = tmp_path / "images.mcap", tmp_path / "prepared.mcap"
    image_recording(source, buffer.getvalue())
    mapped_spec(config)
    RecordingPreparer(config.spec_path).prepare(source, prepared, uuid7.create())
    with source.open("rb") as before, prepared.open("rb") as after:
        original = [message for _, _, message in make_reader(before).iter_messages()]
        copied = [message for _, _, message in make_reader(after).iter_messages()]
    assert [(m.log_time, m.publish_time, m.sequence, m.data) for m in copied] == [
        (m.log_time, m.publish_time, m.sequence, m.data) for m in original
    ]


@pytest.mark.parametrize(
    "image_format,payload,error",
    [
        ("raw", b"not-an-image", "JPEG, PNG or WebP"),
        ("jpeg", b"not-an-image", "cannot be decoded"),
    ],
)
def test_invalid_compressed_images_fail_before_upload(
    config: AnnotationConfig,
    tmp_path: Path,
    image_format: str,
    payload: bytes,
    error: str,
) -> None:
    source, prepared = tmp_path / "images.mcap", tmp_path / "prepared.mcap"
    image_recording(source, payload, image_format)
    mapped_spec(config)
    with pytest.raises(ValueError, match=error):
        RecordingPreparer(config.spec_path).prepare(source, prepared, uuid7.create())
    assert not prepared.exists()


def test_incompatible_sdk_fails_before_upload(config: AnnotationConfig, monkeypatch: pytest.MonkeyPatch) -> None:
    legacy = SimpleNamespace(
        session=Mock(),
        index=Mock(side_effect=ValueError("mode must be driving or construction")),
        upload=Mock(),
    )
    monkeypatch.setattr(importlib.import_module("nomadic"), "NomadicAI", Mock(return_value=legacy))
    with pytest.raises(ValueError, match="supported Nomadic SDK"):
        NomadicGateway(config)
    legacy.upload.assert_not_called()
    legacy.session.close.assert_called_once()


def test_processing_must_finish_before_submission(config: AnnotationConfig) -> None:
    episode, source = saved_episode(config)
    marker = source.parent / ".processing_complete"
    marker.unlink()
    service = AnnotationService(config, FakeGateway)
    try:
        status = service.status(episode)
        assert status.enabled and not status.can_submit
        assert "finish processing" in status.message
        with pytest.raises(FileNotFoundError, match="finish processing"):
            service.submit(episode)
        assert status.job is None
        marker.touch()
        assert service.status(episode).can_submit
    finally:
        service.close()


def test_completed_result_survives_deleted_source_and_mapping(config: AnnotationConfig) -> None:
    episode, source = saved_episode(config)
    store = JobStore(config.state_path)
    job = AnnotationJob(
        job_id=uuid7.create(),
        episode_id=episode,
        state="completed",
        remote_started=True,
        video_id="main-view",
        batch_id="batch-1",
        events=annotation_events(raw_analysis(), "analysis-1"),
    )
    store.save(job)
    source.unlink()
    config.spec_path.unlink()
    service = AnnotationService(config, FakeGateway)
    try:
        status = service.status(episode)
        assert status.job is not None and status.job.events == job.events
        assert not status.can_submit
        assert status.job.viewer_url == "https://app.nomadicml.com/workbench/batch-1?video=main-view"
        with pytest.raises(AnnotationConflictError, match="remote work"):
            service.submit(episode)
    finally:
        service.close()


@pytest.mark.parametrize("phase", ["connecting", "uploading", "ingesting", "indexing", "fetching"])
def test_failures_are_actionable_and_do_not_leak_credentials(
    config: AnnotationConfig,
    phase: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class BrokenGateway(FakeGateway):
        pass

    def fail(*_args: object, **_kwargs: object) -> None:
        raise ValueError(f"Authorization: {config.api_key.get_secret_value()}")

    method = {
        "connecting": "__init__",
        "uploading": "upload",
        "ingesting": "ingest",
        "indexing": "index",
        "fetching": "analysis",
    }[phase]
    monkeypatch.setattr(BrokenGateway, method, fail)
    episode, _ = saved_episode(config)
    FakeGateway.finish.set()
    FakeGateway.calls = []
    service = AnnotationService(config, BrokenGateway)
    try:
        service.submit(episode)
        job = wait_for_job(service, episode, "failed" if phase == "connecting" else "interrupted")
        assert config.api_key.get_secret_value() not in job.model_dump_json()
        assert config.api_key.get_secret_value() not in caplog.text
        assert "Check" in job.message or "Refresh saved result" in job.message
        if phase == "connecting":
            assert not job.remote_started and FakeGateway.calls == []
        else:
            with pytest.raises(AnnotationConflictError):
                service.submit(episode)
        if phase in {"ingesting", "indexing", "fetching"}:
            assert job.ingest_id == "ingest-1"
        if phase == "fetching":
            assert job.analysis_id == "analysis-1" and job.viewer_url is not None
    finally:
        service.close()


def test_partial_index_result_can_be_refreshed_without_resubmission(config: AnnotationConfig) -> None:
    class PendingGateway(FakeGateway):
        def index(self, video_id: str) -> dict[str, Any]:
            return {**super().index(video_id), "status": "failed", "error_code": "timeout"}

    episode, _ = saved_episode(config)
    FakeGateway.calls = []
    FakeGateway.finish.set()
    service = AnnotationService(config, PendingGateway)
    try:
        service.submit(episode)
        job = wait_for_job(service, episode, "interrupted")
        assert job.batch_id == "batch-1" and job.analysis_id == "analysis-1"
        service.refresh(episode)
        assert wait_for_job(service, episode, "completed").events
        assert FakeGateway.calls == ["upload", "index"]
    finally:
        service.close()


def test_timeout_run_reference_is_not_treated_as_a_batch(config: AnnotationConfig) -> None:
    class TimedOutGateway(FakeGateway):
        def index(self, video_id: str) -> dict[str, Any]:
            return {"status": "failed", "error_code": "timeout", "run_id": "index-run-1"}

    episode, _ = saved_episode(config)
    FakeGateway.finish.set()
    service = AnnotationService(config, TimedOutGateway)
    try:
        service.submit(episode)
        job = wait_for_job(service, episode, "interrupted")
        assert job.index_run_id == "index-run-1" and job.batch_id is None
        with pytest.raises(AnnotationConflictError, match="No remote analysis reference"):
            service.refresh(episode)
        status = service.status(episode)
        assert not status.can_submit and status.job.viewer_url is not None
        assert "/workbench/videos/" in status.job.viewer_url
    finally:
        service.close()


def test_queue_is_bounded_while_an_upload_is_running(config: AnnotationConfig) -> None:
    config.max_pending_jobs = 1
    episodes = [saved_episode(config)[0] for _ in range(3)]
    FakeGateway.uploaded.clear()
    FakeGateway.finish.clear()
    service = AnnotationService(config, FakeGateway)
    try:
        service.submit(episodes[0])
        assert FakeGateway.uploaded.wait(5)
        queued = service.submit(episodes[1])
        with pytest.raises(AnnotationConflictError, match="queue is full"):
            service.submit(episodes[2])
        assert service.status(episodes[1]).job.job_id == queued.job_id
    finally:
        FakeGateway.finish.set()
        service.close()


def test_local_preparation_can_be_retried_without_remote_work(config: AnnotationConfig) -> None:
    episode, _ = saved_episode(config)
    spec = mapped_spec(config)
    spec["primary_view"] = "/wrong-view"
    config.spec_path.write_text(json.dumps(spec))
    FakeGateway.calls = []
    FakeGateway.finish.set()
    service = AnnotationService(config, FakeGateway)
    try:
        first = service.submit(episode)
        assert not wait_for_job(service, episode, "failed").remote_started
        assert FakeGateway.calls == []
        mapped_spec(config)
        second = service.submit(episode)
        assert second.job_id != first.job_id
        assert wait_for_job(service, episode, "completed").events
        assert FakeGateway.calls == ["upload", "index"]
    finally:
        service.close()


@pytest.mark.parametrize("bad_input", ["empty", "multiple", "too_large"])
def test_invalid_recording_is_rejected_before_submission(config: AnnotationConfig, bad_input: str) -> None:
    episode, path = saved_episode(config)
    if bad_input == "empty":
        path.write_bytes(b"")
    elif bad_input == "multiple":
        path.with_name("second.mcap").write_bytes(path.read_bytes())
    else:
        config.max_recording_bytes = 1
    service = AnnotationService(config, FakeGateway)
    try:
        assert not service.status(episode).can_submit
        with pytest.raises(ValueError):
            service.submit(episode)
        assert service.status(episode).job is None
    finally:
        service.close()


def test_empty_result_can_be_completed_and_downloaded(config: AnnotationConfig) -> None:
    class EmptyGateway(FakeGateway):
        def analysis(self, video_id: str, analysis_id: str) -> dict[str, Any]:
            return {"status": "completed", "events": []}

    episode, _ = saved_episode(config)
    FakeGateway.finish.set()
    service = AnnotationService(config, EmptyGateway)
    try:
        service.submit(episode)
        assert wait_for_job(service, episode, "completed").events == []
    finally:
        service.close()


def test_storage_failure_is_reported_without_initializing_sdk(config: AnnotationConfig) -> None:
    config.state_path.write_text("not a directory")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_annotation_service] = lambda: AnnotationService(config, FakeGateway)
    with TestClient(app) as client:
        response = client.get(f"/api/v1/episodes/{uuid7.create()}/annotations")
    assert response.status_code == 503
    assert "storage is unavailable" in response.json()["detail"]


def test_workbench_link_preserves_recording_and_custom_dashboard() -> None:
    assert workbench_url("https://nomadic.example/app", "batch/1", "video 1") == (
        "https://nomadic.example/app/workbench/batch%2F1?video=video+1"
    )
    assert workbench_url("https://app.nomadicml.com", None, "video/1") == (
        "https://app.nomadicml.com/workbench/videos/video%2F1?video=video%2F1"
    )


@pytest.mark.parametrize("url", ["javascript:alert(1)", "https://key:secret@example.com", "http://example.com"])
def test_unsafe_dashboard_addresses_disable_submission(config: AnnotationConfig, url: str) -> None:
    config.dashboard_url = url
    service = AnnotationService(config)
    assert service.unavailable_reason() is not None


def test_preparation_refuses_to_replace_its_source(config: AnnotationConfig) -> None:
    episode, source = saved_episode(config)
    original = source.read_bytes()
    with pytest.raises(ValueError, match="separate file"):
        RecordingPreparer(config.spec_path).prepare(source, source, episode)
    assert source.read_bytes() == original


def test_camera_timestamps_must_be_increasing(config: AnnotationConfig, tmp_path: Path) -> None:
    source, prepared = tmp_path / "bad-order.mcap", tmp_path / "prepared.mcap"
    schema, cls = schema_and_class(image=True)
    buffer = io.BytesIO()
    with av.open(buffer, "w", format="image2pipe") as output:
        stream = output.add_stream("mjpeg", rate=10)
        stream.width = stream.height = 64
        stream.pix_fmt = "yuvj420p"
        frame = av.VideoFrame(64, 64, "yuv420p")
        for plane in frame.planes:
            plane.update(bytes([128]) * plane.buffer_size)
        for packet in [*stream.encode(frame), *stream.encode()]:
            output.mux(packet)
    with source.open("wb") as output:
        writer = Writer(output)
        writer.start()
        sid = writer.register_schema("foxglove.CompressedImage", "protobuf", schema)
        cid = writer.register_channel("/camera/head/video", "protobuf", sid)
        payload = cls(data=buffer.getvalue(), format="jpeg").SerializeToString()
        for stamp in [T0, T0]:
            writer.add_message(cid, stamp, payload, publish_time=stamp)
        writer.finish()
    mapped_spec(config)
    with pytest.raises(ValueError, match="strictly increasing"):
        RecordingPreparer(config.spec_path).prepare(source, prepared, uuid7.create())
    assert not prepared.exists()


def test_paths_follow_existing_station_configuration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ["NOMADIC_PROCESSED_EPISODES_PATH", "NOMADIC_STATE_PATH"]:
        monkeypatch.delenv(name, raising=False)
    processed = tmp_path / "station" / "processed"
    monkeypatch.setattr(
        "annotations.config.load_data_collection_config", lambda: SimpleNamespace(processed_data_path=processed)
    )
    get_annotation_config.cache_clear()
    try:
        config = get_annotation_config()
        assert config.processed_episodes_path == processed
        assert config.state_path == processed.parent / "nomadic_annotations"
        monkeypatch.setenv("NOMADIC_PROCESSED_EPISODES_PATH", str(tmp_path / "custom" / "processed"))
        monkeypatch.setenv("NOMADIC_STATE_PATH", str(tmp_path / "custom-state"))
        get_annotation_config.cache_clear()
        overridden = get_annotation_config()
        assert overridden.processed_episodes_path == tmp_path / "custom" / "processed"
        assert overridden.state_path == tmp_path / "custom-state"
    finally:
        get_annotation_config.cache_clear()


def test_optional_config_paths_ignore_empty_environment_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOMADIC_SPEC_PATH", "")
    monkeypatch.setenv("NOMADIC_POLICY_CONTRACT_PATH", str(tmp_path / "custom-contract.yml"))
    config = AnnotationConfig()
    assert config.spec_path is None
    assert config.policy_contract_path == tmp_path / "custom-contract.yml"
    monkeypatch.setenv("NOMADIC_SPEC_PATH", str(tmp_path / "custom-spec.json"))
    assert AnnotationConfig().spec_path == tmp_path / "custom-spec.json"


def test_explicit_or_embedded_spec_does_not_require_unused_contract(config: AnnotationConfig, tmp_path: Path) -> None:
    episode, source = saved_episode(config)
    config.policy_contract_path = tmp_path / "unused-contract.yml"
    explicit = tmp_path / "explicit.mcap"
    RecordingPreparer(config.spec_path, config.policy_contract_path).prepare(source, explicit, episode)
    embedded = tmp_path / "embedded.mcap"
    RecordingPreparer(None, config.policy_contract_path).prepare(explicit, embedded, episode)
    assert embedded.is_file()
    service = AnnotationService(config)
    try:
        assert service.status(episode).can_submit
    finally:
        service.close()
