# Robotiq Gripper

A ROS 2-based gripper control service for Robotiq grippers using serial communication, providing real-time gripper
control and state feedback for robotic manipulation tasks.

## Overview

Robotiq Gripper service provides ROS 2 integration for Robotiq grippers via RS-485 serial communication. It publishes
gripper state and subscribes to gripper commands, enabling precise gripper control and coordination with Franka robots.

### Runtime Responsibilities

1. **Serial communication**: Manages RS-485 serial connection to Robotiq gripper via USB FTDI converter with real-time
   command execution.
2. **Gripper control**: Subscribes to gripper position commands and executes precise gripper movements with configurable
   speed and force.
3. **State publishing**: Publishes real-time gripper state (position, force, status) via ROS 2 for monitoring and
   feedback control.
4. **Device management**: Handles USB device access and serial communication with privileged container permissions.
5. **Namespace isolation**: Supports multiple gripper instances with unique namespaces for multi-robot setups (e.g.,
   left/right arms).

### Architecture

- **Official Robotiq ROS 2 driver** (`src/third_party/robotiq_ros/`): Git submodule of the officially supported
  [robotiq/ros](https://github.com/robotiq/ros) repository (ROS 2 Jazzy), providing `robotiq_driver` (ros2_control
  hardware interface over the in-tree gripper SDK), `robotiq_controllers` and `robotiq_description`. Only the gripper
  packages are built; the TSF-85 force sensitive fingertip package (`robotiq_tsf`) is intentionally excluded for now.
  The submodule nests the gripper SDK under `extern/grippers`, so clone/update with
  `git submodule update --init --recursive`.
- **Gripper bringup** (`src/robotiq_gripper_bringup/`): LABS-owned ROS 2 package with multi-gripper launch files,
  controller configuration, URDF wrapper, and a Float32-to-ParallelGripperCommand client bridge.
- **Gripper Controller Client**: ROS 2 launch file for Robotiq gripper control with YAML-based device parameters.
- **Serial Interface**: RS-485 serial communication with device-by-id persistent naming (USB-TO-RS-485).
- **Command Subscriber**: Subscribes to gripper position commands (typically from teleoperation or trajectory
  execution).
- **State Publisher**: Publishes gripper state feedback including position, force, and error status.

### Configuration

All configuration is loaded from a YAML file mounted to `/workspace/config_robotiq_gripper.yml`. See
[Deployment README](../../../deployments/README.md).

For a single gripper, use a flat YAML. For multiple grippers (e.g. left/right), use top-level keys:

```yaml
LEFT:
  com_port: '/dev/serial/by-id/usb-FTDI_USB_TO_RS-485_DA64HORK-if00-port0'
  namespace: 'gripper/left'
RIGHT:
  com_port: '/dev/serial/by-id/usb-FTDI_USB_TO_RS-485_DAWYTVR5-if00-port0'
  namespace: 'gripper/right'
```

- `com_port`: USB serial device path. Find available devices: `ls /dev/serial/by-id/`
- `namespace`: ROS 2 namespace for topic isolation.
- `FAKE_HARDWARE` (env var): Enable fake hardware mode (`use_fake_hardware` ros2_control mock) for bringup testing
  without a physical device (default `false`). Known limitation (inherited from the upstream driver): the mock hardware
  exports no effort/velocity command interfaces, so the `gripper_cmd` action controller cannot drive the gripper in
  this mode.
