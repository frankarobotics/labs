"""Record service logic.

This module provides the business logic for data recording operations.
Uses subprocess instead of threading for better isolation and to avoid ROS2 context issues.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import UUID

import uuid7  # type: ignore[import-untyped]
from loguru import logger

from configs.data_recorder import DataRecorderConfig
from models.record import (
    DeleteRecordResponse,
    RecordStateResponse,
    RecordStatusResponse,
    StartRecordResponse,
    StopRecordResponse,
)
from models.record_metadata import RecordMetadata
from repos.record_metadata import RecordMetadataRepo


class RecordService:
    """Service for handling data recording operations using subprocess.

    This class implements a singleton pattern and uses subprocesses to run ROS2 bag
    recording commands. It maintains thread safety with a lock to protect shared state
    from concurrent API requests.
    """

    _instance: RecordService | None = None

    def __new__(
        cls, config: DataRecorderConfig, record_metadata_repo: RecordMetadataRepo, ros_topics: list[str]
    ) -> RecordService:
        """Create or return the singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance."""
        # Clean up the existing instance if it exists
        if cls._instance is not None:
            try:
                cls._instance.shutdown()
            except Exception as e:
                logger.error(f"Error during RecordService cleanup: {e}")

            if hasattr(cls._instance, "_initialized"):
                delattr(cls._instance, "_initialized")
        cls._instance = None

    def __init__(
        self, config: DataRecorderConfig, record_metadata_repo: RecordMetadataRepo, ros_topics: list[str]
    ) -> None:
        """Initialize the record service.

        Args:
            config: Configuration for the data recorder.
            record_metadata_repo: Repository for record metadata operations.
            ros_topics: Topics to record, derived from the station config.

        Note:
            This constructor should not be called directly.
            Use the singleton pattern by calling RecordService(config, repo, topics).
        """
        # Only initialize once
        if hasattr(self, "_initialized"):
            return

        # Initialize instance variables
        self.is_recording = False
        self.episode_id: UUID | None = None
        self.recording_process: subprocess.Popen[bytes] | None = None
        self.config: DataRecorderConfig = config
        self.ros_topics: list[str] = ros_topics
        self.output_path = Path(self.config.output_path)
        self.record_metadata_repo: RecordMetadataRepo = record_metadata_repo
        self.lock = Lock()  # Lock for thread safety across concurrent API requests

        # Create output directory if it doesn't exist
        self.output_path.mkdir(parents=True, exist_ok=True)

        # Mark as initialized
        self._initialized = True

    def _get_episode_path(self, episode_id: UUID) -> Path:
        """Get the path for a specific episode.

        Args:
            episode_id: The unique identifier for the recording episode.

        Returns:
            The path where the episode data is stored.
        """
        # Use UUIDv7 to organise files by date: YYYY/MM/DD/UUID7.
        if episode_id.version == 7:  # noqa: PLR2004
            dt: datetime = uuid7.time(episode_id)
            return Path(f"{self.output_path}/{dt.strftime('%Y')}/{dt.strftime('%m')}/{dt.strftime('%d')}/{episode_id}")
        raise ValueError(f"Invalid UUID version {episode_id.version} for {episode_id=}")

    def _get_recording_path(self, episode_id: UUID) -> Path:
        """Get the current recording path.

        Args:
            episode_id: The unique identifier for the recording episode.

        Returns:
            The path where the recording data is stored.
        """
        dt: datetime = uuid7.time(episode_id)
        return Path(
            f"{self.config.output_path}/{dt.strftime('%Y')}/{dt.strftime('%m')}/{dt.strftime('%d')}/{episode_id}/mcap"
        )

    def _start_ros2_recording(self, episode_id: UUID, output_path: Path, topics: list[str]) -> subprocess.Popen[bytes]:
        """Start a ROS2 bag recording subprocess.

        Args:
            episode_id: The unique identifier for this recording episode
            output_path: Base path where recordings should be stored
            topics: List of ROS2 topics to record

        Returns:
            A subprocess.Popen instance for the recording process

        Raises:
            subprocess.SubprocessError: If the process cannot be started
            FileNotFoundError: If ros2 command is not found
            ValueError: If no topics are provided for recording
        """
        # Validate topics
        if not topics:
            raise ValueError("No topics provided for recording")

        # Set up the recording path
        recording_path: Path = self._get_recording_path(episode_id)
        recording_path.parent.mkdir(parents=True, exist_ok=True)

        # Construct the ros2 bag record command - fixed arguments that don't depend on user input
        cmd: list[str] = [
            "ros2",
            "bag",
            "record",
            "-o",
            str(recording_path),
            "-s",
            "mcap",  # Storage format
            "--include-hidden-topics",  # Include hidden topics
        ]

        # Add each topic individually - these come from configuration
        for topic in topics:
            cmd.append(topic)

        logger.info(f"Starting recording process with command: {' '.join(cmd)}")

        try:
            # Redirect stdout/stderr to DEVNULL to prevent the child from
            # blocking on pipe writes (64KB buffer) when nobody reads them —
            # a blocked process cannot execute Python signal handlers.
            proc: subprocess.Popen[bytes] = subprocess.Popen(  # noqa: S603
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return proc
        except subprocess.SubprocessError as e:
            error_msg = f"Failed to start recording process: {e}"
            logger.error(error_msg)
            raise

    def _add_file_size_to_metadata(self, episode_id: UUID, metadata: RecordMetadata) -> None:
        """Calculate and add file size information to metadata.

        Args:
            episode_id: The unique identifier for the recording episode
            metadata: The metadata object to update
        """
        recording_path: Path = self._get_recording_path(episode_id)

        # First, look for MCAP files directly in the recording directory
        mcap_files: list[Path] = list(recording_path.glob("*.mcap"))
        if not mcap_files:
            logger.warning(f"No MCAP files found in {recording_path}")
            return

        # Calculate total size of all MCAP files
        total_size_bytes: int = sum(f.stat().st_size for f in mcap_files)

        # Get formatted size
        size_bytes, human_readable = self._format_file_size(total_size_bytes)

        # Set size in metadata
        metadata.file_size_bytes = size_bytes

        logger.info(f"Recorded data size: {human_readable} ({len(mcap_files)} files)")

    def _format_file_size(self, size_bytes: int) -> tuple[int, str]:
        """Format file size into human-readable format.

        Args:
            size_bytes: File size in bytes

        Returns:
            Tuple of (size in bytes, human-readable size string)
        """
        bytes_in_kb = 1000
        bytes_in_mb = bytes_in_kb * 1000
        bytes_in_gb = bytes_in_mb * 1000

        if size_bytes < bytes_in_kb:
            return size_bytes, f"{size_bytes} B"
        if size_bytes < bytes_in_mb:
            return size_bytes, f"{size_bytes / bytes_in_kb:.2f} KB"
        if size_bytes < bytes_in_gb:
            return size_bytes, f"{size_bytes / bytes_in_mb:.2f} MB"
        return size_bytes, f"{size_bytes / bytes_in_gb:.2f} GB"

    def _stop_ros2_recording(self, process: subprocess.Popen[bytes], timeout: int = 5) -> bool:
        """Stop a ROS2 bag recording subprocess.

        Sends SIGTERM to the process for graceful shutdown (ros2 bag record
        explicitly handles SIGTERM via Python's signal module). Falls back
        to SIGKILL on the process group if it doesn't terminate in time.

        Args:
            process: The subprocess.Popen instance to stop
            timeout: Seconds to wait for graceful shutdown before SIGKILL

        Returns:
            True if the process was stopped gracefully, False if forced
        """
        if process is None or process.poll() is not None:
            return True

        try:
            # Send SIGTERM to the main process. ros2 bag record registers a
            # Python-level SIGTERM handler that triggers graceful shutdown.
            logger.info(f"Sending SIGTERM to recording process (PID {process.pid})")
            os.kill(process.pid, signal.SIGTERM)

            try:
                process.wait(timeout=timeout)
                logger.info("Recording process terminated gracefully")
                return True
            except subprocess.TimeoutExpired:
                logger.warning(f"Process did not terminate within {timeout}s, sending SIGKILL")
                process.kill()
                process.wait()
                logger.info("Recording process killed")
                return False
        except Exception as e:
            logger.error(f"Error stopping recording process: {e}")
            with contextlib.suppress(Exception):
                process.kill()
                process.wait()
            return False

    def _get_process_output(self, process: subprocess.Popen[bytes] | None) -> tuple[str, str]:
        """Get the stdout and stderr output from a process.

        Note: With DEVNULL pipes, no output is available. This method exists
        for interface compatibility and always returns empty strings.

        Args:
            process: The subprocess.Popen instance to get output from

        Returns:
            Tuple of (stdout, stderr) as empty strings
        """
        return "", ""

    def start_recording(self, episode_id: UUID) -> StartRecordResponse:
        """Start recording data using a subprocess.

        Args:
            episode_id: The unique identifier for this recording episode.

        Returns:
            A response indicating the result of the operation.

        Notes:
            Uses subprocess to run ROS2 bag record command.
            The lock ensures that only one recording can be active at a time.
        """
        logger.info(
            f"Start recording with requested episode ID: {episode_id}, "
            f"episode_id: {self.episode_id}, is_recording: {self.is_recording}, RecordService ID: {id(self)}"
        )

        with self.lock:
            # Check if already recording and validate state
            if self.is_recording:
                logger.warning(f"Recording already in progress with episode ID: {self.episode_id}")
                return StartRecordResponse(status="error", message="Recording already in progress")

            # Validate ROS topics are configured
            if not self.ros_topics:
                error_msg: str = "No ROS topics derived from config_station.yml. Check your configuration."
                logger.error(error_msg)
                return StartRecordResponse(status="error", message=error_msg)

            metadata: RecordMetadata | None
            try:
                self.episode_id = episode_id

                # Create record metadata file
                now: datetime = datetime.now(timezone.utc)
                metadata = RecordMetadata(
                    episode_id=episode_id,
                    topics=self.ros_topics,
                    format="mcap",
                    serialization_format="cdr",
                    recording_software="rosbag2_py",
                    start_timestamp_iso=now.isoformat(),
                    status="starting",
                )
                self.record_metadata_repo.create(metadata)

                # Start the recording process
                self.recording_process = self._start_ros2_recording(
                    episode_id=episode_id, output_path=self.output_path, topics=self.ros_topics
                )

                # Give the process a moment to start and check if it's still running
                time.sleep(0.5)
                if self.recording_process is None or self.recording_process.poll() is not None:
                    # Process exited immediately, check stderr
                    _, stderr = self._get_process_output(self.recording_process)
                    self.recording_process = None
                    self.episode_id = None

                    # Update metadata to reflect error
                    metadata.status = "error"
                    metadata.error_message = f"Recording process failed to start: {stderr}"
                    self.record_metadata_repo.update(metadata)

                    error_msg = f"Recording process failed to start: {stderr}"
                    logger.error(error_msg)
                    return StartRecordResponse(status="error", message=error_msg)

                # Mark as recording
                self.is_recording = True

                # Update metadata to reflect active state
                metadata.status = "recording"
                self.record_metadata_repo.update(metadata)

                logger.info(f"Successfully started recording with episode ID: {self.episode_id}")
                return StartRecordResponse(
                    status="success", message=f"Recording started with episode ID: {self.episode_id}"
                )

            except Exception as e:
                logger.error(f"Failed to start recording: {e}")
                if self.recording_process:
                    try:
                        self.recording_process.terminate()
                    except Exception as term_error:
                        logger.warning(f"Failed to terminate recording process: {term_error}")
                    self.recording_process = None

                # Update metadata to reflect error
                metadata = self.record_metadata_repo.read(episode_id)
                if metadata:
                    metadata.status = "error"
                    metadata.error_message = f"Failed to start recording: {e}"
                    self.record_metadata_repo.update(metadata)

                self.episode_id = None
                self.is_recording = False
                return StartRecordResponse(status="error", message=f"Failed to start recording: {e}")

    def stop_recording(self) -> StopRecordResponse:
        """Stop recording data by terminating the subprocess.

        Returns:
            A response indicating the result of the operation.
        """
        logger.info(f"Stop recording, current episode ID: {self.episode_id}")

        with self.lock:
            # Check if recording is in progress
            if not self.is_recording:
                error_msg = "No recording in progress to stop"
                logger.warning(error_msg)
                return StopRecordResponse(status="error", message=error_msg)

            try:
                # Save current episode ID before resetting it
                completed_episode_id: UUID | None = self.episode_id

                # Stop the subprocess if it exists
                self._stop_recording_process()

                # Update metadata
                self._update_recording_metadata(self.episode_id)

                # Reset recording state
                self.is_recording = False
                self.episode_id = None

                logger.info(f"Recording stopped for episode ID: {completed_episode_id}")
                return StopRecordResponse(
                    status="success", message=f"Recording stopped for episode ID: {completed_episode_id}"
                )
            except Exception as e:
                logger.error(f"Failed to stop recording: {e}")
                return StopRecordResponse(status="error", message=f"Failed to stop recording: {e}")

    def _stop_recording_process(self) -> None:
        """Helper method to stop the recording process.

        Handles stopping the process and capturing output.
        """
        if not self.recording_process:
            logger.warning("No recording process to stop")
            return

        logger.info(f"Stopping recording process for episode {self.episode_id}")

        # Stop the process
        self._stop_ros2_recording(self.recording_process)

        # Get process output for logging
        stdout, stderr = self._get_process_output(self.recording_process)
        if stdout:
            logger.debug(f"Recording process stdout: {stdout}")
        if stderr:
            logger.debug(f"Recording process stderr: {stderr}")

        self.recording_process = None

    def _update_recording_metadata(self, episode_id: UUID) -> None:
        """Update metadata when recording stops.

        Args:
            episode_id: The episode ID of the recording

        Raises:
            ValueError: If no metadata is found for the episode ID
        """
        metadata: RecordMetadata | None = self.record_metadata_repo.read(episode_id)
        if metadata is None:
            logger.warning(f"No existing metadata found for episode ID {episode_id}")
            raise ValueError(f"No existing metadata found for episode ID {episode_id}")

        now: datetime = datetime.now(timezone.utc)
        metadata.end_timestamp_iso = now.isoformat()

        # Calculate duration correctly
        if metadata.start_timestamp_iso:
            metadata.duration_seconds = (
                now.timestamp() - datetime.fromisoformat(metadata.start_timestamp_iso).timestamp()
            )

        # Add file size information
        self._add_file_size_to_metadata(episode_id, metadata)

        # Update status
        metadata.status = "completed"
        self.record_metadata_repo.update(metadata)

    def get_recording_status(self, episode_id: UUID) -> RecordStatusResponse:
        """Get the current status of recording.

        Args:
            episode_id: The episode ID to verify against the current recording.
                       Used for logging and verification purposes.

        Returns:
            A response indicating if recording is active or not, and metadata if available.

        Raises:
            ValueError: If no metadata is found for the episode ID.
        """
        logger.info(f"Get recording status, requested episode ID: {episode_id}")

        with self.lock:
            # Attempt to get metadata first
            metadata: RecordMetadata | None = self.record_metadata_repo.read(episode_id)
            if metadata is None:
                logger.warning(f"No existing metadata found for episode ID {episode_id}")
                return RecordStatusResponse(status="error", is_recording=False, episode_id=None, metadata=None)

            # Check if the provided episode_id matches the current recording
            if self.episode_id != episode_id:
                logger.warning(f"Episode ID mismatch: requested {episode_id}, current {self.episode_id}")

                # If we have metadata but it's not the active recording, just return its status
                return RecordStatusResponse(
                    status="success", is_recording=False, episode_id=episode_id, metadata=metadata.model_dump()
                )

            # If recording process exited unexpectedly, update status
            if self.is_recording and self.recording_process:
                if self.recording_process.poll() is not None:
                    logger.warning("Recording process exited unexpectedly")
                    self.is_recording = False
                    metadata.status = "error"
                    metadata.error_message = "Recording process exited unexpectedly"
                    self.record_metadata_repo.update(metadata)
                elif metadata.status != "recording":
                    # If still running, update metadata with current status
                    metadata.status = "recording"
                    self.record_metadata_repo.update(metadata)

            return RecordStatusResponse(
                status="success",
                is_recording=self.is_recording and self.episode_id == episode_id,
                episode_id=self.episode_id,
                metadata=metadata.model_dump(),
            )

    def delete_recording(self, episode_id: UUID) -> DeleteRecordResponse:
        """Delete a recorded episode.

        Args:
            episode_id: The episode ID to delete.

        Returns:
            A response indicating the result of the operation.
        """
        logger.info(f"Delete recording for episode ID: {episode_id}")

        with self.lock:
            # If we're currently recording this episode, we can't delete it
            if self.is_recording and self.episode_id == episode_id:
                error_msg: str = "Cannot delete the recording while it is in progress. Stop recording first."
                logger.warning(error_msg)
                return DeleteRecordResponse(status="error", message=error_msg)

            # Get the episode directory
            episode_path: Path = self._get_episode_path(episode_id)

            # Check if the episode directory exists
            if not episode_path.exists():
                error_msg = f"Recording for episode ID {episode_id} not found"
                logger.warning(error_msg)
                return DeleteRecordResponse(status="error", message=error_msg)

            # Verify it's a directory
            if not episode_path.is_dir():
                error_msg = f"Path for episode ID {episode_id} is not a directory"
                logger.warning(error_msg)
                return DeleteRecordResponse(status="error", message=error_msg)

            try:
                # Attempt to delete the metadata from repository first (if it exists)
                self.record_metadata_repo.delete(episode_id)

                # Delete the entire episode directory and its contents
                shutil.rmtree(episode_path)

                success_msg: str = f"Recording for episode ID {episode_id} deleted successfully"
                logger.info(success_msg)
                return DeleteRecordResponse(status="success", message=success_msg)
            except PermissionError as e:
                error_msg = f"Permission error when deleting recording: {e}"
                logger.error(error_msg)
                return DeleteRecordResponse(status="error", message=error_msg)
            except Exception as e:
                error_msg = f"Failed to delete recording for episode ID {episode_id}: {e}"
                logger.error(error_msg)
                return DeleteRecordResponse(status="error", message=f"Failed to delete recording: {e}")

    def shutdown(self) -> None:
        """Clean up resources when the service is shutting down."""
        logger.info("Shutting down RecordService")

        with self.lock:
            # Stop any active recording
            if self.is_recording and self.recording_process:
                try:
                    logger.info("Stopping active recording during shutdown")
                    self._stop_recording_process()

                    # Update metadata to reflect forced stop
                    if self.episode_id:
                        try:
                            metadata: RecordMetadata | None = self.record_metadata_repo.read(self.episode_id)
                            if metadata:
                                metadata.status = "interrupted"
                                metadata.error_message = "Recording stopped due to service shutdown"
                                metadata.end_timestamp_iso = datetime.now(timezone.utc).isoformat()
                                self.record_metadata_repo.update(metadata)
                        except Exception as e:
                            logger.error(f"Error updating metadata during shutdown: {e}")

                except Exception as e:
                    logger.error(f"Error stopping recording during shutdown: {e}")
                finally:
                    self.is_recording = False
                    self.episode_id = None
                    self.recording_process = None

    def get_record_state(self) -> RecordStateResponse:
        """Get the current state of recorder.

        Returns:
            A response indicating if recorder is active or not
        """
        logger.info(f"Get record state. Current episode ID: {self.episode_id}")

        with self.lock:
            return RecordStateResponse(
                status="success",
                is_recording=self.is_recording,
                episode_id=self.episode_id,
            )
