"""Video Frame Extractor for converting CompressedVideo to individual frames."""

import tempfile
from pathlib import Path

import cv2
import ffmpeg  # type: ignore[import-untyped]
from loguru import logger

from models.video_frame import VideoFrame

COLOR_FRAME_SHAPE_LEN = 3


class VideoFrameExtractor:
    """Extract individual frames from CompressedVideo data with precise timing."""

    def __init__(self, target_fps: float = 20.0) -> None:
        """Initialize video frame extractor.

        Args:
            target_fps: Target frame rate for output (default 20 Hz)
        """
        self.target_fps: float = target_fps
        self.temp_files: list[Path] = []

        logger.info(f"VideoFrameExtractor initialized with target FPS: {target_fps}")

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
        logger.info(f"Extracting frames from {len(compressed_video_data)} bytes of video data")
        logger.info(f"Duration: {duration_ns / 1e9:.3f}s, Target FPS: {self.target_fps}")

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
        """Extract frames using ffmpeg for AV1 videos that OpenCV can't handle."""
        try:
            # Calculate target frame count
            target_frame_count = int(duration_ns / 1e9 * self.target_fps)
            logger.info(f"Target frame count for {self.target_fps} Hz: {target_frame_count}")

            if target_frame_count == 0:
                return []

            # Create temporary directory for frames
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_dir_path = Path(temp_dir)

                # Calculate time interval between frames
                frame_interval_s = (duration_ns / 1e9) / target_frame_count if target_frame_count > 0 else 0

                frames: list[VideoFrame] = []
                for i in range(target_frame_count):
                    # Calculate seek time for this frame
                    seek_time_s = i * frame_interval_s

                    # Extract single frame at specific timestamp
                    frame_output: Path = temp_dir_path / f"frame_{i:06d}.png"

                    try:
                        (
                            ffmpeg.input(str(video_path), ss=seek_time_s)
                            .output(str(frame_output), vframes=1)
                            .overwrite_output()
                            .run(quiet=True, capture_stderr=True)
                        )

                        if frame_output.exists():
                            # Load frame with OpenCV
                            frame_image = cv2.imread(str(frame_output))
                            if frame_image is not None:
                                frame_timestamp_ns = start_timestamp_ns + int(i * (duration_ns / target_frame_count))

                                frame_data = VideoFrame(
                                    frame_index=i,
                                    timestamp_ns=frame_timestamp_ns,
                                    video_frame_index=i,  # Approximate
                                    image=frame_image.copy(),
                                    height=frame_image.shape[0],
                                    width=frame_image.shape[1],
                                    channels=frame_image.shape[2]
                                    if len(frame_image.shape) == COLOR_FRAME_SHAPE_LEN
                                    else 1,
                                )
                                frames.append(frame_data)
                        else:
                            logger.warning(f"Failed to extract frame {i} with ffmpeg")

                    except ffmpeg.Error as e:
                        logger.warning(
                            f"FFmpeg failed to extract frame {i}: {e.stderr.decode() if e.stderr else str(e)}"
                        )
                        continue

                logger.info(f"Extracted {len(frames)} frames using ffmpeg")
                return frames

        except Exception as e:
            logger.error(f"FFmpeg frame extraction failed: {e}")
            raise

    def close(self) -> None:
        """Clean up temporary files."""
        for temp_file in self.temp_files:
            if temp_file.exists():
                temp_file.unlink()
                logger.debug(f"Cleaned up temporary file: {temp_file}")

        self.temp_files.clear()
        logger.info("VideoFrameExtractor closed")
