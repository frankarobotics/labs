import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest
from pipeline_configs import PAD_VALUE, compute_letterbox_geometry

from lerobot_conversion.video_frame_extractor import (
    BGR_CHANNELS,
    GROW_KERNEL,
    SHRINK_KERNEL,
    VideoFrameExtractor,
    _scale_kernel,
)

SOURCE_WIDTH = 640
SOURCE_HEIGHT = 480
SOURCE_SHAPE = (SOURCE_HEIGHT, SOURCE_WIDTH)
SOURCE_FPS = 30
DURATION_S = 1
DURATION_NS = int(DURATION_S * 1e9)
TARGET_FPS = 10.0

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg binary not available")


@pytest.fixture(scope="module")
def video_bytes(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    """A real encoded clip: the resize path lives in ffmpeg, so a synthetic array cannot exercise it."""
    video_file: Path = tmp_path_factory.mktemp("video") / "source.mp4"
    subprocess.run(  # noqa: S603
        [  # noqa: S607
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size={SOURCE_WIDTH}x{SOURCE_HEIGHT}:rate={SOURCE_FPS}:duration={DURATION_S}",
            "-pix_fmt",
            "yuv420p",
            str(video_file),
        ],
        check=True,
    )
    return video_file.read_bytes()


@pytest.fixture
def extractor() -> VideoFrameExtractor:
    return VideoFrameExtractor(target_fps=TARGET_FPS)


@pytest.mark.parametrize("resize", [True, False])
def test_a_source_already_at_the_declared_shape_is_passed_through(
    extractor: VideoFrameExtractor, video_bytes: bytes, resize: bool
) -> None:
    frames = extractor.extract_frames(video_bytes, 0, DURATION_NS, SOURCE_SHAPE, resize)

    assert frames
    for frame in frames:
        assert frame.image.shape == (SOURCE_HEIGHT, SOURCE_WIDTH, BGR_CHANNELS)
        assert (frame.height, frame.width, frame.channels) == (SOURCE_HEIGHT, SOURCE_WIDTH, BGR_CHANNELS)


def test_a_source_differing_from_the_declared_shape_is_rejected_without_resize(
    extractor: VideoFrameExtractor, video_bytes: bytes
) -> None:
    """The recording cannot supply the geometry the policy is served at, and nothing may silently fix it."""
    with pytest.raises(ValueError, match="resize disabled"):
        extractor.extract_frames(video_bytes, 0, DURATION_NS, (224, 224), resize=False)


def test_frames_are_scaled_down_to_the_declared_shape(extractor: VideoFrameExtractor, video_bytes: bytes) -> None:
    frames = extractor.extract_frames(video_bytes, 0, DURATION_NS, (224, 224), resize=True)

    assert frames
    for frame in frames:
        assert frame.image.shape == (224, 224, BGR_CHANNELS)
        assert (frame.height, frame.width) == (224, 224)


def test_frames_are_scaled_up_to_the_declared_shape(extractor: VideoFrameExtractor, video_bytes: bytes) -> None:
    frames = extractor.extract_frames(video_bytes, 0, DURATION_NS, (720, 1280), resize=True)

    assert frames
    assert frames[0].image.shape == (720, 1280, BGR_CHANNELS)


def test_resampling_is_unaffected_by_scaling(extractor: VideoFrameExtractor, video_bytes: bytes) -> None:
    """A scaled decode must yield the same timeline as an unscaled one."""
    unscaled = extractor.extract_frames(video_bytes, 1_000, DURATION_NS, SOURCE_SHAPE, resize=False)
    scaled = extractor.extract_frames(video_bytes, 1_000, DURATION_NS, (224, 224), resize=True)

    assert len(scaled) == len(unscaled) == int(DURATION_S * TARGET_FPS)
    assert [frame.timestamp_ns for frame in scaled] == [frame.timestamp_ns for frame in unscaled]


def test_scaled_frames_carry_the_same_picture(extractor: VideoFrameExtractor, video_bytes: bytes) -> None:
    """A reinterpreted byte stream would satisfy the shape assertions above; per-channel means would not."""
    unscaled = extractor.extract_frames(video_bytes, 0, DURATION_NS, SOURCE_SHAPE, resize=False)
    scaled = extractor.extract_frames(video_bytes, 0, DURATION_NS, (240, 320), resize=True)

    for channel in range(BGR_CHANNELS):
        assert scaled[0].image[..., channel].mean() == pytest.approx(unscaled[0].image[..., channel].mean(), abs=2.0)


def test_shrinking_and_growing_use_the_kernel_inference_uses() -> None:
    assert _scale_kernel((SOURCE_HEIGHT, SOURCE_WIDTH), (168, 224)) == SHRINK_KERNEL
    assert _scale_kernel((SOURCE_HEIGHT, SOURCE_WIDTH), (720, 960)) == GROW_KERNEL


@pytest.mark.parametrize("shape", [(224, 224), (240, 320), (720, 1280)])
def test_scaling_matches_the_inference_adapter_within_rounding(
    extractor: VideoFrameExtractor, video_bytes: bytes, shape: tuple[int, int]
) -> None:
    """The dataset and the served observation must be the same transform, not merely a similar one.

    swscale left in the recorded ``yuv420p`` resizes the half-resolution chroma planes and drifts ~2
    grey levels from this reference, so the pixel format conversion has to precede the scale.
    """
    source = extractor.extract_frames(video_bytes, 0, DURATION_NS, SOURCE_SHAPE, resize=False)[0].image
    scaled = extractor.extract_frames(video_bytes, 0, DURATION_NS, shape, resize=True)[0].image

    geometry = compute_letterbox_geometry(SOURCE_SHAPE, shape)
    shrinking = geometry.width * geometry.height < SOURCE_WIDTH * SOURCE_HEIGHT
    reference = cv2.resize(
        source,
        (geometry.width, geometry.height),
        interpolation=cv2.INTER_AREA if shrinking else cv2.INTER_LINEAR,
    )
    reference = cv2.copyMakeBorder(
        reference,
        geometry.top,
        geometry.bottom,
        geometry.left,
        geometry.right,
        cv2.BORDER_CONSTANT,
        value=PAD_VALUE,
    )
    difference = np.abs(scaled.astype(np.int16) - reference.astype(np.int16))

    assert difference.mean() < 0.5
    assert np.percentile(difference, 99) <= 2


def test_aspect_ratio_change_is_warned_about(
    extractor: VideoFrameExtractor, video_bytes: bytes, warnings_log: list[str]
) -> None:
    extractor.extract_frames(video_bytes, 0, DURATION_NS, (224, 224), resize=True)

    assert any("pads 25% of the frame; the image occupies 224x168" in message for message in warnings_log)


def test_aspect_preserving_scale_is_not_warned_about(
    extractor: VideoFrameExtractor, video_bytes: bytes, warnings_log: list[str]
) -> None:
    extractor.extract_frames(video_bytes, 0, DURATION_NS, (240, 320), resize=True)

    assert not [message for message in warnings_log if "pads" in message]
