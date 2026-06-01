from threading import Lock

import cv2
import numpy as np
from cv_bridge import CvBridge  # type: ignore
from loguru import logger
from rclpy.node import Node
from rclpy.subscription import Subscription
from rclpy.timer import Timer
from sensor_msgs.msg import CompressedImage, Image  # type: ignore

from configs.station import Noop


class CameraNode(Node):
    """ROS2 node for handling camera topic subscription and image processing.

    This node can subscribe to either sensor_msgs/Image or sensor_msgs/CompressedImage topics,
    decode them to OpenCV images, and apply optional transformations.
    """

    def __init__(
        self,
        name: str,
        topic: str,
        transformations: list[Noop] | None = None,
        msg_type: str = "compressed",
    ) -> None:
        """Initialize the observer device camera node.

        Args:
            name (str): Name of the ROS2 node.
            topic (str): Topic to subscribe to.
            transformations (list[Noop] | None, optional): List of transformations to apply. Defaults to None.
            msg_type (str, optional): 'image' for sensor_msgs/Image, 'compressed' for
                sensor_msgs/CompressedImage (default: 'compressed').
        """
        super().__init__(name)
        self.topic: str = topic
        self._cv_bridge = CvBridge()
        self._latest_image: np.ndarray | None = None  # type: ignore[type-arg]
        self._image_lock = Lock()
        self.transformations: list[Noop] = transformations or []
        self.msg_type: str = msg_type
        if msg_type == "image":
            self._subscription: Subscription = self.create_subscription(Image, self.topic, self.listener_callback, 10)
        else:
            self._subscription = self.create_subscription(CompressedImage, self.topic, self.listener_callback, 10)
        self._frame_count = 0
        self._summary_timer: Timer = self.create_timer(10.0, self._log_summary_stats)
        logger.info(f"[CameraNode] name={self.get_name()}, subscribed_to={self.topic}, msg_type={self.msg_type}")

    def listener_callback(self, msg: Image | CompressedImage) -> None:
        """Callback for receiving camera images (Image or CompressedImage).

        Args:
            msg (Image or CompressedImage): Incoming ROS image message.
        """
        if self.transformations:
            image = self._apply_transformations(msg, self.transformations)
        else:
            image = self._convert_image(msg)
        with self._image_lock:
            self._latest_image = image
            self._frame_count += 1

    def _log_summary_stats(self) -> None:
        """Log summary statistics about received images periodically."""
        with self._image_lock:
            count: int = self._frame_count
            shape = self._latest_image.shape if self._latest_image is not None else None
            self._frame_count = 0  # reset for next period
        logger.debug(
            f"[CameraNode] name={self.get_name()}, topic={self.topic}, msg_type={self.msg_type}, "
            f"frames_received_last_10s={count}, last_image_shape={shape}"
        )

    def _convert_image(self, msg: Image | CompressedImage) -> np.ndarray | None:  # type: ignore[type-arg]
        """Convert a ROS image message to an OpenCV image.

        Args:
            msg (Image or CompressedImage): The ROS image message to convert.

        Returns:
            np.ndarray | None: The decoded OpenCV image, or None if conversion fails.
        """
        try:
            if self.msg_type == "image":
                return self._cv_bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")  # type: ignore
            if self.msg_type == "compressed":
                # CompressedImage: decode JPEG/PNG
                np_arr = np.frombuffer(msg.data, np.uint8)
                image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                if image is None:
                    raise ValueError("Failed to decode compressed image data")
                return image
            logger.error(f"[CameraNode] Unsupported message type: {self.msg_type}")
            raise ValueError(f"Unsupported message type: {self.msg_type}")
        except Exception as e:
            logger.error(f"[CameraNode] Error converting camera image: {e}")
            return None

    def _apply_transformations(self, msg: Image | CompressedImage, transformations: list[Noop]) -> np.ndarray | None:  # type: ignore[type-arg]
        """Apply a list of transformations to the image.

        Args:
            msg (Image or CompressedImage): The ROS image message to transform.
            transformations (list[Noop]): List of transformation objects.

        Returns:
            np.ndarray | None: The transformed OpenCV image, or None if conversion fails.
        """
        image = self._convert_image(msg)
        for idx, transformation in enumerate(transformations):
            logger.info(
                f"[CameraNode] name={self.get_name()}, transformation_idx={idx}, "
                f"type={getattr(transformation, 'type', None)}, "
                f"transformation={transformation}, input_type={self.msg_type}"
            )
            # Placeholder for transformation logic
        return image

    def get_latest_image(self) -> np.ndarray | None:  # type: ignore[type-arg]
        """Get the latest image from the camera.

        Returns:
            np.ndarray | None: The latest OpenCV image, or None if no image has been received yet.
        """
        with self._image_lock:
            return self._latest_image.copy() if self._latest_image is not None else None
