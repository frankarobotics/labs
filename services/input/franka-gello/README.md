# Franka GELLO

A ROS 2-based teleoperation interface service for Franka robots using GELLO hardware, enabling
intuitive robot control through physical demonstration and real-time joint mapping.

## Overview

Franka GELLO service provides teleoperation capabilities for Franka robots through GELLO hardware devices. It publishes real-time joint states and gripper commands via ROS 2, enabling intuitive robot programming through physical guidance and demonstration data collection.

### Runtime Responsibilities

1. **Serial communication**: Manages USB FTDI serial connection to GELLO hardware with real-time joint state reading.
2. **Joint state publishing**: Publishes calibrated joint positions with configurable offsets and signs for accurate mapping.
3. **Gripper control**: Manages gripper state publishing with configurable range and real-time gripper commands.
4. **Device management**: Handles USB device access and serial communication with privileged container permissions.
5. **Namespace isolation**: Supports multiple GELLO instances with unique namespaces for multi-robot teleoperation.

### Architecture

- **GELLO Software Integration** (`src/third_party/gello_software/`): Official third-party GELLO ROS 2 package providing joint state publisher and serial communication.
- **ROS 2 Launch Node**: Configurable launch file for GELLO state publisher with YAML-based device parameters.
- **Serial Interface**: USB FTDI serial communication with device-by-id persistent naming.
- **Joint Mapper**: Real-time joint state processing with calibrated offsets and sign corrections.
- **Gripper Publisher**: Gripper state and command publishing with configurable range mapping.

### Configuration

All configuration is loaded from a YAML file mounted to `/workspace/config_gello.yml`. See [Deployment README](../../../deployments//README.md).

For a single GELLO device, use a flat YAML. For multiple devices (e.g. left/right), use top-level keys:

```yaml
LEFT:
  namespace: '/left/'
  com_port: 'usb-ROBOTIS_OpenRB-150_6FFE4629503059384C2E3120FF061E06-if00'
  num_arm_joints: 7
  joint_signs: [1, -1, 1, -1, 1, 1, 1]
  gripper: true
  assembly_offsets: [0.000, 0.000, 3.142, 3.142, 3.142, 4.712, 0.000]
  gripper_range_rad: [2.00, 3.22]
RIGHT: ...
```

- `com_port`: USB serial device path (without `/dev/serial/by-id/` prefix). Find available devices: `ls /dev/serial/by-id/`
- `namespace`: ROS 2 namespace for topic isolation.
- `num_arm_joints`: Number of arm joints (default `7` for Franka).
- `joint_signs`: Sign correction per joint.
- `assembly_offsets`: Calibrated zero-position offsets in radians.
- `gripper_range_rad`: Gripper range `[min, max]` in radians.
- `dynamixel_torque_enable`: Per-joint torque enable (1 = on, 0 = off).
  > **Warning:** When using OpenRB-150, do not enable torque until an external 5V supply is connected to the power terminal with the jumper set to "VIN(DXL)". USB power for torque operation may damage your computer's USB port.
- `dynamixel_goal_position`: Target positions in radians when torque is enabled.
- `dynamixel_kp_p` / `dynamixel_kp_i` / `dynamixel_kp_d`: PID gains per joint.
