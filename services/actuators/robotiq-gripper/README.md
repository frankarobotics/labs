# Robotiq Gripper

A ROS 2-based gripper control service for Robotiq grippers using serial communication, providing real-time gripper
control and state feedback for robotic manipulation tasks.

## Overview

Robotiq Gripper service provides ROS 2 integration for Robotiq grippers via RS-485 serial communication. It publishes
gripper state and subscribes to gripper commands, enabling precise gripper control and coordination with Franka robots
through the GELLO software integration.

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

- **GELLO Software Integration** (`src/third_party/gello_software/`): Official third-party GELLO ROS 2 package providing
  gripper manager and controller client.
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
- `FAKE_HARDWARE` (env var): Enable fake hardware mode for testing without a physical device (default `false`).
