"""Synchronize processed LABS cameras and retain their recorded intrinsics."""

import math
from bisect import bisect_left
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from statistics import median
from typing import Any

from foxglove_schemas_protobuf.CameraCalibration_pb2 import CameraCalibration
from mcap.reader import make_reader
from mcap.writer import Writer
from mcap_protobuf.decoder import DecoderFactory
from mcap_protobuf.schema import register_schema
from mcap_ros2.decoder import DecoderFactory as ROSDecoderFactory
from pipeline_configs import CameraSegment

from recording_conversion.reference_station import capture_time


def camera_frame(role: str) -> str:
    """Keep local camera frames distinct without inventing camera extrinsics."""
    return f"labs_{role}_optical"


@dataclass(frozen=True)
class CameraPlan:
    """Source frame selection and its presentation grid; source timestamps remain in metadata."""

    timestamps: list[int]
    indices: list[int]
    source_count: int
    offset_ns: int


def _capture_times(source: Path, boundaries: dict[str, Any], topics: set[str]) -> dict[str, list[int]]:
    """Recover per-frame capture clocks from the whole-video anchor and recorded intervals."""
    times = {}
    factory = DecoderFactory()
    with source.open("rb") as handle:
        for schema, channel, message in make_reader(handle).iter_messages(topics=sorted(topics)):
            if channel.topic in times or schema is None:
                raise ValueError("Camera alignment requires one whole-video message per view.")
            decode = factory.decoder_for(channel.message_encoding, schema)
            if decode is None:
                raise ValueError("The camera schema cannot be decoded.")
            video = decode(message.data)
            recorded = boundaries[channel.topic].get("frame_timestamps") or []
            if not recorded or any(type(value) is not int for value in recorded):
                raise ValueError("Camera timestamps must be integer nanoseconds.")
            if any(a >= b for a, b in pairwise(recorded)):
                raise ValueError("Camera timestamps must be strictly increasing.")
            anchor = video.timestamp.seconds * 1_000_000_000 + video.timestamp.nanos
            anchor = anchor or recorded[0]
            times[channel.topic] = [anchor + value - recorded[0] for value in recorded]
    if set(times) != topics:
        raise ValueError("Every declared camera must contain frames.")
    return times


def alignment_plan(
    source: Path, boundaries: dict[str, Any], views: list[dict[str, Any]], primary: str
) -> tuple[dict[str, CameraPlan], list[str]]:
    """Estimate camera phase from capture clocks and resample onto the primary cadence.

    Cameras may start or stop at slightly different times. The grid covers only the interval every camera recorded, and
    a warning says how much footage was left out.
    """
    topics = {view["channel"] for view in views}
    if not topics <= boundaries.keys():
        return {}, []
    times = _capture_times(source, boundaries, topics)
    reference = times[primary]
    if len(reference) < 2:  # noqa: PLR2004
        return {}, []
    # Nomadic remuxes camera frames at an integer fps. Use that same presentation clock.
    cadence = median(b - a for a, b in pairwise(reference))
    fps = max(1, round(1_000_000_000 / cadence))
    period = round(1_000_000_000 / fps)
    aligned, offsets = {}, {}
    for topic, stamps in times.items():
        if len(stamps) < 2 or max(b - a for a, b in pairwise(stamps)) > 3 * period:  # noqa: PLR2004
            raise ValueError("A camera has a long gap; refusing to fill missing footage.")
        offsets[topic] = (
            0
            if topic == primary
            else int(
                median(value - (reference[0] + round((value - reference[0]) / period) * period) for value in stamps)
            )
        )
        aligned[topic] = [value - offsets[topic] for value in stamps]
    # A grid point is usable when every camera has a frame within 1.5 periods of it.
    tolerance = period * 1.5
    first = max(stamps[0] for stamps in aligned.values()) - tolerance
    last = min(stamps[-1] for stamps in aligned.values()) + tolerance
    full = range(round((reference[-1] - reference[0]) / period) + 1)
    grid = [reference[0] + index * period for index in full if first <= reference[0] + index * period <= last]
    if len(grid) < 2:  # noqa: PLR2004
        raise ValueError("The cameras do not record a common interval.")
    plans = {}
    for topic, stamps in aligned.items():
        indices = []
        for timestamp in grid:
            insertion = bisect_left(stamps, timestamp)
            candidates = [index for index in (insertion - 1, insertion) if 0 <= index < len(stamps)]
            indices.append(min(candidates, key=lambda index: (abs(stamps[index] - timestamp), index)))
        plans[topic] = CameraPlan(grid, indices, len(times[topic]), offsets[topic])
    warnings = []
    if len(grid) < len(full):
        lead, tail = (grid[0] - reference[0]) / 1e9, (reference[-1] - grid[-1]) / 1e9
        warnings.append(
            f"The cameras started or stopped at different times, so only the interval all cameras recorded was "
            f"annotated: {lead:.2f} s left out at the start and {tail:.2f} s at the end. Annotation times count from "
            "the start of that interval."
        )
    return plans, warnings


def write_calibrations(writer: Writer, source: Path, cameras: tuple[CameraSegment, ...]) -> int:
    """Copy source CameraInfo intrinsics into Foxglove messages, without global transforms."""
    by_topic = {camera.topic.rsplit("/", 1)[0] + "/camera_info": camera for camera in cameras}
    seen = set()
    factory = ROSDecoderFactory()
    schema_id = None
    with source.open("rb") as handle:
        for schema, channel, message in make_reader(handle).iter_messages(topics=sorted(by_topic)):
            if channel.topic in seen:
                continue
            if schema is None or schema.name != "sensor_msgs/msg/CameraInfo":
                raise ValueError(f"{channel.topic}: expected ROS CameraInfo.")
            decode = factory.decoder_for(channel.message_encoding, schema)
            if decode is None:
                raise ValueError(f"{channel.topic}: camera calibration cannot be decoded.")
            info = decode(message.data)
            if (
                info.width <= 0
                or info.height <= 0
                or not all(math.isfinite(value) for value in [*info.k, *info.r, *info.p, *info.d])
            ):
                raise ValueError(f"{channel.topic}: invalid camera calibration.")
            camera = by_topic[channel.topic]
            value = CameraCalibration(
                frame_id=camera_frame(camera.policy_key),
                width=info.width,
                height=info.height,
                distortion_model=info.distortion_model,
                D=info.d,
                K=info.k,
                R=info.r,
                P=info.p,
            )
            timestamp = capture_time(info, message.log_time)
            value.timestamp.seconds, value.timestamp.nanos = divmod(timestamp, 1_000_000_000)
            if schema_id is None:
                schema_id = register_schema(writer, CameraCalibration)
            target = writer.register_channel(camera.dataset_topic + "/calibration", "protobuf", schema_id)
            writer.add_message(target, timestamp, value.SerializeToString(), publish_time=timestamp)
            seen.add(channel.topic)
    return len(seen)
