"""Recording service logic.

This module provides the business logic for recording operations.
"""

from __future__ import annotations

from uuid import UUID

import uuid7  # type: ignore[import-untyped]
from loguru import logger

from models.episode import EpisodeLabel
from models.recording import (
    DiscardRecordingResponse,
    SaveRecordingResponse,
    StartRecordingResponse,
    StopRecordingResponse,
)
from repos.data_recorder import DataRecorderRepo
from services.teleop import TeleopService
from state_machine.recording import RecordingStateMachine


class RecordingService:
    """Service for managing recordings."""

    def __init__(
        self,
        state_machine: RecordingStateMachine,
        data_recorder_repo: DataRecorderRepo,
        teleop_service: TeleopService,
    ) -> None:
        """Initialize the episode service.

        Args:
            state_machine: State machine instance for managing collection states.
            data_recorder_repo: Repository for communicating with the data recorder service.
            teleop_service: Service for teleoperation forwarding and control.
        """
        self.state_machine: RecordingStateMachine = state_machine
        self.data_recorder_repo: DataRecorderRepo = data_recorder_repo
        self.teleop_service: TeleopService = teleop_service

    def start_recording(self, task_id: UUID) -> StartRecordingResponse:
        """Start recording an episode."""
        episode_id: UUID = uuid7.create()
        logger.info(f"Starting recording episode {episode_id} for task {task_id}")

        try:
            self.state_machine.start_recording(episode_id=episode_id, task_id=task_id)
        except Exception as e:
            message = f"Failed to start recording for episode_id {episode_id} and task_id {task_id}: {e}"
            logger.error(message)
            return StartRecordingResponse(episode_id=episode_id, status="error", message=message)

        logger.info(f"Recording started successfully for episode_id: {episode_id}")
        return StartRecordingResponse(episode_id=episode_id, status="success", message="Recording started")

    def stop_recording(self) -> StopRecordingResponse:
        """Stop recording an episode."""
        try:
            self.state_machine.stop_recording()
        except Exception as e:
            message = f"Failed to stop recording: {e}"
            logger.error(message)
            return StopRecordingResponse(status="error", message=message)

        logger.info("Recording stopped successfully")
        return StopRecordingResponse(status="success", message="Recording stopped")

    def save_episode(self, label: EpisodeLabel, tags: list[str]) -> SaveRecordingResponse:
        """Save the current episode by transitioning the state machine."""
        try:
            self.state_machine.save(label, tags)
        except Exception as e:
            message = f"Failed to save episode with label {label} and tags {tags}: {e}"
            logger.error(message)
            return SaveRecordingResponse(status="error", message=message)

        logger.info("Episode saved successfully")
        return SaveRecordingResponse(status="success", message="Episode saved")

    def discard_episode(self) -> DiscardRecordingResponse:
        """Discard the current episode by transitioning the state machine."""
        try:
            self.state_machine.discard()
        except Exception as e:
            message = f"Failed to discard episode: {e}"
            logger.error(message)
            return DiscardRecordingResponse(status="error", message=message)

        logger.info("Episode discarded successfully")
        return DiscardRecordingResponse(status="success", message="Episode discarded")
