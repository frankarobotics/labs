# Bridges Float32 gripper width commands to robotiq_gripper_controller ParallelGripperCommand goals.
# Derived from franka_gripper_manager (https://github.com/wuphilipp/gello_software, BSD-3-Clause).

import rclpy
from rclpy.node import Node
from control_msgs.action import ParallelGripperCommand
from rclpy.action import ActionClient
from std_msgs.msg import Float32

DEFAULT_GRIPPER_COMMAND_TOPIC = "gripper_client/target_gripper_width_percent"
DEFAULT_MOVE_ACTION_TOPIC = "robotiq_gripper_controller/gripper_cmd"

KNUCKLE_JOINT_NAME = "robotiq_85_left_knuckle_joint"
# URDF limit of the knuckle joint: 0.0 rad = open, 0.8 rad = closed.
KNUCKLE_JOINT_MAX_POSITION = 0.8
# Full-scale force of the 2F-85 (gripper_max_force hardware parameter).
# 235 N is the 2F-85 full-scale force (100% max_effort).
GRIPPER_MAX_FORCE_N = 235.0


class RobotiqGripperClient(Node):
    def __init__(self):
        super().__init__("robotiq_gripper_client")
        self.get_logger().info("Starting Robotiq Gripper Client")
        self.gripper_state_sub = self.create_subscription(
            Float32,
            DEFAULT_GRIPPER_COMMAND_TOPIC,
            self.gripper_state_callback,
            10,
        )
        self.action_client = ActionClient(self, ParallelGripperCommand, DEFAULT_MOVE_ACTION_TOPIC)
        self.action_client.wait_for_server()
        self.last_width = -1.0
        self.get_logger().info("Gripper action server is up and running")

    def gripper_state_callback(self, msg):
        gripper_target_position = msg.data
        if abs(gripper_target_position - self.last_width) < 0.02:
            return
        self.send_gripper_command(gripper_target_position)

    def send_gripper_command(self, gripper_position):
        self.last_width = gripper_position
        # Convert the 0-1 open fraction to the knuckle joint angle in rad and
        # clamp to the URDF joint limits so the controller accepts the goal.
        position = min(max(1 - gripper_position, 0.0), KNUCKLE_JOINT_MAX_POSITION)
        goal_msg = ParallelGripperCommand.Goal()
        goal_msg.command.name = [KNUCKLE_JOINT_NAME]
        goal_msg.command.position = [position]
        goal_msg.command.effort = [GRIPPER_MAX_FORCE_N]
        self.future = self.action_client.send_goal_async(goal_msg)
        self.future.add_done_callback(self.gripper_response_callback)

    def gripper_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            raise RuntimeError(f"Goal rejected with status: {goal_handle.status}")

        self._get_result_future = goal_handle.get_result_async()
        self._get_result_future.add_done_callback(self.get_result_callback)

    def get_result_callback(self, future):
        result = future.result().result
        self.get_logger().info("Result: {0}".format(result))


def main(args=None):
    rclpy.init(args=args)
    gripper_client = RobotiqGripperClient()
    rclpy.spin(gripper_client)
    rclpy.shutdown()


if __name__ == "__main__":
    main()
