# RealSense Camera

A ROS 2-based camera service providing RealSense depth camera integration for robotics data
collection and computer vision applications.

## Overview

RealSense Camera service publishes synchronized RGB, depth, infrared, and point cloud data streams from RealSense cameras (D400/D500 series) using the official RealSense ROS 2 wrapper. It provides multi-stream camera data with configurable profiles and real-time visualization tools.

### Runtime Responsibilities

1. **Camera initialization**: Launches RealSense ROS 2 nodes with serial number-based device selection and camera profile configuration.
2. **Multi-stream publishing**: Publishes RGB, depth, infrared, and point cloud topics via ROS 2 with configurable resolution and frame rates.
3. **Hardware access**: Manages privileged USB 3.0 device access for real-time camera streaming with DDS tuning for large message payloads.
4. **Namespace isolation**: Supports multiple camera instances with unique namespaces for multi-camera setups (e.g., wrist_camera_left, wrist_camera_right).
5. **Stream visualization**: Provides OpenCV-based topic viewer for real-time camera feed validation and debugging.

### Architecture

- **RealSense ROS Wrapper** (`src/third_party/realsense-ros/`): Official third-party ROS 2 integration package from RealSense providing camera lifecycle nodes.
- **Camera Launch Node**: ROS 2 launch file with configurable parameters for serial number, namespace, camera name, color profile, and depth enable settings.
- **Camera Visualizer** (`src/helpers/visualize_ros_camera_topic.py`): ROS 2 subscriber node with OpenCV integration for real-time image topic visualization.
- **DDS Configuration**: CycloneDDS tuning for large image message transport with optimized network buffer settings.

### Configuration

All configuration is loaded from a YAML file mounted to `/workspace/config_realsense_camera.yml`. See [Deployment README](../../../deployments/README.md).

Two formats are supported:

**Single camera** — flat YAML with camera settings at the top level:

```yaml
serial_number: '315122271154'
camera_name: D405
camera_namespace: wrist_camera_left
depth_module.color_profile: 640x480x30
enable_depth: true
```

Environment variables `SERIAL_NUMBER`, `CAMERA_NAME`, `CAMERA_NAMESPACE` override YAML values for per-instance configuration.

**Multi camera** — nested YAML with one top-level key per camera (e.g. `LEFT`, `RIGHT`):

```yaml
LEFT:
  serial_number: '315122271154'
  camera_name: D405
  camera_namespace: wrist_camera_left
  depth_module.color_profile: 640x480x30
  enable_depth: true
RIGHT: ...
```

All config keys are passed directly as launch arguments to `rs_launch.py`, so camera-model-specific parameters (e.g. `depth_module.color_profile` for D405, `rgb_camera.color_profile` for D455) can be set without modifying the launch file.

> **Note for D405:** The D405 has no separate RGB sensor. Its color image is produced by the depth module. Use `depth_module.color_profile` and `enable_depth: true`.

### Visualization

To visualize the camera feed in real-time:

```bash
python src/helpers/visualize_ros_camera_topic.py --topic /wrist_camera_left/D405/color/image_rect_raw
```
