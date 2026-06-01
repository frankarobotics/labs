from typing import Any
from uuid import UUID

from loguru import logger
from statemachine import Event, State, StateMachine

from models.db import EpisodeLabelDB, EpisodeStatusDB
from repos.data_recorder import DataRecorderRepo
from services.episode import EpisodeService


class RecordingStateMachine(StateMachine):
    """State machine for the recording mechanism.

    This state machine manages the transitions between different states
    when recording episodes: IDLE, RECORDING, and REVIEWING.
    Thread safety is provided by ``python-statemachine``'s built-in processing
    lock (available since 3.x).
    """

    def __init__(self, episode_service: EpisodeService, data_recorder_repo: DataRecorderRepo, **kwargs: Any) -> None:  # noqa: ANN401
        """Initialize the RecordingStateMachine with required service dependencies."""
        self.episode_service = episode_service
        self.data_recorder_repo = data_recorder_repo
        self.current_episode_id: UUID | None = None
        super().__init__(**kwargs)

    def after_transition(self, event: str, source: State, target: State) -> None:
        """Procedure called after every state transition."""
        logger.info(f"State transition: {source.id} -> {target.id} [event: {event}]")

    # Define states
    idle = State("IDLE", initial=True)
    recording = State("RECORDING")
    reviewing = State("REVIEWING")

    # Define events
    start_recording = Event(idle.to(recording))
    stop_recording = Event(recording.to(reviewing))
    save = Event(reviewing.to(idle))
    discard = Event(reviewing.to(idle))

    def before_start_recording(self, episode_id: UUID, task_id: UUID) -> None:
        """Create the episode in the database and start the data recorder."""
        self.current_episode_id = episode_id
        try:
            self.episode_service.create_episode(task_id, episode_id)
            # Start recording current episode
            recorder_response = self.data_recorder_repo.start_recording(episode_id)
            if recorder_response.status != "success":
                raise Exception(f"DataRecorder failed to start recording: {recorder_response.message}")
            # Update the status of the episode to recording
            self.episode_service.update_episode(episode_id, status=EpisodeStatusDB.RECORDING, message="")
        except Exception as e:
            self.current_episode_id = None
            try:
                self.episode_service.update_episode(episode_id, status=EpisodeStatusDB.ERROR, message=str(e))
            except Exception:
                logger.error(f"Failed to update episode status to ERROR for {episode_id}")
            raise

    def before_stop_recording(self) -> None:
        """Stop the data recorder and update the episode status to RECORDED."""
        episode_id = self.current_episode_id
        try:
            recorder_response = self.data_recorder_repo.stop_recording(episode_id)
            if recorder_response.status != "success":
                raise Exception(f"DataRecorder failed to stop recording: {recorder_response.message}")
            # Update entry in the database
            updated_episode = self.episode_service.update_episode(
                episode_id, status=EpisodeStatusDB.RECORDED, message=""
            )
            # Update episode metadata file
            self.episode_service.update_episode_metadata(
                episode_id, status=updated_episode.status, message=updated_episode.message
            )
            logger.info(f"Successfully stopped recording for episode {episode_id}")
        except Exception as e:
            try:
                self.episode_service.update_episode(episode_id, status=EpisodeStatusDB.ERROR, message=str(e))
            except Exception:
                logger.error(f"Failed to update episode status to ERROR for {episode_id}")
            raise

    def before_save(self, label: EpisodeLabelDB, tags: list[str]) -> None:
        """Persist the reviewed episode with a label and tags, then clear the current episode."""
        episode_id = self.current_episode_id
        try:
            self.episode_service.update_episode(
                episode_id, status=EpisodeStatusDB.SAVED, message="", label=label, tags=tags
            )
            self.episode_service.update_episode_metadata(
                episode_id, status=EpisodeStatusDB.SAVED, message="", label=label, tags=tags
            )
            self.current_episode_id = None
            logger.info(f"Episode {episode_id} saved successfully with label {label} and tags {tags}")
        except Exception as e:
            try:
                self.episode_service.update_episode(episode_id, status=EpisodeStatusDB.ERROR, message=str(e))
            except Exception:
                logger.error(f"Failed to update episode status to ERROR for {episode_id}")
            raise

    def before_discard(self) -> None:
        """Delete the recording and mark the episode as DISCARDED."""
        episode_id = self.current_episode_id
        try:
            recorder_response = self.data_recorder_repo.delete_recording(episode_id)
            if recorder_response.status != "success":
                raise Exception(f"DataRecorder failed to delete recording: {recorder_response.message}")
            # Update database entry
            updated_episode = self.episode_service.update_episode(
                episode_id, status=EpisodeStatusDB.DISCARDED, message=""
            )
            # Update episode metadata file
            self.episode_service.update_episode_metadata(episode_id, status=updated_episode.status)
            self.current_episode_id = None
            logger.info(f"Episode {episode_id} discarded successfully")
        except Exception as e:
            try:
                self.episode_service.update_episode(episode_id, status=EpisodeStatusDB.ERROR, message=str(e))
            except Exception:
                logger.error(f"Failed to update episode status to ERROR for {episode_id}")
            raise
