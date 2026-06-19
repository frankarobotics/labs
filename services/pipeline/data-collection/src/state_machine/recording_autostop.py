"""Bridge listener that stops an active recording when the workflow leaves FOLLOWING."""

from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from loguru import logger
from state_machine.recording import RecordingStateMachine


class RecordingAutoStopListener:
    """Workflow state machine listener that stops an active recording when leaving FOLLOWING."""

    def __init__(self, recording_sm: RecordingStateMachine) -> None:
        """Initialize the listener with the recording state machine to control."""
        self._recording_sm = recording_sm
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rec_autostop")

    def on_exit_following(self) -> None:
        """Schedule a recording stop when the workflow exits FOLLOWING.

        Fires on every exit of FOLLOWING (-> READY / IDLE / AUTORECOVERY). The work
        is offloaded to a worker thread so the workflow transition is never stalled.
        """
        self._executor.submit(self._stop_if_recording)

    def _stop_if_recording(self) -> None:
        """Stop the recording if one is currently active (stop-to-review)."""
        try:
            if self._recording_sm.current_state == self._recording_sm.recording:
                logger.info("Workflow left FOLLOWING while recording, auto-stopping recording")
                self._recording_sm.stop_recording()
        except Exception:
            logger.exception("Auto-stop recording failed after workflow left FOLLOWING")
