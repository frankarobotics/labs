from geometry_msgs.msg import TwistStamped  # type: ignore
from loguru import logger
from pipeline_configs.station import Identity, Noop, ROSMessageType
from rclpy.node import Node
from rclpy.publisher import Publisher
from rclpy.subscription import Subscription
from sensor_msgs.msg import JointState  # type: ignore
from std_msgs.msg import Float32  # type: ignore


class TeleopRobotNode(Node):
    """ROS2 node for handling teleop topic subscription, transforming, and actuator publishing."""

    def __init__(
        self,
        name: str,
        ros_message_type: ROSMessageType,
        leader_topic: str,
        follower_topic: str,
        transformations: list[Noop | Identity] | None = None,
    ) -> None:
        """Initialize the teleop component node."""
        super().__init__(name)
        self.transformations: list[Noop | Identity] | None = transformations
        self.ros_message_type: ROSMessageType = ros_message_type
        ros_msg_type: type[TwistStamped] | type[JointState] | type[Float32] = self._get_ros_message_type(
            ros_message_type
        )
        self.publisher: Publisher = self.create_publisher(ros_msg_type, follower_topic, 10)
        self.subscription: Subscription = self.create_subscription(
            ros_msg_type, leader_topic, self.listener_callback, 10
        )
        logger.info(
            f"node={self.get_name()}, ros_message_type={ros_message_type}, "
            f"subscribed_to={leader_topic}, publishing_to={follower_topic}"
        )

    def _get_ros_message_type(
        self, ros_message_type: ROSMessageType
    ) -> type[TwistStamped] | type[JointState] | type[Float32]:
        """Get the ROS2 message class for the message type."""
        logger.info(f"node={self.get_name()}, resolving ros_message_type={ros_message_type}")
        match ROSMessageType(ros_message_type):
            case ROSMessageType.TWIST_STAMPED:
                return TwistStamped  # type: ignore[no-any-return]
            case ROSMessageType.JOINT_STATE:
                return JointState  # type: ignore[no-any-return]
            case ROSMessageType.FLOAT32:
                return Float32  # type: ignore[no-any-return]
            case _:
                logger.error(f"Unsupported ros_message_type: {ros_message_type}")
                raise ValueError(f"Unsupported ros_message_type: {ros_message_type}")

    def listener_callback(
        self,
        msg: TwistStamped | JointState | Float32,
    ) -> None:
        """Callback for receiving teleop messages."""
        # logger.debug(
        #     f"node={self.get_name()}, topic={self.subscription.topic_name}, "
        #     f"received_type={type(msg).__name__}, msg={msg}"
        # )
        data: TwistStamped | JointState | Float32 = (
            self._apply_transformations(msg, self.transformations) if self.transformations else msg
        )
        # logger.debug(
        #     f"node={self.get_name()}, publishing_to={self.publisher.topic_name}, "
        #     f"data_type={type(data).__name__}, data={data}"
        # )
        self.publisher.publish(data)

    def _apply_transformations(
        self,
        data: TwistStamped | JointState | Float32,
        transformations: list[Noop | Identity],
    ) -> TwistStamped | JointState | Float32:
        """Apply transformations to the incoming teleop data."""
        # TwistStamped logic
        if isinstance(data, TwistStamped):
            # Placeholder for transformation logic
            return data

        # JointState logic
        if isinstance(data, JointState):
            # Placeholder for transformation logic
            return data

        # Float32 logic
        if isinstance(data, Float32):
            # Placeholder for transformation logic
            return data

        raise NotImplementedError(f"node={self.get_name()}, unsupported_message_type={type(data)}, data={data}")

    def cleanup(self) -> None:
        """Clean up publishers and subscriptions before destroying the node."""
        logger.info(f"node={self.get_name()}, starting cleanup")

        # Clean up publisher
        try:
            topic_name: str = self.publisher.topic_name
            logger.info(f"node={self.get_name()}, destroying publisher for topic: {topic_name}")
            self.destroy_publisher(self.publisher)
            logger.info(f"node={self.get_name()}, successfully destroyed publisher for topic: {topic_name}")
        except Exception as e:
            logger.error(f"node={self.get_name()}, error destroying publisher: {e}")

        # Clean up subscription
        try:
            topic_name = self.subscription.topic_name
            logger.info(f"node={self.get_name()}, destroying subscription for topic: {topic_name}")
            self.destroy_subscription(self.subscription)
            logger.info(f"node={self.get_name()}, successfully destroyed subscription for topic: {topic_name}")
        except Exception as e:
            logger.error(f"node={self.get_name()}, error destroying subscription: {e}")

        logger.info(f"node={self.get_name()}, cleanup completed")
