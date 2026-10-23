"""Prepare processed LABS recordings for Nomadic ingestion.

LABS stores a complete video in one CompressedVideo message. Nomadic expects
timestamped frames. Re-encode that stream as H.264 access units using LABS'
original per-frame timestamps, retaining all other channels and metadata.
"""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Iterator
from fractions import Fraction
from itertools import pairwise
from pathlib import Path
from typing import Any, BinaryIO
from uuid import UUID

import av
from av.video.codeccontext import VideoCodecContext
from mcap.reader import make_reader
from mcap.records import Channel, Message, Schema
from mcap.summary import Summary
from mcap.writer import Writer
from mcap_protobuf.decoder import DecoderFactory

from annotations.cameras import CameraPlan, alignment_plan, camera_frame, write_calibrations
from annotations.reference_station import ReferenceStationMapping


def file_digest(path: Path) -> str:
    """Hash the source incrementally for provenance and mutation checks."""
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _check_spec(spec: dict[str, Any], topics: set[str]) -> list[str]:
    """Check local wiring; Nomadic remains authoritative for its full spec contract."""
    views = spec.get("views") or []
    if not views or spec.get("primary_view") not in {view["channel"] for view in views}:
        raise ValueError("The Nomadic spec must declare cameras and a primary_view.")
    declared = [view["channel"] for view in views] + [signal["channel"] for signal in spec.get("signals", [])]
    if missing := set(declared) - topics:
        raise ValueError(f"Nomadic spec references missing MCAP channels: {', '.join(sorted(missing))}")
    if spec.get("spec_version") not in {"1.0", "1.1"}:
        raise ValueError("A supported Nomadic spec_version (1.0 or 1.1) is required.")
    if not spec.get("recording", {}).get("platform"):
        raise ValueError("The Nomadic spec must explicitly describe the recording platform.")
    return [] if spec.get("signals") else ["No robot signals are mapped. Trajectory evidence is unavailable."]


def _encoder(frame: av.VideoFrame, timestamps: list[int]) -> VideoCodecContext:
    encoder = av.CodecContext.create("libx264", "w")
    encoder.width, encoder.height = frame.width, frame.height
    encoder.pix_fmt = "yuv420p"
    encoder.framerate = (
        Fraction((len(timestamps) - 1) * 1_000_000_000, timestamps[-1] - timestamps[0]).limit_denominator(60000)
        if len(timestamps) > 1
        else Fraction(30)
    )
    encoder.time_base = 1 / encoder.framerate
    encoder.options = {"preset": "fast", "tune": "zerolatency", "crf": "20", "bf": "0"}
    encoder.thread_count = 1
    return encoder


def _check_image(payload: bytes, image_format: str) -> None:
    """Validate an image without modifying its bytes or recorded timestamps."""
    if image_format not in {"jpeg", "jpg", "png", "webp"} or not payload:
        raise ValueError("Camera images must contain JPEG, PNG or WebP data.")
    try:
        with av.open(io.BytesIO(payload), mode="r") as image:
            if next(image.decode(video=0), None) is None:
                raise ValueError("Camera image contains no decodable frame.")
    except av.FFmpegError as exc:
        raise ValueError("Camera image cannot be decoded.") from exc


def _packet_time(packet: av.Packet[Any], timestamps: list[int]) -> int:
    if packet.pts is None or not 0 <= packet.pts < len(timestamps):
        raise ValueError("The video encoder did not preserve frame identities.")
    return timestamps[packet.pts]


def _camera_timestamp(current: int, previous: int) -> int:
    """Reject duplicate or reordered capture times within a camera stream."""
    if current <= previous:
        raise ValueError("Camera timestamps must be strictly increasing within each view.")
    return current


def _selected_frames(
    container: av.container.InputContainer, timestamps: list[int], plan: CameraPlan | None
) -> Iterator[av.VideoFrame]:
    """Select source frames with bounded memory and verify the complete source frame count."""
    frames = iter(container.decode(video=0))
    current = None
    source_index = -1
    for selected in plan.indices if plan else range(len(timestamps)):
        while source_index < selected:
            current = next(frames, None)
            if current is None:
                raise ValueError("Video/frame timestamp counts differ; the decoded video has fewer frames.")
            source_index += 1
        if current is None:
            raise ValueError("The decoded video has no frames.")
        yield current
    count = source_index + 1 + sum(1 for _ in frames)
    if count != (plan.source_count if plan else len(timestamps)):
        raise ValueError("Video/frame timestamp counts differ; refusing to fabricate or drop frame times.")


def _video_packets(
    payload: bytes, timestamps: list[int], plan: CameraPlan | None = None
) -> Iterator[tuple[int, bytes]]:
    """Stream decoded frames through a low-latency encoder, keeping original timestamps."""
    if not timestamps or any(type(t) is not int for t in timestamps):
        raise ValueError("Camera frame timestamps must be integer nanoseconds.")
    if any(a >= b for a, b in pairwise(timestamps)):
        raise ValueError("Camera timestamps must be strictly increasing; duplicates cannot be repaired safely.")
    encoder = None
    packet_count = 0
    with av.open(io.BytesIO(payload), mode="r") as container:
        container.streams.video[0].codec_context.thread_count = 1
        for index, frame in enumerate(_selected_frames(container, timestamps, plan)):
            if encoder is None:
                encoder = _encoder(frame, timestamps)
            frame.pts = index
            frame.time_base = encoder.time_base
            for packet in encoder.encode(frame):
                packet_count += 1
                yield _packet_time(packet, timestamps), bytes(packet)
        if encoder:
            for packet in encoder.encode(None):
                packet_count += 1
                yield _packet_time(packet, timestamps), bytes(packet)
    if packet_count != len(timestamps):
        raise ValueError("Video/frame timestamp counts differ; refusing to fabricate or drop frame times.")


def _record_provenance(source: Path, episode_id: UUID, spec: dict[str, Any], plans: dict[str, CameraPlan]) -> None:
    """Prefer the saved episode metadata and record every temporal adjustment."""
    episode_file = source.parent.parent / "episode_metadata.json"
    if episode_file.is_file():
        episode = json.loads(episode_file.read_text())
        if episode.get("episode_id") != str(episode_id):
            raise ValueError("Episode metadata does not match the recording being prepared.")
        if instruction := episode.get("task_description"):
            spec["recording"]["task"] = {"instruction": instruction}
        spec.setdefault("source", {})["task_metadata_origin"] = "episode_metadata.json"
    if plans:
        spec.setdefault("source", {})["camera_alignment"] = {
            topic: {
                "offset_ns": plan.offset_ns,
                "source_frames": plan.source_count,
                "output_frames": len(plan.indices),
                "repeated_frames": [
                    index for index in range(1, len(plan.indices)) if plan.indices[index] == plan.indices[index - 1]
                ],
            }
            for topic, plan in plans.items()
        }


class RecordingPreparer:
    """Convert one finalized MCAP into a separate, uploadable file."""

    def __init__(self, spec_path: Path | None, policy_contract_path: Path | None = None) -> None:
        """Use an explicit/embedded mapping, or derive the FR3 Duo reference from its contract."""
        self.spec_path = spec_path
        self.policy_contract_path = policy_contract_path

    def prepare(self, source: Path, output: Path, episode_id: UUID) -> tuple[str, list[str]]:
        """Preserve sensor payloads and reject unsupported inputs before any network call."""
        if source.resolve() == output.resolve():
            raise ValueError("The prepared recording must be a separate file from the original.")
        original_stat = source.stat()
        digest = file_digest(source)
        with source.open("rb") as handle:
            reader = make_reader(handle)
            summary = reader.get_summary()
            if not summary or not summary.channels:
                raise ValueError("MCAP must have a readable channel summary.")
            metadata = list(reader.iter_metadata())
        spec, reference = self._mapping(summary, metadata)
        topics = {channel.topic for channel in summary.channels.values()}
        mapped_topics = topics | ({binding.channel for binding in reference.bindings} if reference else set())
        warnings = _check_spec(spec, mapped_topics)
        if reference:
            warnings.extend(reference.configure_frames(source))
        conversion: dict[str, Any] = next(
            (json.loads(m.metadata["data"]) for m in metadata if m.name == "conversion_info"), {}
        )
        # Prepared copies retain conversion_info, but already contain per-frame camera messages.
        prepared_copy = any(record.name == "nomadic_preparation" for record in metadata)
        boundaries = {} if prepared_copy else conversion.get("frame_boundaries") or {}
        plans = alignment_plan(source, boundaries, spec["views"], spec["primary_view"]) if reference else {}
        _record_provenance(source, episode_id, spec, plans)
        camera_topics = {view["channel"] for view in spec["views"]}
        spec["recording"].update(id=str(episode_id), clock="log_time")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(".partial")
        try:
            with source.open("rb") as handle, temporary.open("wb") as destination:
                writer = Writer(destination)
                writer.start()
                for record in metadata:
                    if record.name not in {"nomadic_spec", "nomadic_preparation"}:
                        writer.add_metadata(record.name, record.metadata)
                self._copy_messages(writer, handle, summary, camera_topics, boundaries, spec, plans)
                if reference:
                    reference.write_signals(writer, source)
                    write_calibrations(writer, source, reference.contract.cameras)
                handle.seek(0)
                for attachment in make_reader(handle).iter_attachments():
                    writer.add_attachment(
                        attachment.create_time,
                        attachment.log_time,
                        attachment.name,
                        attachment.media_type,
                        attachment.data,
                    )
                writer.add_metadata("nomadic_spec", {"spec": json.dumps(spec)})
                writer.add_metadata("nomadic_preparation", {"source_sha256": digest, "episode_id": str(episode_id)})
                writer.finish()  # type: ignore[no-untyped-call]  # Upstream mcap omits this return annotation.
            final_stat = source.stat()
            if (final_stat.st_size, final_stat.st_mtime_ns, final_stat.st_ino) != (
                original_stat.st_size,
                original_stat.st_mtime_ns,
                original_stat.st_ino,
            ) or file_digest(source) != digest:
                raise ValueError(
                    "The source recording changed during preparation; try again after processing finishes."
                )
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
        return digest, warnings

    def _mapping(self, summary: Summary, metadata: list[Any]) -> tuple[dict[str, Any], ReferenceStationMapping | None]:
        """Prefer explicit or embedded specs, then the configured LABS reference contract."""
        embedded = [m for m in metadata if m.name == "nomadic_spec"]
        if len(embedded) > 1:
            raise ValueError("The recording has multiple Nomadic specs.")
        reference = None
        topics = {channel.topic for channel in summary.channels.values()}
        if self.spec_path:
            spec = json.loads(self.spec_path.read_text())
        elif embedded:
            spec = json.loads(embedded[0].metadata["spec"])
        elif self.policy_contract_path:
            if not self.policy_contract_path.is_file():
                raise ValueError(
                    "The LABS policy contract is unavailable. Check NOMADIC_POLICY_CONTRACT_PATH on the station."
                )
            reference = ReferenceStationMapping(self.policy_contract_path, topics)
            spec = reference.spec
            context: dict[str, Any] = next(
                (json.loads(m.metadata["data"]) for m in metadata if m.name == "episode_context"), {}
            )
            if instruction := context.get("task_description"):
                spec["recording"]["task"] = {"instruction": instruction}
        else:
            raise ValueError(
                "Configure NOMADIC_POLICY_CONTRACT_PATH for the reference station "
                "or NOMADIC_SPEC_PATH for a custom mapping."
            )
        if not reference:
            self._check_signal_schemas(spec, summary)
        return spec, reference

    def _copy_messages(  # noqa: PLR0913
        self,
        writer: Writer,
        handle: BinaryIO,
        summary: Summary,
        camera_topics: set[str],
        boundaries: dict[str, Any],
        spec: dict[str, Any],
        plans: dict[str, CameraPlan],
    ) -> None:
        schemas: dict[int, int] = {}
        registered: dict[int, int] = {}
        seen_cameras: set[str] = set()
        decoder_factory = DecoderFactory()
        first_camera_time: int | None = None
        last_camera_time: dict[str, int] = {}
        for schema, channel, message in make_reader(handle).iter_messages(log_time_order=False):
            target = self._register(writer, schema, channel, schemas, registered)
            if channel.topic in camera_topics:
                timestamps = (boundaries.get(channel.topic) or {}).get("frame_timestamps")
                plan = plans.get(channel.topic)
                if plan:
                    timestamps = plan.timestamps
                if timestamps:
                    if channel.topic in seen_cameras:
                        raise ValueError("Whole-video camera topics must contain exactly one message.")
                    if schema is None or schema.name != "foxglove.CompressedVideo":
                        raise ValueError("LABS video conversion requires foxglove.CompressedVideo.")
                    count = sum(1 for c in summary.channels.values() if c.topic == channel.topic)
                    if count != 1:
                        raise ValueError("Camera topic has multiple channel definitions.")
                    decoder = decoder_factory.decoder_for(channel.message_encoding, schema)
                    if decoder is None:
                        raise ValueError("Cannot decode the processed camera schema.")
                    decoded = decoder(message.data)
                    self._write_video(writer, target, decoded, timestamps, plan, channel.topic, spec)
                    timestamp = timestamps[0]
                else:
                    last_camera_time[channel.topic] = _camera_timestamp(
                        message.log_time, last_camera_time.get(channel.topic, -1)
                    )
                    single_message = bool(
                        summary.statistics and summary.statistics.channel_message_counts.get(channel.id) == 1
                    )
                    self._check_camera(schema, channel, message, decoder_factory, single_message=single_message)
                    writer.add_message(
                        target,
                        message.log_time,
                        message.data,
                        publish_time=message.publish_time,
                        sequence=message.sequence,
                    )
                    timestamp = message.log_time
                first_camera_time = timestamp if first_camera_time is None else min(first_camera_time, timestamp)
                seen_cameras.add(channel.topic)
            else:
                writer.add_message(
                    target,
                    message.log_time,
                    message.data,
                    publish_time=message.publish_time,
                    sequence=message.sequence,
                )
        if camera_topics != seen_cameras or first_camera_time is None:
            raise ValueError("Every declared camera must contain messages.")
        spec["recording"]["t0_ns"] = first_camera_time

    @staticmethod
    def _write_video(  # noqa: PLR0913
        writer: Writer,
        target: int,
        decoded: Any,  # noqa: ANN401 -- Dynamic protobuf camera type.
        timestamps: list[int],
        plan: CameraPlan | None,
        topic: str,
        spec: dict[str, Any],
    ) -> None:
        """Emit independent H.264 access units on the selected presentation clock."""
        for sequence, (timestamp, payload) in enumerate(_video_packets(decoded.data, timestamps, plan)):
            encoded = type(decoded)()
            encoded.CopyFrom(decoded)
            encoded.data, encoded.format = payload, "h264"
            if plan:
                role = next(view["role"] for view in spec["views"] if view["channel"] == topic)
                encoded.frame_id = camera_frame("head" if role == "front" else role)
            encoded.timestamp.seconds, encoded.timestamp.nanos = divmod(timestamp, 1_000_000_000)
            writer.add_message(
                target,
                timestamp,
                encoded.SerializeToString(),
                publish_time=timestamp,
                sequence=sequence,
            )

    @staticmethod
    def _check_signal_schemas(spec: dict[str, Any], summary: Summary) -> None:
        """Require Nomadic-compatible signal payloads for explicit or embedded specs."""
        signals = {signal["channel"] for signal in spec.get("signals", [])}
        for channel in summary.channels.values():
            if channel.topic in signals:
                schema = summary.schemas.get(channel.schema_id)
                if schema is None or schema.name != "nomadic.Signal" or channel.message_encoding != "protobuf":
                    raise ValueError(
                        f"{channel.topic}: mapped telemetry must use nomadic.Signal/protobuf. "
                        "Use the LABS reference contract to convert ROS measurements."
                    )

    @staticmethod
    def _register(
        writer: Writer, schema: Schema | None, channel: Channel, schemas: dict[int, int], channels: dict[int, int]
    ) -> int:
        if channel.id not in channels:
            if schema and schema.id not in schemas:
                schemas[schema.id] = writer.register_schema(schema.name, schema.encoding, schema.data)
            channels[channel.id] = writer.register_channel(
                channel.topic,
                channel.message_encoding,
                schemas[schema.id] if schema else 0,
                channel.metadata,
            )
        return channels[channel.id]

    @staticmethod
    def _check_camera(
        schema: Schema | None,
        channel: Channel,
        message: Message,
        decoder_factory: DecoderFactory,
        *,
        single_message: bool,
    ) -> None:
        if schema and schema.name in {"sensor_msgs/msg/CompressedImage", "sensor_msgs/CompressedImage"}:
            return
        if schema is None or schema.name not in {"foxglove.CompressedImage", "foxglove.CompressedVideo"}:
            raise ValueError("Process raw camera images before annotation; this camera encoding is unsupported.")
        decoder = decoder_factory.decoder_for(channel.message_encoding, schema)
        if decoder is None:
            raise ValueError("Cannot decode the camera schema.")
        video = decoder(message.data)
        if schema.name == "foxglove.CompressedImage":
            _check_image(video.data, video.format)
            return
        if video.format not in {"h264", "h265", "hevc"}:
            raise ValueError("Video needs H.264/H.265 frames or LABS conversion_info with original frame timestamps.")
        if single_message:
            parser = av.CodecContext.create("h264" if video.format == "h264" else "hevc", "r")
            packets = [*parser.parse(video.data), *parser.parse(None)]
            if len(packets) != 1:
                raise ValueError("Whole-video messages require LABS conversion_info with original frame timestamps.")
