#!/usr/bin/env python3
# NOTE: Do NOT use IncludeLaunchDescription(rs_launch.py) here.
# rs_launch.py inherits the parent's 'config_file' launch argument and passes
# the raw YAML (with LEFT/RIGHT keys) directly to realsense2_camera_node,
# which rejects unknown top-level keys. Use Node() with parameters=[...] instead.
"""Launch file for one or more RealSense cameras from a single config file.

Supports two config formats:
- Single camera: flat YAML with camera settings directly at the top level.
  Environment variables (SERIAL_NUMBER, CAMERA_NAME, CAMERA_NAMESPACE)
  take precedence for per-instance overrides.
- Multi camera: nested YAML where each top-level key defines one camera
  (e.g. LEFT, RIGHT, or any other grouping).

Config keys (including dotted keys like depth_module.color_profile) are passed
directly as ROS 2 node parameters.
"""

import os
from typing import Any

import yaml
from launch import LaunchContext, LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def load_yaml(file_path: str) -> dict[str, Any]:
    """Load and parse a YAML file."""
    with open(file_path) as f:
        return yaml.safe_load(f)


def is_multi_camera_config(config: dict[str, Any]) -> bool:
    """Check if the config represents a multi-camera setup."""
    if not config or not isinstance(config, dict):
        return False
    return any(isinstance(v, dict) and ("serial_number" in v or "camera_namespace" in v) for v in config.values())


def make_camera_node(config: dict[str, Any]) -> Node:
    """Create a ROS2 Node for a single RealSense camera from config."""
    camera_name = config.get("camera_name", "camera")
    camera_namespace = config.get("camera_namespace", "")
    serial_number = str(config.get("serial_number", ""))

    params: dict[str, Any] = {
        k: v for k, v in config.items() if k not in ("camera_name", "camera_namespace", "serial_number")
    }
    params["serial_no"] = serial_number

    return Node(
        package="realsense2_camera",
        executable="realsense2_camera_node",
        name=camera_name,
        namespace=camera_namespace,
        parameters=[params],
        output="screen",
    )


def generate_camera_nodes(context: LaunchContext) -> list[Node]:
    """Generate ROS2 nodes for all configured RealSense cameras."""
    config_file_name = LaunchConfiguration("config_file").perform(context)

    possible_paths = [
        config_file_name,
        os.path.join("/workspace", config_file_name),
        os.path.join(os.getcwd(), config_file_name),
    ]

    config_file = next((p for p in possible_paths if os.path.exists(p)), None)
    if not config_file:
        raise FileNotFoundError(f"Config file '{config_file_name}' not found. Tried: {possible_paths}")

    config = load_yaml(config_file) or {}

    if is_multi_camera_config(config):
        return [make_camera_node(dict(entry)) for entry in config.values()]

    # Single camera: environment variables take precedence over config file values.
    merged = dict(config)
    for env_key, field in {
        "SERIAL_NUMBER": "serial_number",
        "CAMERA_NAME": "camera_name",
        "CAMERA_NAMESPACE": "camera_namespace",
    }.items():
        if env_key in os.environ:
            merged[field] = os.environ[env_key]

    return [make_camera_node(merged)]


def generate_launch_description() -> LaunchDescription:
    """Generate the ROS2 launch description for the RealSense camera(s)."""
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "config_file",
                default_value="config_realsense_camera.yml",
                description="Path to the camera configuration YAML file",
            ),
            OpaqueFunction(function=generate_camera_nodes),
        ]
    )
