"""Video Frame Extractor for converting CompressedVideo to individual frames."""

import tempfile
from pathlib import Path

import ffmpeg  # type: ignore[import-untyped]
import numpy as np
from loguru import logger

from models.video_frame import VideoFrame

BGR_CHANNELS = 3


class VideoFrameExtractor:
    """Extract individual frames from CompressedVideo data with precise timing."""

    def __init__(self, target_fps: float = 20.0) -> None:
        """Initialize video frame extractor.

        Args:
            target_fps: Target frame rate for output (default 20 Hz)
        """
        self.target_fps: float = target_fps
        self.temp_files: list[Path] = []

        logger.debug(f"VideoFrameExtractor initialized with target FPS: {target_fps}")

    def extract_frames(
        self, compressed_video_data: bytes, start_timestamp_ns: int, duration_ns: int
    ) -> list[VideoFrame]:
        """Extract frames from CompressedVideo data with timestamps.

        Args:
            compressed_video_data: Raw MP4/AV1 video bytes
            start_timestamp_ns: Episode start time in nanoseconds
            duration_ns: Episode duration in nanoseconds

        Returns:
            List of frame dictionaries with timestamp and image data
        """
        logger.debug(f"Extracting frames from {len(compressed_video_data)} bytes of video data")
        logger.debug(f"Duration: {duration_ns / 1e9:.3f}s, Target FPS: {self.target_fps}")

        frames: list[VideoFrame] = []
        temp_video_path: Path | None = None

        try:
            # Write video data to temporary file
            temp_video_path = self._write_temp_video(compressed_video_data)
            frames = self._extract_frames_with_ffmpeg(temp_video_path, start_timestamp_ns, duration_ns)
            logger.info(f"Extracted {len(frames)} frames at {self.target_fps} Hz")
            return frames
        except Exception as e:
            logger.error(f"Failed to extract frames: {e}")
            raise
        finally:
            # Cleanup temporary file
            if temp_video_path and temp_video_path.exists():
                temp_video_path.unlink()
                if temp_video_path in self.temp_files:
                    self.temp_files.remove(temp_video_path)

    def _write_temp_video(self, video_data: bytes) -> Path:
        """Write video data to temporary file.

        Args:
            video_data: Raw video bytes

        Returns:
            Path to temporary video file
        """
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(video_data)

        self.temp_files.append(temp_path)
        logger.debug(f"Wrote {len(video_data)} bytes to temporary file: {temp_path}")
        return temp_path

    def _extract_frames_with_ffmpeg(
        self, video_path: Path, start_timestamp_ns: int, duration_ns: int
    ) -> list[VideoFrame]:
        """Extract frames by resampling the video to ``target_fps`` in a single ffmpeg pass.

        The ``fps`` filter resamples the whole stream in one invocation and streams raw
        ``bgr24`` frames over a stdout pipe (no temporary image files). Streaming avoids
        the large temp-disk burst and PNG encode/decode cost of writing frames to disk,
        and lets ffmpeg determine how many frames the stream actually yields (avoiding
        tail-seek failures past the end of the stream).
        """
        try:
            target_frame_count = int(duration_ns / 1e9 * self.target_fps)
            logger.debug(f"Target frame count for {self.target_fps} Hz: {target_frame_count}")

            if target_frame_count <= 0:
                return []

            width, height = self._probe_dimensions(video_path)
            frame_size = width * height * BGR_CHANNELS

            # Single pass: resample to target fps and stream raw frames over stdout.
            # ``vframes`` caps the count inside ffmpeg so it stops and exits cleanly on
            # its own (reading until EOF avoids killing it with a broken pipe). run_async
            # + incremental reads keep peak memory at one frame, instead of buffering the
            # entire raw stream (which would be many GiB for long videos).
            process = (
                ffmpeg.input(str(video_path))
                .filter("fps", fps=self.target_fps)
                .output("pipe:", format="rawvideo", pix_fmt="bgr24", vframes=target_frame_count)
                .run_async(pipe_stdout=True, pipe_stderr=True)
            )

            frame_interval_ns = duration_ns / target_frame_count
            frames: list[VideoFrame] = []
            try:
                while True:
                    raw_frame = self._read_exact(process.stdout, frame_size)
                    if raw_frame is None:
                        break

                    # ``np.frombuffer`` yields a read-only view backed by the pipe
                    # bytes; copy to an owned, writable, contiguous array (matching
                    # the previous ``cv2.imread`` semantics) and free the raw buffer.
                    frame_image = np.frombuffer(raw_frame, np.uint8).reshape((height, width, BGR_CHANNELS)).copy()

                    i = len(frames)
                    frame_timestamp_ns = start_timestamp_ns + int(i * frame_interval_ns)
                    frames.append(
                        VideoFrame(
                            frame_index=i,
                            timestamp_ns=frame_timestamp_ns,
                            video_frame_index=i,
                            image=frame_image,
                            height=height,
                            width=width,
                            channels=BGR_CHANNELS,
                        )
                    )
            finally:
                process.stdout.close()
                stderr = process.stderr.read()
                process.stderr.close()
                returncode = process.wait()

            if returncode != 0:
                detail = stderr.decode(errors="replace") if stderr else "unknown error"
                raise RuntimeError(f"ffmpeg exited with code {returncode}: {detail}")

            if len(frames) < target_frame_count:
                # Expected when the stream is slightly shorter than the
                # timestamp-derived duration; downstream sync tolerates it.
                logger.warning(
                    f"ffmpeg produced {len(frames)} frames, expected {target_frame_count} "
                    f"(stream shorter than timestamp duration)"
                )

            logger.debug(f"Extracted {len(frames)} frames using ffmpeg (single pass)")
            return frames

        except Exception as e:
            logger.error(f"FFmpeg frame extraction failed: {e}")
            raise

    def _probe_dimensions(self, video_path: Path) -> tuple[int, int]:
        """Return the (width, height) of the first video stream.

        Raw frames carry no headers, so the pixel dimensions must be known up front to
        reshape the byte stream into images.
        """
        probe = ffmpeg.probe(str(video_path))
        video_stream = next(
            (stream for stream in probe.get("streams", []) if stream.get("codec_type") == "video"),
            None,
        )
        if video_stream is None:
            raise ValueError(f"No video stream found in {video_path}")

        return int(video_stream["width"]), int(video_stream["height"])

    @staticmethod
    def _read_exact(stream: object, size: int) -> bytes | None:
        """Read exactly ``size`` bytes from a pipe, or ``None`` at clean end-of-stream.

        A single ``read`` on a pipe may return fewer bytes than requested, so loop until
        the full frame is collected. A partial trailing read indicates a truncated frame.
        """
        chunks: list[bytes] = []
        remaining = size
        while remaining > 0:
            chunk = stream.read(remaining)  # type: ignore[attr-defined]
            if not chunk:
                if chunks:
                    logger.warning(f"Discarding truncated final frame ({size - remaining}/{size} bytes)")
                return None
            chunks.append(chunk)
            remaining -= len(chunk)

        return b"".join(chunks)

    def close(self) -> None:
        """Clean up temporary files."""
        for temp_file in self.temp_files:
            if temp_file.exists():
                temp_file.unlink()
                logger.debug(f"Cleaned up temporary file: {temp_file}")

        self.temp_files.clear()
        logger.debug("VideoFrameExtractor closed")
