import argparse

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge  # type: ignore
from rclpy.node import Node
from rclpy.subscription import Subscription
from sensor_msgs.msg import CompressedImage, Image  # type: ignore


class CameraViewer(Node):
    """A ROS2 node that subscribes to an image topic (raw or compressed) and displays camera frames using OpenCV."""

    def __init__(self, topic: str, msg_type: str = "Image") -> None:
        """Initialize the CameraViewer node.

        Args:
            topic (str): The ROS2 image topic to subscribe to.
            msg_type (str): The message type: 'Image' or 'CompressedImage'.
        """
        super().__init__("camera_viewer")
        self.bridge = CvBridge()
        self.frame = None
        self.msg_type = msg_type
        if msg_type == "CompressedImage":
            self.subscription: Subscription = self.create_subscription(
                CompressedImage, topic, self.compressed_callback, 10
            )
        else:
            self.subscription: Subscription = self.create_subscription(Image, topic, self.raw_callback, 10)

    def raw_callback(self, msg: Image) -> None:
        """Callback for raw Image messages."""
        try:
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
            self.frame = cv_image
        except Exception as e:
            self.get_logger().error(f"Could not convert image: {e}")

    def compressed_callback(self, msg: CompressedImage) -> None:
        """Callback for CompressedImage messages."""
        try:
            np_arr = np.frombuffer(msg.data, np.uint8)
            cv_image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            self.frame = cv_image
        except Exception as e:
            self.get_logger().error(f"Could not decode compressed image: {e}")


def main(args: list[str] | None = None) -> None:
    """Visualize a ROS2 camera topic using OpenCV.

    Args:
        args (list or None): Command-line arguments to parse. If None, uses sys.argv.
    """
    parser = argparse.ArgumentParser(description="Visualize ROS2 camera topic with OpenCV")
    parser.add_argument(
        "--topic",
        type=str,
        default="/camera/camera/color/image_rect_raw",
        help="ROS2 image topic to subscribe to",
    )
    parser.add_argument(
        "--msg-type",
        type=str,
        choices=["Image", "CompressedImage"],
        default="Image",
        help="Message type: 'Image' or 'CompressedImage'",
    )
    parsed_args: argparse.Namespace = parser.parse_args(args)

    rclpy.init(args=args)
    viewer: CameraViewer = CameraViewer(parsed_args.topic, parsed_args.msg_type)
    try:
        while rclpy.ok():
            rclpy.spin_once(viewer, timeout_sec=0.1)
            if viewer.frame is not None:
                cv2.imshow(parsed_args.topic, viewer.frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
        cv2.destroyAllWindows()
    finally:
        viewer.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
