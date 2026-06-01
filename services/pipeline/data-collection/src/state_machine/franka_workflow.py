from __future__ import annotations

from typing import Any

from loguru import logger

from services.franka_robot import FrankaRobotService
from state_machine.workflow import BaseWorkflowStateMachine


class FrankaWorkflowStateMachine(BaseWorkflowStateMachine):
    """Franka-specific workflow state machine.

    Implements ``BaseWorkflowStateMachine`` for Franka robots, delegating
    state transition actions to the ``RobotService`` which communicates with
    the controller coordinator over ROS 2.
    """

    def __init__(self, robot_service: FrankaRobotService, **kwargs: Any) -> None:  # noqa: ANN401
        """Initialize the FrankaWorkflowStateMachine with the given robot service."""
        self.robot_service = robot_service
        super().__init__(**kwargs)

    def _register_service_callbacks(self) -> None:
        self.robot_service.register_controller_coordinator_state_callback(self._on_follower_state_changed)

    def before_get_ready(self) -> None:
        """Trigger the controller coordinator to get READY and wait for all coordinators to confirm.

        Raises:
            RuntimeError: If the ROS call fails or coordinators do not reach READY
                within the specified timeout.
        """
        try:
            self.robot_service.trigger_controller_coordinator("get_ready")
            self.robot_service.wait_for_matching_controller_coordinator_states({"READY"})
        except Exception as e:
            logger.error(f"Failed to get READY state: {e}.")
            raise

    def before_start_syncing(self) -> None:
        """Trigger the controller coordinator to start operating and wait for all coordinators to confirm.

        Raises:
            RuntimeError: If the ROS call fails or coordinators do not reach SYNCING
                within the specified timeout.
        """
        try:
            self.robot_service.trigger_controller_coordinator("start_operating")
            self.robot_service.wait_for_matching_controller_coordinator_states({"SYNCING", "FOLLOWING"})
        except Exception as e:
            logger.error(f"Failed to get SYNCING state: {e}.")
            raise

    def before_get_idle(self) -> None:
        """Trigger the controller coordinator to stop and wait for all coordinators to confirm.

        Error should be forwarded to the user as the controllers might be still running.

        Raises:
            RuntimeError: If the ROS call fails or coordinators do not reach IDLE
                within the specified timeout.
        """
        try:
            self.robot_service.trigger_controller_coordinator("stop")
            self.robot_service.wait_for_matching_controller_coordinator_states({"IDLE"}, timeout=5.0)
        except Exception as e:
            logger.error(f"Failed to confirm IDLE state on controller coordinator (continuing to IDLE): {e}")
            raise

    def _on_follower_state_changed(self, namespace: str, state: str) -> None:
        """React to a follower state change by aligning the workflow state machine.

        Forces the workflow (and hence all other controller coordinators) into the
        same state when any individual coordinator drops unexpectedly.
        Automatically transitions SYNCING -> FOLLOWING when all coordinators report FOLLOWING.
        """
        if self.current_state == self.syncing and state == "FOLLOWING":
            pending = {ns: s for ns, s in self.robot_service.controller_coordinator_states.items() if s != "FOLLOWING"}
            if not pending:
                logger.info("All controller coordinators are FOLLOWING, transitioning workflow")
                self.start_following()
            else:
                logger.info(f"Controller coordinator {namespace!r} is FOLLOWING, waiting for {list(pending.keys())}")
        elif self.current_state in (self.following, self.syncing) and state == "READY":
            logger.warning(f"Controller coordinator {namespace!r} dropped to READY, forcing workflow transition")
            try:
                self.get_ready()
            except Exception as e:
                logger.error(f"Failed to recover workflow to READY after coordinator {namespace!r} dropped: {e}")
        elif self.current_state in (self.ready, self.following, self.syncing) and state == "IDLE":
            logger.warning(f"Controller coordinator {namespace!r} dropped to IDLE, forcing workflow transition")
            try:
                self.get_idle()
            except Exception as e:
                logger.error(f"Failed to recover workflow to IDLE after coordinator {namespace!r} dropped: {e}")
