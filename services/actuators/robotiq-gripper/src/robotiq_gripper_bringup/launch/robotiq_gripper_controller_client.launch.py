# Multi-gripper launch orchestration from YAML config.
# Applies per-gripper namespaces and starts the Float32 command bridge.

import os
import yaml
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    GroupAction,
    IncludeLaunchDescription,
    OpaqueFunction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node, PushRosNamespace
from launch_ros.substitutions import FindPackageShare


def load_yaml(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    with open(file_path, "r") as file:
        return yaml.safe_load(file)


def resolve_com_port(com_port: str) -> str:
    """Resolve udev symlinks to the real tty node.

    libserialport 0.1.1 rejects paths under /dev/serial/by-id (and any
    symlink): it looks up /sys/class/tty/<basename>, which only exists for
    kernel names like ttyUSB0. Keep by-id in config for stable naming, but
    pass the resolved device path to the hardware interface.
    """
    resolved = os.path.realpath(com_port)
    if not os.path.exists(resolved):
        raise FileNotFoundError(
            f"com_port '{com_port}' resolves to '{resolved}', which does not exist"
        )
    return resolved


def generate_robot_nodes(context):
    config_file_name = LaunchConfiguration("config_file").perform(context)
    use_fake_hardware = LaunchConfiguration("use_fake_hardware").perform(context)
    bringup_share = FindPackageShare("robotiq_gripper_bringup").perform(context)
    config_file = os.path.join(bringup_share, "config", config_file_name)
    model = os.path.join(bringup_share, "urdf", "robotiq_2f_85_gripper.urdf.xacro")
    controllers = os.path.join(bringup_share, "config", "robotiq_controllers.yaml")
    configs = load_yaml(config_file)
    nodes = []
    for item_name, config in configs.items():
        namespace = config["namespace"]
        com_port = str(config["com_port"])
        if use_fake_hardware.lower() not in ("true", "1"):
            com_port = resolve_com_port(com_port)
        nodes.append(
            GroupAction(
                [
                    PushRosNamespace(namespace),
                    IncludeLaunchDescription(
                        PythonLaunchDescriptionSource(
                            PathJoinSubstitution(
                                [
                                    FindPackageShare("robotiq_gripper_bringup"),
                                    "launch",
                                    "robotiq_control.launch.py",
                                ]
                            )
                        ),
                        launch_arguments={
                            "com_port": com_port,
                            "use_fake_hardware": use_fake_hardware,
                            "model": model,
                            "controllers": controllers,
                        }.items(),
                    ),
                    Node(
                        package="robotiq_gripper_bringup",
                        executable="robotiq_gripper_client",
                        name="robotiq_gripper_client",
                        output="screen",
                    ),
                ]
            )
        )
    return nodes


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "config_file",
                default_value="example_fr3_config_robotiq.yaml",
                description="Path to the robot configuration file to load",
            ),
            DeclareLaunchArgument(
                "use_fake_hardware",
                default_value="false",
                description="Use ros2_control mock (fake) hardware instead of real grippers",
            ),
            OpaqueFunction(function=generate_robot_nodes),
        ]
    )
