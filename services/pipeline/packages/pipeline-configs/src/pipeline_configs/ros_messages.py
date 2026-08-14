"""ROS message type vocabulary shared by the pipeline config models."""

from __future__ import annotations

from enum import Enum


class ROSMessageType(Enum):
    """A message type in the ``<package>/<Type>`` short form the station and contract configs use."""

    TWIST_STAMPED = "geometry_msgs/TwistStamped"
    WRENCH_STAMPED = "geometry_msgs/WrenchStamped"
    JOINT_STATE = "sensor_msgs/JointState"
    FLOAT32 = "std_msgs/Float32"
