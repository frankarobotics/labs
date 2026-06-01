# ZED Camera

A ROS 2-based stereo camera service built with GPU acceleration, designed for high-performance
computer vision and SLAM applications using Stereolabs ZED cameras.

## Overview

ZED Camera service publishes stereo RGB, depth, point cloud, and positional tracking data from Stereolabs ZED stereo cameras using the official zed-ros2-wrapper with CUDA-accelerated processing. It provides real-time visual-inertial odometry and high-bandwidth stereo data streams for robotics applications.

### Runtime Responsibilities

1. **Camera initialization**: Launches ZED ROS 2 wrapper nodes with camera model selection and GPU-accelerated initialization.
2. **Multi-stream publishing**: Publishes stereo RGB, depth, point cloud, IMU, and odometry topics via ROS 2 with CUDA-accelerated processing.
3. **GPU acceleration**: Manages NVIDIA CUDA runtime access for real-time computer vision processing with memory-optimized pipelines.
4. **SLAM pipeline**: Provides visual-inertial odometry with positional tracking and scene mapping capabilities.
5. **Hardware access**: Manages privileged USB device access and nvidia-container-runtime for GPU passthrough with DDS tuning for high-bandwidth data.

### Architecture

- **ZED ROS 2 Wrapper** (`src/third_party/zed-ros2-wrapper/`): Official third-party ROS 2 integration from Stereolabs providing camera lifecycle nodes with CUDA acceleration.
- **Camera Launch Node**: ROS 2 launch file with configurable parameters for camera model selection and feature toggles.
- **SLAM Module**: Visual-inertial odometry engine with positional tracking and scene reconstruction.
- **GPU Pipeline**: CUDA-accelerated depth estimation, point cloud generation, and image processing.
- **DDS Configuration**: CycloneDDS tuning for large stereo image and point cloud message transport with network buffer optimization.

### Configuration

All configuration is loaded from a YAML file mounted to `/workspace/config_zed_camera.yml`. See [Deployment README](../../../deployments/README.md).

The config uses a list under `zed-cameras`, with one entry per camera. Each entry has a `ros2_launch_args` sub-dict (passed as launch arguments to `zed_camera.launch.py`) and remaining keys written to a ROS 2 params override file:

```yaml
zed-cameras:
  - ros2_launch_args:
      camera_name: head_camera
      serial_number: '18646855'
      camera_model: zedm   # zed | zedm | zed2 | zed2i | zedx | zedxm | ...
    general:
      grab_resolution: HD720
      pub_frame_rate: 30.0
    depth:
      depth_mode: NONE
    video:
      brightness: 4
      ...
```

The `ZED_CAMERA_CONFIG_FILE` environment variable overrides the default config path.

## Prerequisites

NVIDIA Container Toolkit is required for GPU access. Check if installed:

```bash
dpkg -l | grep nvidia-container-toolkit
```

If not installed:

```bash
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

See [Troubleshooting](#troubleshooting) if the package cannot be located.

### Visualization

To verify camera streams in real-time:

```bash
# Example topics: /zed/zed_node/left/image_rect_color, /zed/zed_node/depth/depth_registered
python src/helpers/visualize_ros_camera_topic.py --topic /zed/zed_node/left/image_rect_color
```

## Troubleshooting

### NVIDIA Container Toolkit package not found

If `apt-get` cannot locate the nvidia-container-toolkit package, add the NVIDIA repository following [their installation guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html#setting-up-nvidia-container-toolkit):

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
&& curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update

export NVIDIA_CONTAINER_TOOLKIT_VERSION=1.17.8-1
sudo apt-get install -y \
    nvidia-container-toolkit=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
    nvidia-container-toolkit-base=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
    libnvidia-container-tools=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
    libnvidia-container1=${NVIDIA_CONTAINER_TOOLKIT_VERSION}
```

Configure NVIDIA runtime by creating `/etc/docker/daemon.json`:

```json
{
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "runtimeArgs": []
    }
  },
  "default-runtime": "nvidia"
}
```

Restart Docker after configuration:

```bash
sudo systemctl restart docker
```

### ZED_Explorer cannot connect to camera

**Issue:** When launching the ROS 2 node for the ZED camera (e.g., in `entrypoint.sh`), `ZED_Explorer` cannot connect to the camera at the same time and will be stuck in `Waiting for camera...`

**Solution:** In `entrypoint.sh`, comment out `sleep infinity` (so `ros2 launch` is not triggered), then exec into the container (`task exec-zed-camera-<instance>`) and run the binary `ZED_Explorer`.
