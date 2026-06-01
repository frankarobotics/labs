"""Device monitor for tracking and managing device states.

The DeviceMonitor handles robust ROS-based device monitoring with automatic recovery from
ROS context invalidation. It accepts a `repo_factory: Callable[[Session], DeviceRepo]` and
the worker creates a DB session with `with SessionLocal() as db:` then calls
`repo = self._repo_factory(db)`.

Key Features:
 - Automatic ROS node context validation and recovery
 - Graceful handling of ROS shutdown scenarios
 - Robust error handling that prevents monitor loop crashes
 - Proper resource cleanup without interfering with other ROS components

Reasoning:
 - The repo factory decouples the monitor from concrete repo implementations and makes unit
   testing easier (tests can inject test/mocked repo factories).
 - The worker creates the SQLAlchemy `Session` (via `SessionLocal`) in-thread so the session
   lifecycle (commit/rollback/close) is owned by the worker thread. SQLAlchemy Sessions are
   not thread-safe; creating the session inside the worker avoids accidental cross-thread reuse.
 - The factory expects a `Session` argument so the worker and factory have distinct
   responsibilities: worker manages session lifecycle, factory produces a repo bound to that
   session.
 - ROS node context validation prevents "rcl node's context is invalid" errors during shutdown
   or when ROS components are restarted.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime

import rclpy
from fastapi import FastAPI
from loguru import logger
from rclpy.node import Node
from rclpy.topic_endpoint_info import TopicEndpointInfo
from sqlalchemy.orm import Session

from configs.data_collection import DataCollectionConfig
from configs.station import (
    ObserverDevice,
    RealSenseCameraConfig,
    RobotObserverConfig,
    StationConfig,
    TeleopRobot,
    TeleopRobotConfig,
    ZedCameraConfig,
)
from db import SessionLocal
from helpers.rclpy_guard import safe_init
from models.db import DeviceDB, DeviceStatusDB, DeviceTypeDB
from repos.devices import DeviceRepo


class DeviceMonitor:
    """Device monitor lifecycle and thread with robust ROS integration.

    Responsibilities:
    - Sync devices from `configs.station` into the DB on start
    - Periodically check ROS topics and update device status with automatic recovery
    - Handle ROS node context invalidation gracefully during shutdown scenarios
    - Provide start/stop methods for integration with FastAPI lifespan
    - Ensure thread-safe resource management without interfering with other ROS components
    """

    def __init__(
        self,
        config: DataCollectionConfig,
        station_config: StationConfig,
        repo_factory: Callable[[Session], DeviceRepo],
    ) -> None:
        """Create a DeviceMonitor.

        Args:
            config: Data collection config
            station_config: Station config
            repo_factory: Callable that accepts a SQLAlchemy Session and returns a DeviceRepo
        """
        self.config: DataCollectionConfig = config
        self.station_config: StationConfig = station_config
        self._repo_factory: Callable[[Session], DeviceRepo] = repo_factory
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._node: Node | None = None

    def _init_rclpy_node(self) -> Node:
        """Initialize ROS node with proper error handling.

        Only initializes rclpy if it's not already running to avoid double-init errors.
        Multiple services in the process may initialize/shutdown rclpy independently.

        Returns:
            Initialized ROS Node instance

        Raises:
            Exception: If ROS node initialization fails
        """
        try:
            # Ensure rclpy is initialized safely once per process
            safe_init()
            node = Node("device_monitor_node")
            logger.info("rclpy node initialized for device monitoring")
            return node
        except Exception as e:
            logger.exception("Failed to initialize rclpy for device monitoring: {}", e)
            raise

    def get_configured_topics(self, device: DeviceDB) -> list[str]:
        """Get the list of ROS topics for a given device based on its type and configuration.

        Args:
            device: Device database model containing type and configuration

        Returns:
            List of ROS topic names that should be monitored for this device

        Raises:
            NotImplementedError: If the device type is not supported
        """
        if device.type == DeviceTypeDB.TELEOP_ROBOT:
            return self._topics_for_teleop(TeleopRobotConfig.model_validate(device.config))
        if device.type == DeviceTypeDB.REALSENSE_CAMERA:
            return self._topics_for_realsense(RealSenseCameraConfig.model_validate(device.config))
        if device.type == DeviceTypeDB.ZED_CAMERA:
            return self._topics_for_zed(ZedCameraConfig.model_validate(device.config))
        if device.type == DeviceTypeDB.ROBOT_OBSERVER:
            return self._topics_for_robot_observer(RobotObserverConfig.model_validate(device.config))
        raise NotImplementedError(f"Unknown device type: {device.type}")

    def _topics_for_teleop(self, cfg: TeleopRobotConfig) -> list[str]:
        topics: list[str] = []
        # Check leader_topic first: it reflects whether the input device (e.g. GELLO) is
        # online and publishing. The follower_topic only has a publisher while teleop is
        # actively running (TeleopRobotNode), so it would always appear offline in IDLE state.
        if cfg.leader_topic:
            topics.append(cfg.resolve_topic(cfg.leader_topic))
        if cfg.follower_topic:
            topics.append(cfg.resolve_topic(cfg.follower_topic))
        if cfg.observer_topics:
            topics.extend(cfg.observer_topics)
        return topics

    def _topics_for_realsense(self, cfg: RealSenseCameraConfig) -> list[str]:
        topics: list[str] = []
        if cfg and cfg.rgb:
            topics.append(cfg.rgb.topic)
        return topics

    def _topics_for_zed(self, cfg: ZedCameraConfig) -> list[str]:
        topics: list[str] = []
        if cfg and cfg.rgb:
            topics.append(cfg.rgb.topic)
        if cfg and cfg.rgb_left:
            topics.append(cfg.rgb_left.topic)
        if cfg and cfg.rgb_right:
            topics.append(cfg.rgb_right.topic)
        return topics

    def _topics_for_robot_observer(self, cfg: RobotObserverConfig) -> list[str]:
        topics: list[str] = []
        if cfg:
            topics.extend(cfg.topics)
        return topics

    def update_device_status(self, repo: DeviceRepo, device: DeviceDB, now: datetime) -> None:
        """Update the status of a device based on ROS topic availability with robust error handling.

        This method checks if the device's configured ROS topics have active publishers,
        handling ROS context invalidation gracefully. If the ROS node context is invalid,
        the device is marked as offline rather than raising an exception.

        Args:
            repo: Device repository for database operations
            device: Device to check and update
            now: Current timestamp for updates

        Note:
            - Protects the monitor loop from crashes due to ROS context issues
            - Automatically marks devices offline when ROS connectivity is lost
        """
        if self._node is None:
            logger.error(f"Cannot update device status for {device.id} since rclpy node is None")
            return

        try:
            is_online: bool = False
            configured_topics: list[str] = self.get_configured_topics(device)
            if not configured_topics:
                logger.warning(f"No configured topics for device {device.id}")
                new_status = DeviceStatusDB.OFFLINE
            else:
                configured_topic: str = configured_topics[0]

                # Check if rclpy and node context are valid before making ROS calls
                if not rclpy.ok():  # type: ignore[attr-defined]
                    logger.debug("rclpy is not OK while updating device {}; marking offline", device.id)
                    new_status = DeviceStatusDB.OFFLINE
                elif self._node.context is None or not self._node.context.ok():
                    logger.debug("Node context is invalid for device {}; marking offline", device.id)
                    new_status = DeviceStatusDB.OFFLINE
                else:
                    try:
                        publishers: rclpy.List[TopicEndpointInfo] = self._node.get_publishers_info_by_topic(  # type: ignore[name-defined]
                            configured_topic
                        )
                        if len(publishers) > 0:
                            is_online = True
                        new_status = DeviceStatusDB.ONLINE if is_online else DeviceStatusDB.OFFLINE
                    except Exception as e_inner:
                        # Handle RCLError when rclpy/node context becomes invalid during shutdown.
                        # This is expected behavior and should not be treated as an error.
                        # Log at debug level to reduce noise in logs during normal operation.
                        logger.debug(
                            f"Ignoring rclpy error while checking publishers for device {device.id}: {e_inner}"
                        )
                        new_status = DeviceStatusDB.OFFLINE

            if device.status != new_status:
                logger.info(f"Device {device.id} status change {device.status} -> {new_status}")
                device.status = new_status
            if is_online:
                device.last_heartbeat = now
            device.updated_at = now
            repo.db.add(device)
        except Exception:
            # Protect the monitor loop from dying on unexpected errors that are not
            # related to ROS context issues. Log full exception with stack trace and
            # continue monitoring other devices. ROS-specific exceptions are handled
            # separately above to avoid reaching this catch block during normal shutdown.
            logger.exception("Unexpected error updating device status for {}", device.id)

    def _is_node_valid(self) -> bool:
        """Check if the ROS node and context are valid and can be used for ROS operations.

        Returns:
            True if the node exists and both rclpy and node context are valid,
            False otherwise
        """
        return (
            self._node is not None
            and rclpy.ok()  # type: ignore[attr-defined]
            and self._node.context is not None
            and self._node.context.ok()
        )

    def _ensure_valid_node(self) -> bool:
        """Ensure we have a valid ROS node, reinitializing if necessary.

        This method provides automatic recovery from ROS context invalidation by:
        1. Checking if the current node is valid
        2. Cleaning up the invalid node if needed
        3. Attempting to create a new node
        4. Validating the new node before returning

        Returns:
            True if we have a valid node after this call, False if we cannot create one

        Note:
            This method enables the monitor to continue operating even when ROS
            components are restarted or shut down elsewhere in the system.
        """
        if self._is_node_valid():
            return True

        # Try to clean up existing node if it exists
        if self._node is not None:
            try:
                self._node.destroy_node()  # type: ignore[no-untyped-call]
            except Exception as e:
                logger.debug(f"Error destroying invalid node: {e}")
            self._node = None

        # Try to reinitialize
        try:
            self._node = self._init_rclpy_node()
            return self._is_node_valid()
        except Exception as e:
            logger.error(f"Failed to reinitialize ROS node: {e}")
            return False

    def monitor_loop(self, repo: DeviceRepo, interval_sec: float) -> None:
        """Monitor the status of devices in a loop with automatic ROS node recovery.

        This is the main monitoring loop that:
        1. Ensures we have a valid ROS node before each monitoring cycle
        2. Updates device status based on ROS topic availability
        3. Marks all devices offline if ROS connectivity is lost
        4. Handles graceful shutdown when stop event is set

        Args:
            repo: Device repository for database operations
            interval_sec: Sleep interval between monitoring cycles

        Note:
            The loop uses short sleep intervals (0.25s) for responsive shutdown
            while maintaining the specified monitoring interval.
        """
        self._node = self._init_rclpy_node()
        try:
            while not self._stop_event.is_set():
                # Check if we need to reinitialize the node for robust ROS connectivity
                if not self._ensure_valid_node():
                    logger.warning("Cannot ensure valid ROS node; marking all devices offline")
                    devices: list[DeviceDB] = list(repo.get_all())
                    now: datetime = datetime.now(UTC)
                    for device in devices:
                        if device.status != DeviceStatusDB.OFFLINE:
                            logger.info(f"Device {device.id} status change {device.status} -> {DeviceStatusDB.OFFLINE}")
                            device.status = DeviceStatusDB.OFFLINE
                            device.updated_at = now
                            repo.db.add(device)
                else:
                    # Normal monitoring path when ROS node is healthy
                    devices = list(repo.get_all())
                    now = datetime.now(UTC)
                    for d in devices:
                        self.update_device_status(repo, d, now)

                repo.db.commit()

                # Sleep in short intervals so shutdown is responsive
                slept = 0.0
                while slept < interval_sec and not self._stop_event.is_set():
                    time.sleep(0.25)
                    slept += 0.25
        except Exception as e:
            logger.error("Device monitor loop error: {}", e)
        finally:
            try:
                if self._node is not None:
                    self._node.destroy_node()  # type: ignore[no-untyped-call]
                    self._node = None
                # Avoid calling rclpy.shutdown() here as other parts of the system might be using ROS.
                # Let the main application or other components handle global ROS shutdown.
                logger.info("Device monitor node cleanup completed")
            except Exception as e:
                logger.error("Error during node cleanup in device monitor: {}", e)

    def _sync_config_to_db(self, repo: DeviceRepo) -> None:
        """Synchronize station configuration devices to the database.

        This method reads the station configuration and ensures all configured
        devices (teleop robots and observer devices) are present in the database
        with UNKNOWN status initially.

        Args:
            repo: Device repository for database operations
        """
        teleop_robots: list[TeleopRobot] = self.station_config.embodiment.teleop_robots or []
        for teleop_robot in teleop_robots:
            repo.upsert(
                device_id=teleop_robot.id,
                device_type=teleop_robot.type,
                status=DeviceStatusDB.UNKNOWN,
                config=teleop_robot.config.model_dump(),
            )
            logger.debug("Upserted teleop robot {} into DB", teleop_robot.id)

        observer_devices: list[ObserverDevice] = self.station_config.embodiment.observer_devices or []
        for observer_device in observer_devices:
            repo.upsert(
                device_id=observer_device.id,
                device_type=observer_device.type,
                status=DeviceStatusDB.UNKNOWN,
                config=observer_device.config.model_dump(),
            )
            logger.debug("Upserted observer device {} into DB", observer_device.id)

    def start(self, app: FastAPI) -> None:
        """Start the device monitor in a background thread and attach to app.state.

        This method creates and starts a daemon thread that will:
        1. Initialize the database with configured devices
        2. Start the monitoring loop with ROS node recovery
        3. Store monitor references on app.state for external access

        Args:
            app: FastAPI application instance to store monitor state

        Note:
            The monitor thread is marked as daemon so it won't prevent
            application shutdown. Monitor references are stored on app.state
            so other parts of the application can inspect or control it.
        """
        if getattr(app.state, "device_monitor_instance", None) is not None:
            logger.debug("Device monitor already started on app.state")
            return

        def worker() -> None:
            logger.info("Device monitor thread starting up")
            with SessionLocal() as db:
                logger.debug(f"Loaded data collection config: {self.config}")
                logger.debug(f"Loaded station config: {self.station_config}")

                # Create a repo using the provided factory so callers can control repo/session lifecycle
                repo: DeviceRepo = self._repo_factory(db)

                logger.info("Clearing devices table")
                repo.delete_all()

                logger.info("Syncing station config to DB")
                self._sync_config_to_db(repo)

                logger.info("Starting monitor loop")
                self.monitor_loop(repo, self.config.device_status_poll_interval_sec)

        self._thread = threading.Thread(target=worker, name="device-monitor", daemon=True)
        app.state.device_monitor_instance = self
        app.state.device_monitor_thread = self._thread
        app.state.device_monitor_stop_event = self._stop_event
        self._thread.start()

    def stop(self, timeout_sec: float = 5.0) -> None:
        """Signal the monitor to stop and wait for thread completion.

        This method gracefully shuts down the monitor by:
        1. Setting the stop event to signal the monitoring loop
        2. Waiting for the thread to complete within the timeout
        3. Warning if the thread doesn't stop within the timeout

        Args:
            timeout_sec: Maximum time to wait for thread completion

        Note:
            The monitor thread should stop gracefully due to the responsive
            sleep intervals in the monitoring loop.
        """
        logger.info("Stopping device monitor thread")
        self._stop_event.set()
        if self._thread is None:
            logger.debug("No device monitor thread to join")
            return
        self._thread.join(timeout=timeout_sec)
        if self._thread.is_alive():
            logger.warning(f"Device monitor thread did not stop within {timeout_sec} seconds")
        else:
            logger.info("Device monitor thread stopped")
