#!/usr/bin/env python3
"""Launch file for one or more ZED cameras from a single config file.

Reads config_zed_camera.yml from the path set by the ZED_CAMERA_CONFIG_FILE
environment variable (default: /workspace/config_zed_camera.yml).

Each entry under the top-level 'zed-cameras' list launches one camera node via
the zed_wrapper zed_camera.launch.py. The 'ros2_launch_args' sub-dict is passed
as launch arguments; all remaining keys are written to a temporary ROS 2 params
override file and passed via 'ros_params_override_path'.
"""

import os
import tempfile
from typing import Any

import yaml
from launch import LaunchContext, LaunchDescription
from launch.actions import IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def load_yaml(file_path: str) -> dict[str, Any]:
    """Load and parse a YAML file."""
    with open(file_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def generate_camera_nodes(context: LaunchContext) -> list[IncludeLaunchDescription]:
    """Generate camera launch actions from the config file."""
    config_file = os.getenv("ZED_CAMERA_CONFIG_FILE", "/workspace/config_zed_camera.yml")
    config = load_yaml(config_file)

    nodes = []
    for index, camera_cfg in enumerate(config.get("zed-cameras", [])):
        camera_cfg = dict(camera_cfg)  # noqa: PLW2901 — shallow copy, don't mutate parsed config
        ros2_launch_args: dict[str, Any] = camera_cfg.pop("ros2_launch_args")

        # Write remaining parameters to a temporary ROS 2 params override file.
        params_content = {"/**": {"ros__parameters": camera_cfg}}
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=f"_camera_{index}.yaml",
            delete=False,
            encoding="utf-8",
        ) as params_file:
            yaml.dump(params_content, params_file)
            params_file_name = params_file.name

        launch_args = {str(k): str(v) for k, v in ros2_launch_args.items()}
        launch_args["ros_params_override_path"] = params_file_name

        nodes.append(
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    PathJoinSubstitution([FindPackageShare("zed_wrapper"), "launch", "zed_camera.launch.py"])
                ),
                launch_arguments=launch_args.items(),
            )
        )

    return nodes


def generate_launch_description() -> LaunchDescription:
    """Generate launch description for all configured ZED cameras."""
    return LaunchDescription([OpaqueFunction(function=generate_camera_nodes)])
