"""Video Encoder component for H.264 encoding with FFmpeg integration."""

import contextlib
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import cv2
import ffmpeg  # type: ignore[import-untyped]
import numpy as np
from loguru import logger

MIN_FRAMES_FOR_FRAME_RATE = 2
BGR_CHANNELS = 3
BGRA_CHANNELS = 4
EXPECTED_CHANNELS = BGR_CHANNELS  # output is always BGR


class VideoEncoder:
    """Handle H.264 encoding with FFmpeg integration."""

    def __init__(self, codec_settings: dict[str, Any] | None = None) -> None:
        """Initialize the video encoder.

        Args:
            codec_settings: Optional codec configuration
        """
        # Default codec settings matching LeRobot dataset standards
        # https://github.com/huggingface/lerobot/pull/302
        self.default_settings: dict[str, Any] = {
            # Constant Rate Factor (CRF): controls quality vs file size for x264.
            # Range: 0 (lossless/huge) -> 51 (worst). Lower = better quality/larger files.
            # LeRobot uses CRF=30 for optimal storage efficiency in robotics applications.
            "crf": 30,
            # Preset: encoding speed vs compression efficiency trade-off.
            # For libsvtav1: 0-12 (0=slowest/best quality, 12=fastest/lower quality)
            # For libx264: ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow
            # Preset 8 provides balanced encoding speed and compression for robotics data (equivalent to "medium")
            "preset": 8,
            # GOP (Group Of Pictures) size: number of frames between keyframes (I-frames).
            # ~1 keyframe per second @30fps keeps Foxglove scrubbing of the processed MCAP smooth
            # Dataset-builder re-encodes with its own (smaller) GOP for frame-level training seeks.
            "gop_size": 30,
            # Pixel format: chroma subsampling and layout. "yuv420p" is 8-bit 4:2:0 planar and widely compatible.
            # LeRobot standard format for broad compatibility with visualization tools.
            "pixel_format": "yuv420p",
            # Codec: the encoder implementation to use (FFmpeg name).
            # "libsvtav1" is the AV1 encoder, LeRobot standard for robotics datasets (better compression than H.264).
            "codec": "libsvtav1",
            # CPU thread limiting: reduce CPU usage by limiting threads
            # 0 = auto, positive number = specific thread count
            # Set to quarter of available cores to leave CPU for other processes
            "threads": 0,  # Will be auto-calculated to use quarter CPU cores
            # Nice value for the FFmpeg subprocess (0-19, higher = lower priority).
            # 19 = lowest priority, ensuring other processes are not starved.
            "nice": 19,
            # CPU core affinity: list of core indices the encoder is allowed to use.
            # None = auto (uses the upper quarter of cores).
            # Example: [8, 9, 10, 11] pins encoding to cores 8-11 only.
            "cpu_affinity": None,
        }

        # Merge with user settings
        self.codec_settings: dict[str, Any] = {**self.default_settings, **(codec_settings or {})}

        # Auto-calculate thread count if set to 0.
        cpu_count: int = os.cpu_count() or 4  # Fallback to 4 if can't detect
        if self.codec_settings["threads"] == 0:
            self.codec_settings["threads"] = max(1, cpu_count // 4)

        # Auto-calculate CPU affinity if set to None.
        if self.codec_settings["cpu_affinity"] is None:
            num_encoder_cores = max(1, cpu_count // 4)
            self.codec_settings["cpu_affinity"] = list(range(cpu_count - num_encoder_cores, cpu_count))

        # Temporary files for processing
        self.temp_files: list[Path] = []

        logger.info("Video Encoder initialized")
        logger.info(f"Codec settings: {self.codec_settings}")
        logger.info(
            f"Using {self.codec_settings['threads']} threads on cores {self.codec_settings['cpu_affinity']} "
            f"(of {cpu_count} available) at nice {self.codec_settings['nice']}"
        )

    def encode_frames(self, frames: list[dict[str, Any]], topic: str) -> tuple[bytes, dict[str, Any]]:
        """Encode frames to H.264 video using FFmpeg.

        Args:
            frames: List of frame data dictionaries
            topic: Source topic name for logging

        Returns:
            Tuple of (encoded_video_bytes, encoding_metadata)
        """
        if not frames:
            raise ValueError(f"No frames provided for encoding topic {topic}")

        logger.info(f"Encoding {len(frames)} frames from {topic}")

        # Sort frames by timestamp to ensure correct order
        sorted_frames: list[dict[str, Any]] = sorted(frames, key=lambda x: x["timestamp"])

        # Extract video parameters from first frame
        first_frame: dict[str, Any] = sorted_frames[0]
        width = first_frame["width"]
        height = first_frame["height"]
        encoding = first_frame["encoding"]

        logger.info(f"Video parameters: {width}x{height}, encoding: {encoding}")

        # Calculate frame rate from timestamps
        frame_rate: float = self._calculate_frame_rate(sorted_frames)
        logger.info(f"Calculated frame rate: {frame_rate:.2f} FPS")

        # Use configured GOP size
        gop_size: int = self.codec_settings["gop_size"]

        try:
            # Convert frames to OpenCV format and encode
            video_bytes: bytes = self._encode_with_ffmpeg(sorted_frames, width, height, frame_rate, gop_size)

            # Generate encoding metadata
            metadata: dict[str, Any] = {
                "total_frames": len(sorted_frames),
                "width": width,
                "height": height,
                "frame_rate": frame_rate,
                "encoding": encoding,
                "codec_settings": {**self.codec_settings, "gop_size": gop_size, "frame_rate": frame_rate},
                "timestamps": [frame["timestamp"] for frame in sorted_frames],
                "ros_timestamps": [frame["ros_timestamp"] for frame in sorted_frames],
                "frame_ids": [frame["frame_id"] for frame in sorted_frames],
                "duration_ms": (sorted_frames[-1]["timestamp"] - sorted_frames[0]["timestamp"]) / 1_000_000,
                "original_properties": {
                    "encoding": encoding,
                    "step": first_frame["step"],
                    "is_bigendian": first_frame["is_bigendian"],
                },
            }

            logger.info(f"Encoded video: {len(video_bytes)} bytes, {metadata['duration_ms']:.1f}ms duration")

            return video_bytes, metadata

        except Exception as e:
            logger.error(f"Failed to encode video for {topic}: {e}")
            raise

    def _calculate_frame_rate(self, frames: list[dict[str, Any]]) -> float:
        """Calculate frame rate from timestamps.

        Args:
            frames: List of frame data (must be sorted by timestamp)

        Returns:
            Frame rate in FPS
        """
        if len(frames) < MIN_FRAMES_FOR_FRAME_RATE:
            return 30.0  # Default fallback

        # Calculate intervals between consecutive frames (in nanoseconds)
        intervals = []
        for i in range(1, len(frames)):
            interval = frames[i]["timestamp"] - frames[i - 1]["timestamp"]
            if interval > 0:  # Skip any duplicate timestamps
                intervals.append(interval)

        if not intervals:
            return 30.0  # Fallback

        # Use median interval for robustness against outliers
        median_interval_ns = float(np.median(intervals))
        frame_rate: float = 1_000_000_000 / median_interval_ns  # Convert to FPS

        # Clamp to reasonable range
        return max(1.0, min(120.0, frame_rate))

    def _encode_with_ffmpeg(  # noqa: C901, PLR0915
        self, frames: list[dict[str, Any]], width: int, height: int, frame_rate: float, gop_size: int
    ) -> bytes:
        """Encode frames using FFmpeg with AV1 or H.264 format.

        Args:
            frames: List of frame data
            width: Video width
            height: Video height
            frame_rate: Target frame rate
            gop_size: Group of Pictures size

        Returns:
            Encoded video bytes (AV1 or H.264 format based on codec setting)
        """
        # Create temporary files for input and output.
        # libsvtav1 has an internal lookahead buffer that does not fully drain when
        # the encoder reads from a pipe, causing the last N frames to be silently
        # dropped from the bitstream while the MP4 container header still declares
        # the full duration. Writing raw frames to a file instead of piping gives
        # FFmpeg a seekable input stream, which allows the encoder to properly signal
        # end-of-stream and flush all buffered frames.
        suffix = ".mp4" if self.codec_settings["codec"] == "libsvtav1" else ".h264"
        with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as temp_input_file:
            temp_input = Path(temp_input_file.name)
            self.temp_files.append(temp_input)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
            temp_output = Path(temp_file.name)
            self.temp_files.append(temp_output)

        try:
            # Convert frames to raw video data and write incrementally to the temp input file.
            # Writing one frame at a time keeps peak Python heap at ~1 frame (~3 MB for 1280x720)
            # instead of holding the entire raw video (~950 MB for a 12s ZED episode) in RAM
            # before writing. The .raw file on disk is the same size either way.
            logger.info(f"Encoding {len(frames)} frames with FFmpeg...")
            expected_size = len(frames) * width * height * BGR_CHANNELS
            logger.info(f"Expected raw size: {len(frames)} * {width} * {height} * 3 = {expected_size} bytes")
            with temp_input.open("wb") as f:
                for frame_data in frames:
                    frame_array = self._ros_image_to_opencv(frame_data)
                    f.write(frame_array.tobytes())
            logger.info(f"Raw video data written: {temp_input.stat().st_size} bytes")

            # Prepare FFmpeg input stream from file (not pipe) so the encoder can
            # properly flush its lookahead buffer at end-of-stream.
            input_stream = ffmpeg.input(
                str(temp_input),
                format="rawvideo",
                pix_fmt="bgr24",  # OpenCV uses BGR
                s=f"{width}x{height}",
                r=frame_rate,
            )

            # Configure encoding based on codec type
            if self.codec_settings["codec"] == "libsvtav1":
                # AV1 encoding with SVT-AV1 - use MP4 container for AV1 streams
                # SVT-AV1 uses different thread parameters than standard FFmpeg
                output_stream = ffmpeg.output(
                    input_stream,
                    str(temp_output),
                    format="mp4",  # MP4 container supports AV1
                    vcodec=self.codec_settings["codec"],
                    crf=self.codec_settings["crf"],
                    preset=self.codec_settings["preset"],  # Numeric preset for libsvtav1
                    g=gop_size,  # GOP size
                    pix_fmt=self.codec_settings["pixel_format"],
                    **{
                        "svtav1-params": f"lp={self.codec_settings['threads']}",  # SVT-AV1 logical processors
                        "movflags": "+faststart",  # Optimize for streaming
                        "loglevel": "error",  # Reduce verbose output
                    },
                ).overwrite_output()
            else:
                # Handle string preset for libx264 fallback
                preset_value = self.codec_settings["preset"]
                if isinstance(preset_value, int):
                    preset_value = "medium"  # Convert numeric to string preset for x264

                # Fallback to H.264 encoding with Annex B format
                output_stream = ffmpeg.output(
                    input_stream,
                    str(temp_output),
                    format="h264",  # Raw H.264 stream
                    vcodec=self.codec_settings["codec"],
                    crf=self.codec_settings["crf"],
                    preset=preset_value,
                    g=gop_size,  # GOP size
                    pix_fmt=self.codec_settings["pixel_format"],
                    threads=self.codec_settings["threads"],  # Limit CPU usage
                    **{
                        "bf": 0,  # No B-frames (Foxglove requirement)
                        "bsf:v": "h264_mp4toannexb",  # Convert to Annex B format
                        "loglevel": "error",  # Reduce verbose output
                    },
                ).overwrite_output()

            try:
                cmd = ffmpeg.compile(output_stream)
                nice_value = self.codec_settings["nice"]
                affinity_cores = self.codec_settings["cpu_affinity"]

                def _set_low_priority() -> None:
                    """Pre-exec hook: lower priority & pin to designated cores."""
                    with contextlib.suppress(OSError):
                        os.nice(nice_value)
                    with contextlib.suppress(OSError):
                        if affinity_cores:
                            os.sched_setaffinity(0, affinity_cores)

                result = subprocess.run(  # noqa: S603
                    cmd,
                    capture_output=True,
                    check=False,
                    preexec_fn=_set_low_priority,
                )
                logger.info(f"FFmpeg stdout: {result.stdout.decode() if result.stdout else 'None'}")
                logger.info(f"FFmpeg stderr: {result.stderr.decode() if result.stderr else 'None'}")
                if result.returncode != 0:
                    raise ffmpeg.Error("ffmpeg", result.stdout, result.stderr)
            except ffmpeg.Error as e:
                logger.error(f"FFmpeg error: stdout={e.stdout.decode() if e.stdout else 'None'}")
                logger.error(f"FFmpeg error: stderr={e.stderr.decode() if e.stderr else 'None'}")
                raise

            # Read encoded video data
            with temp_output.open("rb") as f:
                encoded_bytes: bytes = f.read()

            if not encoded_bytes:
                raise RuntimeError("FFmpeg produced no output")

            logger.debug(f"FFmpeg encoding completed: {len(encoded_bytes)} bytes")
            return encoded_bytes

        except ffmpeg.Error as e:
            error_msg = e.stderr.decode() if e.stderr else "Unknown FFmpeg error"
            logger.error(f"FFmpeg encoding failed: {error_msg}")
            raise RuntimeError(f"FFmpeg encoding failed: {error_msg}") from e

        finally:
            # Clean up temporary files
            for tmp in (temp_input, temp_output):
                if tmp.exists():
                    tmp.unlink()
                if tmp in self.temp_files:
                    self.temp_files.remove(tmp)

    def _ros_image_to_opencv(self, frame_data: dict[str, Any]) -> np.ndarray:
        """Convert ROS Image message data to OpenCV format.

        Args:
            frame_data: Frame data dictionary from MCAP

        Returns:
            OpenCV image array
        """
        width = frame_data["width"]
        height = frame_data["height"]
        encoding = frame_data["encoding"]
        step = frame_data["step"]
        data = bytes(frame_data["data"])

        # Convert based on encoding
        if encoding == "bgr8":
            # Direct BGR format
            image_array = np.frombuffer(data, dtype=np.uint8).reshape(height, width, BGR_CHANNELS)
        elif encoding == "rgb8":
            # Convert RGB to BGR
            image_array = np.frombuffer(data, dtype=np.uint8).reshape(height, width, BGR_CHANNELS)
            image_array = cv2.cvtColor(image_array, cv2.COLOR_RGB2BGR)  # type: ignore[assignment]
        elif encoding == "bgra8":
            # Convert BGRA to BGR (drop alpha channel)
            bgra_array = np.frombuffer(data, dtype=np.uint8).reshape(height, width, BGRA_CHANNELS)
            image_array = cv2.cvtColor(bgra_array, cv2.COLOR_BGRA2BGR)  # type: ignore[assignment]
        elif encoding == "mono8":
            # Grayscale to BGR
            grayscale_array = np.frombuffer(data, dtype=np.uint8).reshape(height, width)
            image_array = cv2.cvtColor(grayscale_array, cv2.COLOR_GRAY2BGR)  # type: ignore[assignment]
        else:
            logger.warning(f"Unsupported encoding {encoding}, attempting direct conversion")
            # Attempt direct conversion assuming 3 channels
            bytes_per_pixel = step // width
            if bytes_per_pixel == BGR_CHANNELS:
                image_array = np.frombuffer(data, dtype=np.uint8).reshape(height, width, BGR_CHANNELS)
            else:
                raise ValueError(f"Unsupported image encoding: {encoding}")

        # Ensure we have a valid BGR image
        if image_array.shape != (height, width, EXPECTED_CHANNELS):
            raise ValueError(
                f"Invalid image shape: {image_array.shape}, expected: ({height}, {width}, {EXPECTED_CHANNELS})"
            )

        return image_array

    def close(self) -> None:
        """Close the video encoder and clean up resources."""
        # Clean up any remaining temporary files
        for temp_file in self.temp_files:
            if temp_file.exists():
                temp_file.unlink()
                logger.debug(f"Cleaned up temporary file: {temp_file}")

        self.temp_files.clear()
        logger.info("Video Encoder closed")
