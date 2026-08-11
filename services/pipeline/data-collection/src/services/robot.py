from __future__ import annotations

import contextlib
import threading

import rclpy  # type: ignore
import rclpy.executors  # type: ignore
import rclpy.node  # type: ignore
from loguru import logger
from pipeline_configs.station import StationConfig


class BaseRobotService:
    """Base class for robot services.

    Handles generic ROS 2 lifecycle (node initialisation and cleanup).
    """

    def __init__(self, station_config: StationConfig) -> None:
        """Initialize the robot service and set up the ROS 2 node."""
        self.station_config: StationConfig = station_config
        self.node: rclpy.node.Node | None = None
        self._initialized_rclpy: bool = False
        self._spin_executor: rclpy.executors.SingleThreadedExecutor | None = None
        self._spin_thread: threading.Thread | None = None
        self._initialize_ros2()

    def _initialize_ros2(self) -> None:
        """Initialize rclpy, create a persistent ROS 2 node, and spin it in a background thread."""
        try:
            if not rclpy.ok():
                rclpy.init()
                self._initialized_rclpy = True
            self.node = rclpy.create_node("robot_service_node")
            # Spin the node in a background thread so subscriptions (e.g. coordinator
            # state topics) are delivered continuously without manual spin_once calls.
            self._spin_executor = rclpy.executors.SingleThreadedExecutor()
            self._spin_executor.add_node(self.node)
            self._spin_thread = threading.Thread(
                target=self._spin_executor.spin, daemon=True, name="robot_service_spin"
            )
            self._spin_thread.start()
            logger.info(f"ROS2 initialized successfully for {type(self).__name__}")
        except Exception as e:
            logger.warning(f"Failed to initialize ROS2: {e}")
            self.node = None

    def cleanup(self) -> None:
        """Destroy the ROS 2 node and shut down rclpy if this instance owns it."""
        if self._spin_executor is not None:
            with contextlib.suppress(Exception):
                self._spin_executor.shutdown(timeout_sec=1.0)
            self._spin_executor = None
        if self._spin_thread is not None:
            with contextlib.suppress(Exception):
                self._spin_thread.join(timeout=1.0)
            self._spin_thread = None
        if self.node is not None:
            with contextlib.suppress(Exception):
                self.node.destroy_node()
            self.node = None
        if self._initialized_rclpy:
            with contextlib.suppress(Exception):
                rclpy.shutdown()
            self._initialized_rclpy = False

    def __del__(self) -> None:
        """Clean up when the object is garbage collected."""
        self.cleanup()
