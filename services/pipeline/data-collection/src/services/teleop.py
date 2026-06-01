"""Teleoperation service logic.

This module provides the business logic for teleoperation operations.
"""

from __future__ import annotations

import threading
import time

from loguru import logger
from rclpy.executors import MultiThreadedExecutor

from configs.station import StationConfig
from helpers.rclpy_guard import safe_init
from models.teleop import TeleopResponse, TeleopStatusResponse
from services.franka_robot import FrankaRobotService
from services.teleop_robot_node import TeleopRobotNode
from state_machine.workflow import BaseWorkflowStateMachine


class TeleopService:
    """Service for handling teleoperation operations."""

    def __init__(
        self, station_config: StationConfig, state_machine: BaseWorkflowStateMachine, robot_service: FrankaRobotService
    ) -> None:
        """Initialize the teleoperation service.

        Args:
            station_config: Station configuration loaded from YAML.
            state_machine: State machine instance
            robot_service: Robot service instance for arm reset operations
        """
        self.station_config: StationConfig = station_config
        self.robot_service: FrankaRobotService = robot_service
        self.state_machine: BaseWorkflowStateMachine = state_machine
        self._nodes: list[TeleopRobotNode] = []
        self._executor: MultiThreadedExecutor | None = None
        self._ros_thread: threading.Thread | None = None
        self._ros_running: bool = False
        self._shutdown_lock: threading.Lock = threading.Lock()

    def _spin_executor(self) -> None:
        """Spin the ROS2 executor for teleop nodes in a background thread."""
        logger.info("Spinning ROS2 executor for teleop nodes")
        self._ros_running = True
        try:
            if self._executor is not None:
                self._executor.spin()
            else:
                logger.error("Executor is None, cannot spin.")
        except Exception as e:
            logger.error(f"ROS2 executor error: {e}")
        finally:
            self._ros_running = False
            logger.info("ROS2 executor stopped")

    def start_teleop(self) -> TeleopResponse:
        """Start teleoperation mode by transitioning the state machine and starting ROS nodes."""
        logger.info("Starting teleoperation")
        try:
            self.state_machine.get_ready()
        except Exception as e:
            logger.error(e)
            try:
                self.state_machine.get_idle()
            except Exception:
                logger.error("Failed to recover to IDLE after get_ready failure")
            raise e

        # Ensure rclpy is initialized safely once per process
        safe_init()

        with self._shutdown_lock:
            try:
                self._nodes = []
                for teleop_robot in self.station_config.embodiment.teleop_robots or []:
                    if teleop_robot.config.leader_topic and teleop_robot.config.follower_topic:
                        node = TeleopRobotNode(
                            name=f"{teleop_robot.id}".replace("-", "_").replace(" ", "_"),
                            ros_message_type=teleop_robot.config.ros_message_type,
                            leader_topic=teleop_robot.config.resolve_topic(teleop_robot.config.leader_topic),
                            follower_topic=teleop_robot.config.resolve_topic(teleop_robot.config.follower_topic),
                            transformations=teleop_robot.config.transformations,
                        )
                        self._nodes.append(node)

                self._executor = MultiThreadedExecutor()
                for node in self._nodes:
                    self._executor.add_node(node)
                    logger.info(f"Added node to executor: {node.get_name()}")

                logger.info(f"Created executor with {len(self._nodes)} nodes")
                self._ros_thread = threading.Thread(target=self._spin_executor, daemon=True)
                self._ros_thread.start()
            except Exception as e:
                logger.error(f"Exception during teleop node startup: {e}")
                self.shutdown()
                raise e

        logger.info("Teleoperation started successfully with ROS2 nodes")
        return TeleopResponse(status="success", message="Teleoperation started")

    def stop_teleop(self) -> TeleopResponse:
        """Stop teleoperation mode by transitioning the state machine and shutting down ROS nodes."""
        logger.info("Stopping teleoperation")
        try:
            self.state_machine.get_idle()
        except Exception as e:
            logger.error(f"State transition to IDLE failed: {e}")
            raise e

        threading.Thread(target=self.shutdown, daemon=True).start()
        logger.info("Teleoperation stopped, node cleanup running in background")
        return TeleopResponse(status="success", message="Teleoperation stopped")

    def start_syncing(self) -> TeleopResponse:
        """Start syncing mode by transitioning the state machine."""
        logger.info("Starting syncing")
        try:
            self.state_machine.start_syncing()
        except Exception as e:
            logger.error(f"State transition to SYNCING failed: {e}")
            try:
                self.state_machine.get_ready()
            except Exception:
                logger.error("Failed to recover to READY after start_syncing failure, falling back to IDLE")
                try:
                    self.state_machine.get_idle()
                except Exception:
                    logger.error("Failed to recover to IDLE after start_syncing failure")
            raise e

        logger.info("Syncing started successfully")
        return TeleopResponse(status="success", message="Syncing started")

    def shutdown(self) -> None:
        """Shutdown teleoperation resources and clean up ROS2 nodes and executor."""
        if not self._nodes and not self._executor and not self._ros_running:
            return

        with self._shutdown_lock:
            logger.info(f"Starting shutdown of {len(self._nodes)} teleop nodes")
            self._ros_running = False

            # Stop the executor first to halt all processing
            if self._executor:
                try:
                    logger.info("Shutting down executor...")
                    self._executor.shutdown(timeout_sec=1.0)
                except Exception as e:
                    logger.error(f"Error shutting down executor: {e}")

            # Stop the ROS thread
            if self._ros_thread and self._ros_thread.is_alive():
                try:
                    logger.info("Joining ROS thread...")
                    self._ros_thread.join(timeout=1.0)
                    if self._ros_thread.is_alive():
                        logger.warning("ROS thread did not terminate within timeout")
                except Exception as e:
                    logger.error(f"Error joining ROS thread: {e}")

            # Clean up and destroy nodes
            for node in self._nodes:
                try:
                    node_name: str = node.get_name()
                    logger.info(f"Destroying node: {node_name}")
                    node.cleanup()
                    node.destroy_node()  # type: ignore[no-untyped-call]
                except Exception as e:
                    logger.error(f"Error destroying node: {e}")

            # Clear everything
            self._nodes = []
            self._executor = None
            self._ros_thread = None

            # Wait for ROS2 discovery cleanup
            time.sleep(1.0)
            logger.info("Teleop shutdown completed")

    def get_teleop_status(self) -> TeleopStatusResponse:
        """Get the current status of teleoperation.

        Returns:
            A response indicating if teleoperation is active or not.
        """
        logger.info("Getting teleoperation status")

        is_active: bool = self.state_machine.current_state.name in ("READY", "SYNCING", "TELEOP")

        return TeleopStatusResponse(status="success", is_active=is_active)
