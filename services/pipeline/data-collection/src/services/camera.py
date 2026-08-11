from __future__ import annotations

import asyncio
import threading

import cv2  # pyright: ignore[reportMissingImports]
from fastapi import WebSocket
from loguru import logger
from pipeline_configs.station import StationConfig
from rclpy.executors import MultiThreadedExecutor

from helpers.rclpy_guard import safe_init
from services.camera_node import CameraNode


def infer_ros_image_message_type(topic: str) -> str:
    """Infer the ROS image message type from a topic name."""
    return "compressed" if topic.endswith("/compressed") else "image"


class CameraService:
    """Service for handling camera node lifecycle and image streaming (refactored for simplicity)."""

    def __init__(self, station_config: StationConfig) -> None:
        """Initialize the camera service."""
        self.station_config: StationConfig = station_config
        self._node: CameraNode | None = None
        self._executor: MultiThreadedExecutor | None = None
        self._ros_thread: threading.Thread | None = None
        self._ros_running: bool = False

    def _spin_executor(self) -> None:
        self._ros_running = True
        try:
            if self._executor is not None:
                self._executor.spin()
        except Exception as e:
            logger.error(f"ROS2 executor error: {e}")
        finally:
            self._ros_running = False

    def start(self, name: str, topic: str) -> None:
        """Start the camera node and ROS2 executor."""
        # Ensure rclpy is initialized safely once per process
        safe_init()
        msg_type = infer_ros_image_message_type(topic)
        self._node = CameraNode(name=name, topic=topic, msg_type=msg_type)
        self._executor = MultiThreadedExecutor()
        self._executor.add_node(self._node)
        self._ros_thread = threading.Thread(target=self._spin_executor, daemon=True)
        self._ros_thread.start()

    def stop(self) -> None:
        """Stop the camera node and ROS2 executor."""
        if self._executor:
            try:
                self._executor.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down executor: {e}")
        self._executor = None
        if self._ros_thread and self._ros_thread.is_alive():
            try:
                self._ros_thread.join(timeout=2.0)
            except Exception as e:
                logger.error(f"Error joining ROS thread: {e}")
        self._ros_thread = None
        if self._node:
            try:
                self._node.destroy_node()  # type: ignore[no-untyped-call]
            except Exception as e:
                logger.error(f"Error destroying camera node: {e}")
        self._node = None
        # Note: We don't call rclpy.shutdown() here because other parts of the application
        # may still be using ROS2. The global shutdown is handled by the application lifespan.
        # safe_shutdown()
        self._ros_running = False

    async def stream(self, websocket: WebSocket) -> None:
        """Stream images from the camera node to the WebSocket."""
        while True:
            image = self._node.get_latest_image() if self._node is not None else None
            if image is not None:
                success, encoded_image = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if success:
                    await websocket.send_bytes(encoded_image.tobytes())
            await asyncio.sleep(0.05)
