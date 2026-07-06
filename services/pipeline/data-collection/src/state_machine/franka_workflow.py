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

    def after_start_autorecovery(self) -> None:
        """Trigger all coordinators to autorecover.

        Uses the after hook, because we want the workflow state to reflect AUTORECOVERY immediately when one
        of the coordinators enters this state, other coordinators can follow afterwards.
        """
        try:
            self.robot_service.trigger_controller_coordinator("start_autorecovery")
        except Exception as e:
            logger.error(f"Failed to trigger autorecover: {e}")

    def _on_follower_state_changed(self, namespace: str, state: str) -> None:
        """React to a follower state change by aligning the workflow state machine."""
        if self.current_state == self.syncing and state == "FOLLOWING":
            self._on_coordinator_following(namespace)
        elif self.current_state in (self.following, self.syncing, self.ready) and state == "AUTORECOVERY":
            self._on_coordinator_autorecovery(namespace)
        elif self.current_state in (self.autorecovery, self.following, self.syncing) and state == "READY":
            self._on_coordinator_ready(namespace)
        elif self.current_state in (self.ready, self.autorecovery, self.following, self.syncing) and state == "IDLE":
            self._on_coordinator_idle(namespace)

    def _on_coordinator_following(self, namespace: str) -> None:
        # Only transition the workflow when all coordinators coordinator reached FOLLOWING
        pending = {ns: s for ns, s in self.robot_service.controller_coordinator_states.items() if s != "FOLLOWING"}
        if not pending:
            logger.info("All controller coordinators are FOLLOWING, transitioning workflow")
            self.start_following()
        else:
            logger.info(f"Controller coordinator {namespace!r} is FOLLOWING, waiting for {list(pending.keys())}")

    def _on_coordinator_autorecovery(self, namespace: str) -> None:
        logger.warning(f"Controller coordinator {namespace!r} entered AUTORECOVERY, mirroring workflow state")
        try:
            self.start_autorecovery()
        except Exception as e:
            logger.error(f"Failed to enter AUTORECOVERY workflow state after coordinator {namespace!r} dropped: {e}")

    def _on_coordinator_ready(self, namespace: str) -> None:
        # Only transition the workflow when all coordinators coordinator reached READY
        # in order to avoid broadcasting get_ready while one is still in AUTORECOVERY.
        pending = {ns: s for ns, s in self.robot_service.controller_coordinator_states.items() if s != "READY"}
        if pending:
            logger.info(f"Controller coordinator {namespace!r} is READY, waiting for {list(pending.keys())}")
            return
        logger.info("All controller coordinators are READY, transitioning workflow")
        try:
            self.get_ready()
        except Exception as e:
            logger.error(f"Failed to recover to READY after coordinator {namespace!r} dropped: {e}. Escaping to IDLE.")
            try:
                self.get_idle()
            except Exception as idle_e:
                logger.error(f"Failed to escape to IDLE: {idle_e}")

    def _on_coordinator_idle(self, namespace: str) -> None:
        logger.warning(f"Controller coordinator {namespace!r} dropped to IDLE, forcing workflow transition")
        try:
            self.get_idle()
        except Exception as e:
            logger.error(f"Failed to recover workflow to IDLE after coordinator {namespace!r} dropped: {e}")
