import contextlib
from pathlib import Path

import ffmpeg  # type: ignore[import-untyped]
import numpy as np
from loguru import logger

# These settings (except for GOP size) mirror the data-processor's VideoEncoder
# so the dataset videos are encoded identically to the recorded ones.
ENCODE_VCODEC = "libsvtav1"
ENCODE_PIX_FMT = "yuv420p"
INPUT_PIX_FMT = "bgr24"
INPUT_NDIM = 3  # bgr24 frames are 3-dimensional: (height, width, channels)
INPUT_CHANNELS = 3  # bgr24 is 3 channels (height, width, 3)
ENCODE_PRESET = 8
ENCODE_CRF = 30
# GOP (Group Of Pictures) size: number of frames between keyframes (I-frames).
# LeRobot uses GOP=2 for frequent keyframes, enabling better random access
# which is crucial for robotics applications where frame-level seeking is common.
ENCODE_GOP_SIZE = 2


class LeRobotVideoWriter:
    """Handles writing video files in the LeRobot directory structure.

    This class creates the appropriate directory hierarchy and writes MP4 video files
    for each camera and episode, organizing them by chunk and camera name
    """

    def __init__(self, output_dir: Path) -> None:
        """Initialize the LeRobotVideoWriter with the base output directory.

        Args:
            output_dir: Base output directory for LeRobot dataset
        """
        self.videos_dir: Path = output_dir / "videos"
        self.videos_dir.mkdir(parents=True, exist_ok=True)

    def write_video_from_frames(
        self,
        frames: list[np.ndarray],
        camera_name: str,
        episode_index: int,
        chunk_index: int = 0,
        fps: float = 20.0,
    ) -> Path:
        """Encode synchronized frames into an MP4 at the dataset's target FPS.

        Args:
            frames: Synchronized frames as ``bgr24`` ``(height, width, 3)`` arrays, one
                per Parquet row, in timeline order
            camera_name: Camera identifier (e.g. ``observation.images.head``)
            episode_index: Episode number
            chunk_index: Chunk number
            fps: Frame rate to encode at (the dataset target FPS)

        Returns:
            Path to written video file.
        """
        if not frames:
            raise ValueError(f"No frames provided for camera {camera_name} (episode {episode_index})")

        camera_dir: Path = self.videos_dir / f"chunk-{chunk_index:03d}" / camera_name
        camera_dir.mkdir(parents=True, exist_ok=True)
        video_file: Path = camera_dir / f"episode_{episode_index:06d}.mp4"

        first_frame = frames[0]
        if first_frame.ndim != INPUT_NDIM or first_frame.shape[2] != INPUT_CHANNELS:
            raise ValueError(
                f"Camera {camera_name} (episode {episode_index}) frames must be "
                f"(height, width, {INPUT_CHANNELS}) {INPUT_PIX_FMT} arrays, got shape {first_frame.shape}"
            )
        mismatch = next(((i, f.shape) for i, f in enumerate(frames) if f.shape != first_frame.shape), None)
        if mismatch is not None:
            index, shape = mismatch
            raise ValueError(
                f"Frame {index} for camera {camera_name} (episode {episode_index}) has shape {shape}, "
                f"expected {first_frame.shape}; all frames must share one resolution and channel count."
            )

        height, width = first_frame.shape[:2]

        process = (
            ffmpeg.input(
                "pipe:",
                format="rawvideo",
                pix_fmt=INPUT_PIX_FMT,
                s=f"{width}x{height}",
                framerate=fps,
            )
            .output(
                str(video_file),
                vcodec=ENCODE_VCODEC,
                pix_fmt=ENCODE_PIX_FMT,
                r=fps,
                preset=ENCODE_PRESET,
                crf=ENCODE_CRF,
                g=ENCODE_GOP_SIZE,
                movflags="+faststart",
                loglevel="error",
            )
            .overwrite_output()
            .run_async(pipe_stdin=True, pipe_stderr=True)
        )

        # ffmpeg may exit before all frames are written (e.g. bad args), which surfaces as a
        # BrokenPipeError on stdin.write. Capture it so the real cause from ffmpeg's stderr
        # (read in the finally block) is reported instead of the opaque pipe error.
        write_error: BrokenPipeError | None = None
        try:
            for frame in frames:
                process.stdin.write(np.ascontiguousarray(frame, dtype=np.uint8).tobytes())
        except BrokenPipeError as exc:
            write_error = exc
        finally:
            with contextlib.suppress(BrokenPipeError):
                process.stdin.close()
            stderr = process.stderr.read()
            process.stderr.close()
            returncode = process.wait()

        if returncode != 0:
            detail = stderr.decode(errors="replace") if stderr else "unknown error"
            raise RuntimeError(
                f"ffmpeg encode for {video_file} exited with code {returncode}: {detail}"
            ) from write_error
        if write_error is not None:
            raise write_error

        logger.info(f"Wrote video file: {video_file} ({len(frames)} frames @ {fps} fps)")

        return video_file
