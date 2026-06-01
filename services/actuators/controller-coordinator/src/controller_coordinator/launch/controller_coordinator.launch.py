#  Copyright (c) 2026 Franka Robotics GmbH
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import os

import yaml
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def load_yaml(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    with open(file_path, "r") as file:
        return yaml.safe_load(file)


def generate_robot_nodes(context):
    config_file_name = LaunchConfiguration("config_file").perform(context)
    package_config_dir = FindPackageShare("controller_coordinator").perform(context)
    config_file = os.path.join(package_config_dir, "config", config_file_name)
    configs = load_yaml(config_file)
    nodes = []
    for item_name, config in configs.items():
        namespace = config["namespace"]

        coordinator_namespace = f"/{namespace}" if namespace else ""
        nodes.append(
            Node(
                package="controller_coordinator",
                executable="controller_coordinator_node",
                namespace=namespace,
                parameters=[
                    {
                        "ready_controller": config["ready_controller"],
                        "operating_controller": config["operating_controller"],
                        "controller_manager_namespace": f"{coordinator_namespace}/controller_manager",
                        "monitor_rate_hz": 10.0,
                        "service_timeout_ms": 5000,
                    }
                ],
                output="screen",
            )
        )
    return nodes


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "config_file",
                default_value="example_fr3_config.yaml",
                description="Name of the robot configuration file to load (relative to config/ in controller_coordinator)",
            ),
            OpaqueFunction(function=generate_robot_nodes),
        ]
    )
