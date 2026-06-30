from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import rclpy  # type: ignore
import rclpy.client  # type: ignore
import rclpy.subscription  # type: ignore
from loguru import logger
from std_msgs.msg import String  # type: ignore
from std_srvs.srv import Trigger  # type: ignore

from configs.station import StationConfig
from services.robot import BaseRobotService


class FrankaRobotService(BaseRobotService):
    """RobotService implementation for Franka robots.

    Manages ROS 2 communication with Franka FR3 controller coordinators:
    subscribes to their state topics, exposes service-call helpers, and
    publishes joint states for teleoperation and replay workflows.
    """

    def __init__(self, station_config: StationConfig) -> None:
        """Initialize the Franka robot service and set up ROS 2 controller coordinator resources."""
        self._controller_coordinator_clients: dict[str, dict[str, rclpy.client.Client]] = {}
        self._controller_coordinator_state_subscribers: dict[str, rclpy.subscription.Subscription] = {}
        self._controller_coordinator_state_callbacks: list[Callable[[str, str], None]] = []
        self.controller_coordinator_states: dict[str, str] = {}
        self._state_changed = threading.Condition()
        self._state_callback_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cc_state_cb")
        super().__init__(station_config)  # triggers _initialize_ros2()
        self._init_controller_coordinators()

    def _init_controller_coordinators(self) -> None:
        """Initialize service clients and state subscribers for the controller coordinators.

        One set of clients and one state subscriber per teleop robot with follower_device
        "franka_fr3" is created. The station config validation ensures unique
        (namespace, follower_device) pairs.
        """
        if self.node is None:
            logger.warning("ROS2 node not available, cannot initialize service clients")
            return

        for teleop_robot in self.station_config.embodiment.teleop_robots or []:
            if teleop_robot.config.follower_device == "franka_fr3":
                namespace = teleop_robot.config.namespace or ""
                prefix = f"/{namespace}" if namespace else ""

                self._controller_coordinator_clients[namespace] = {
                    "get_ready": self.node.create_client(Trigger, f"{prefix}/controller_coordinator/get_ready"),
                    "start_operating": self.node.create_client(
                        Trigger, f"{prefix}/controller_coordinator/start_operating"
                    ),
                    "stop": self.node.create_client(Trigger, f"{prefix}/controller_coordinator/stop"),
                    "start_autorecovery": self.node.create_client(
                        Trigger, f"{prefix}/controller_coordinator/start_autorecovery"
                    ),
                }

                self.controller_coordinator_states[namespace] = "UNKNOWN"
                qos = rclpy.qos.QoSProfile(
                    depth=1,
                    durability=rclpy.qos.DurabilityPolicy.TRANSIENT_LOCAL,
                )
                self._controller_coordinator_state_subscribers[namespace] = self.node.create_subscription(
                    String,
                    f"{prefix}/controller_coordinator/state",
                    lambda msg, ns=namespace: self._on_controller_coordinator_state(ns, msg),
                    qos,
                )

    def cleanup(self) -> None:
        """Shut down the state callback worker and delegate to the base cleanup."""
        try:
            self._state_callback_worker.shutdown(wait=False, cancel_futures=True)
        except Exception:
            logger.exception("Failed to shut down controller coordinator state callback worker")
        super().cleanup()

    def register_controller_coordinator_state_callback(self, cb: Callable[[str, str], None]) -> None:
        """Register a callback to be invoked when any controller coordinator state changes."""
        self._controller_coordinator_state_callbacks.append(cb)

    def _on_controller_coordinator_state(self, namespace: str, msg: String) -> None:
        """Notify listeners of a controller coordinator state change and update internal state.

        The user callbacks are dispatched onto a dedicated worker thread so that
        the ROS spin thread is not blocked.

        Args:
            namespace: The namespace identifying the controller coordinator.
            msg: The state message received from the topic.
        """
        if self.controller_coordinator_states.get(namespace) == msg.data:
            return
        new_state = msg.data
        logger.info(f"Controller coordinator {namespace!r} state changed to: {new_state}")
        self.controller_coordinator_states[namespace] = new_state
        with self._state_changed:
            self._state_changed.notify_all()
        callbacks = list(self._controller_coordinator_state_callbacks)

        def _invoke() -> None:
            for cb in callbacks:
                try:
                    cb(namespace, new_state)
                except Exception:
                    logger.exception(f"Controller coordinator state callback failed for {namespace!r}")

        self._state_callback_worker.submit(_invoke)

    def _get_mismatched_controller_coordinator_states(self, expected: set[str]) -> dict[str, str]:
        """Return a dict of controller coordinators whose current state does not match one of ``expected``.

        Returns an empty dict if all coordinators match.
        """
        return {
            namespace: state for namespace, state in self.controller_coordinator_states.items() if state not in expected
        }

    def wait_for_matching_controller_coordinator_states(self, expected: set[str], timeout: float = 3.0) -> None:
        """Block until all coordinators reach ``expected`` state or the timeout expires.

        Uses a ``threading.Condition`` notified by ``_on_controller_coordinator_state``
        so the calling thread wakes up immediately on state changes instead of
        polling.

        Args:
            expected: The set of valid coordinator states to wait for (e.g. ``{"READY"}``
                or ``{"SYNCING", "FOLLOWING"}``).
            timeout: The maximum time to wait for all coordinators to reach the expected state.

        Raises:
            RuntimeError: If not all coordinators reach ``expected`` within
                ``timeout`` seconds.
        """
        with self._state_changed:
            if self._state_changed.wait_for(
                lambda: not self._get_mismatched_controller_coordinator_states(expected),
                timeout=timeout,
            ):
                return
        pending = self._get_mismatched_controller_coordinator_states(expected)
        raise RuntimeError(f"Coordinator(s) did not reach {expected!r} within {timeout}s: {pending}")

    def _get_available_clients_for_action(self, action: str) -> list[rclpy.client.Client]:
        """Return clients that are available for ``action``, raising if any are not.

        Args:
            action: One of 'get_ready', 'start_operating', or 'stop'.

        Raises:
            RuntimeError: If one or more services are not available within the timeout.
        """
        unavailable: list[str] = []
        available_clients: list[rclpy.client.Client] = []
        for clients in self._controller_coordinator_clients.values():
            client = clients[action]
            if not client.wait_for_service(timeout_sec=5.0):
                unavailable.append(client.srv_name)
            else:
                available_clients.append(client)
        if unavailable:
            raise RuntimeError(f"Controller coordinator service(s) not available: {unavailable}")
        return available_clients

    def _check_trigger_results(self, futures: list[tuple[str, rclpy.Future]]) -> None:
        """Raise a RuntimeError if any service call timed out or returned a failure.

        Args:
            futures: List of (service_name, future) pairs to inspect.

        Raises:
            RuntimeError: If any future timed out or returned a failure response.
        """
        errors: list[str] = []
        for service_name, future in futures:
            if not future.done():
                errors.append(f"Service call to {service_name} timed out")
            else:
                result = future.result()
                if result.success:
                    logger.info(f"Successfully called {service_name}: {result.message}")
                else:
                    errors.append(f"Service {service_name} returned failure: {result.message}")
        if errors:
            raise RuntimeError(": ".join(errors))

    def trigger_controller_coordinator(self, action: str) -> None:
        """Trigger a controller coordinator state transition via ROS2 service call.

        Sends requests in parallel to all pre-initialized clients for the given action.

        Args:
            action: One of 'get_ready', 'start_operating', or 'stop'.
        """
        if self.node is None:
            raise RuntimeError("ROS2 node not available")

        num_coordinators = len(self._controller_coordinator_clients)
        logger.info(f"Triggering controller coordinator action {action!r} for {num_coordinators} coordinator(s)")

        available_clients = self._get_available_clients_for_action(action)

        # Timeout for service calls, should be longer than the controller coordinator's configured service timeout
        timeout_s = 7.0
        done_event = threading.Event()
        pending = [len(available_clients)]

        def _on_done(_f: rclpy.Future) -> None:
            pending[0] -= 1
            if pending[0] == 0:
                done_event.set()

        futures: list[tuple[str, rclpy.Future]] = []
        for client in available_clients:
            future = client.call_async(Trigger.Request())
            future.add_done_callback(_on_done)
            futures.append((client.srv_name, future))

        done_event.wait(timeout=timeout_s)
        self._check_trigger_results(futures)
