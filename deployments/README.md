# Deployments

Station-specific configurations for running the LABS stack in different physical environments.

## Overview

Each deployment represents a complete station configuration with its own hardware layout, device mappings, and environment-specific settings. Deployments allow you to run the same LABS services across multiple robot stations with different hardware setups without modifying service code.

## Deployment Structure

Each deployment folder contains:

### Pipeline

| File                         | Description                                                           |
| ---------------------------- | --------------------------------------------------------------------- |
| `config_station.yml`         | Station ID and dual-arm teleoperation mapping                         |
| `config_tasks.yml`           | Task definitions available for data collection episodes               |
| `config_data_collection.yml` | data-collection service settings and data-recorder client connection, see also [Data Collection README](../services/pipeline/data-collection/README.md). |
| `config_data_recorder.yml`   | data-recorder service settings and ROS 2 topics to record, see also [Data Recorder README](../services/pipeline/data-recorder/README.md). |
| `config_data_processor.yml`  | data-processor service settings and data-collection client connection, see also [Data Processor README](../services/pipeline/data-processor/README.md). |

### Hardware

| File                                | Description                                                          |
| ----------------------------------- | -------------------------------------------------------------------- |
| `config_franka_robot.yml`           | Franka FR3 robot IPs and ROS namespaces (left/right)|
| `config_gello.yml`                  | GELLO serial ports (left/right), see also [Franka GELLO README](../services/input/franka-gello/README.md). |
| `config_robotiq_gripper.yml`        | Robotiq gripper serial ports (left/right), see also [Robotiq Gripper README](../services/actuators/robotiq-gripper/README.md). |
| `config_realsense_camera.yml`       | RealSense camera serial numbers and ROS namespaces (left/right), see also [RealSense Camera README](../services/sensors/realsense-camera/README.md). |
| `config_zed_camera.yml`             | ZED camera serial number and resolution settings, see also [ZED Camera README](../services/sensors/zed-camera/README.md). |
| `config_controller_coordinator.yml` | Controller coordinator settings for robot controller lifecycle, see also [Controller Coordinator README](../services/actuators/controller-coordinator/src/controller_coordinator/README.md). |

### Orchestration

| File                | Description                                                        |
| ------------------- | ------------------------------------------------------------------ |
| `.env.example`      | Template for environment variables (rename to `.env` to customize `DATA_ROOT` path) |
| `cyclonedds.xml`    | CycloneDDS configuration for ROS 2 communication                  |
| `docker-compose.yml`| Compose services and volume mounts for the deployment             |
| `Taskfile.yml`      | Station-specific helper tasks for build/start/stop flows          |
| `Tiltfile`          | Tilt live-reload workflow                                         |

## Services

The following services are available for deployment. Core services are always required; hardware services are optional based on your setup.

| Service                  | Required | Notes                                                            |
| ------------------------ | -------- | ---------------------------------------------------------------- |
| `data-collection`        | ✅       | Core orchestrator — always required                              |
| `data-recorder`          | ✅       | ROS 2 topic recording — always required                          |
| `data-collection-ui`     | ✅       | Web UI — always required                                         |
| `data-processor`         | ✅       | Post-processing and video encoding — always required             |
| `franka-robot`           | ⚙️       | Required if using Franka FR3 arms                                |
| `controller-coordinator` | ⚙️       | Required if using Franka robots (manages ros2_control lifecycle) |
| `robotiq-gripper`        | ⚙️       | Required if using Robotiq grippers                               |
| `franka-gello`           | ⚙️       | Required if using GELLO as teleoperation device                  |
| `realsense-camera-wrist` | ⚙️       | Required if using Intel RealSense cameras                        |
| `zed-camera-head`        | ⚙️       | Required if using a ZED stereo camera; needs NVIDIA GPU          |

## Available Deployments

### example_station

Reference implementation demonstrating a dual-arm Franka bimanual setup with multiple cameras and teleoperation modalities, specifically tailored to the Franka Vision and Manipulation Kit.

#### Hardware Configuration

This station (`station_id: example_station`) includes:

**Actuators:**

- 1x Franka FR3 Duo (2x Franka FR3 arms as left/right)
- 2x Robotiq 2F-85 grippers (left/right)

**Input / Teleoperation Devices:**

- 2x Franka GELLO devices (left/right) for kinesthetic teaching

**Sensors:**

- 1x ZED stereo camera (head-mounted, `head_camera`)
- 2x RealSense D405 cameras (wrist-mounted, `wrist_camera_left`, `wrist_camera_right`)

**Observer Topics:**

- Robot state: joint states, end-effector poses, and velocities for both arms

#### Quick Configuration Guide for Franka Vision & Manipulation Kit

If you are using the hardware of the Franka Vision & Manipulation Kit, you can quickly get started with the default settings with just having to modify the following files in the `example_station` folder:

- Update `robot_ip` in `config_franka_robot.yml` — the fixed IP of each Franka robot arm, typically configured in the robot's network settings.
- Update `com_port` in `config_robotiq_gripper.yml` — find available USB serial devices with `ls /dev/serial/by-id/` and copy the path of the FTDI USB-TO-RS-485 converter (see [Robotiq Gripper README](../services/actuators/robotiq-gripper/README.md#configuration)).
- If using GELLO as teleoperation device, update `com_port` in `config_gello.yml` — find available USB serial devices with `ls /dev/serial/by-id/` and copy the OpenRB-150 device ID (see [Franka GELLO README](../services/input/franka-gello/README.md#configuration)).
- Update `serial_number` in `config_realsense_camera.yml` — find the 12-digit number on the label of your RealSense camera(s) (see [RealSense Camera README](../services/sensors/realsense-camera/README.md#configuration)).

> **Hint:** Plug one devices at a time, that way you can easily differentiate between multiple devices of the same type (e.g. left & right).

> **Important:** Update device configs to match your hardware before starting services.

#### Next Steps

After updating the quick-start config files above:

1. **Review configuration notes** (see [Configuration Notes](#configuration-notes) below) to understand cross-service dependencies and task setup if needed.

2. **Make hardware operational** 
   - Make sure your Franka robot(s) are powered on, with brakes unlocked and FCI enabled.
   - Make sure all your other devices are powered on and connected. Please note that USB cameras may not be detected or only detected as USB-2-device. Try connecting the cables until devices are recognized as USB-3-device(s). `lsusb -t` is a useful command to verify correct recognition of USB devices.

3. **Test your deployment**
   ```bash
   cd deployments/example_station
   task build                  # Build service images
   task start                  # Start all services with Tilt
   ```

4. **Verify deployment health**
   - Tilt dashboard: http://localhost:10360/ (tracks live rebuild and container logs): Check if all services build and start correctly.
   - Data collection UI: http://localhost:4000/ (web interface for episodes and teleoperation): See if all configured devices show up with green indicator and if camera streams are visualized 
     > **Hint:** If there are no updates to the Web UI, try refreshing the website).
   - Swagger API docs: http://localhost:3001/docs (data-collection service API)

5. **Troubleshoot** if services fail to start
   - **Note:** A container showing a green indicator in the Tilt dashboard does not guarantee all services are healthy — errors can occur even with running containers.
   - Verify basic functionality in the Data Collection UI (http://localhost:4000/). If the UI fails to load or shows errors, inspect container logs:
     - Via Tilt dashboard: click on a service to view its live logs
     - Via task: `task logs SERVICE=<service_name>` (e.g., `task logs SERVICE=data-collection`)
     - Via Docker CLI: `docker logs <container_name>` or `docker compose logs -f <service_name>`
   - Check the main README or individual service READMEs for service-specific troubleshooting.

For detailed service-specific configuration options and advanced setup, please refer to the README files in the respective folders which are also linked in the `Deployment Structure` tables above.

Kindly note the below described [Configuration Notes](#configuration-notes) (e.g. how to configure your tasks). If you have completed the configuration for the deployment, you can jump back to the [main README](../README.md).

## Configuration Notes

### Topic Name Resolution in `config_station.yml`

Topics under `embodiment.teleop_robots` are **namespace-relative** — the `namespace` field is prepended at runtime to form the full ROS 2 path:

```yaml
- id: left_arm
  config:
    namespace: left
    leader_topic: leader/gello/joint_states  # → /left/leader/gello/joint_states
    follower_topic: gello/joint_states       # → /left/gello/joint_states
```

Topics starting with `/` are treated as absolute and used as-is.
Topics under `observer_devices` are always absolute.

### Cross-Service URL Dependencies

Some URLs appear in multiple config files and must be kept in sync:

| URL                              | Where to change                                                                                             |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| data-collection (`0.0.0.0:3001` and `localhost:3001`) | `config_data_collection.yml` -> `data_collection.url`<br>`config_data_processor.yml` -> `data_collection.url` |
| data-recorder (`0.0.0.0:3002` and `localhost:3002`)   | `config_data_recorder.yml` -> `url`<br>`config_data_collection.yml` -> `data_recorder.url`                    |

### Data Processor Storage Behavior

In `config_data_processor.yml`, `delete_raw_episode: false` keeps raw episode data after successful processing. This lets you convert the same raw data into different formats later at the cost of more storage. Set it to `true` to remove raw input data after conversion.

### Task Configuration

Tasks define the demonstrations that operators can select during data collection. The `config_tasks.yml` file contains a list of task definitions. Check out the configuration in `example_station` as exemplary reference.

**Task fields:**

- `id` (required): Unique UUID identifier — e.g. generate one with `uuidgen` (Linux/Mac) or `python3 -c "import uuid; print(uuid.uuid4())"`
- `name` (required): Display name shown in the UI
- `description` (optional): Detailed description of the task
- `version` (optional): Version string for tracking task revisions
- `language_instructions` (optional): Step-by-step instructions for language model context
- `metadata` (optional): Arbitrary key-value pairs for filtering or categorization

Tasks are loaded at service startup and exposed through the read-only API. Episodes reference tasks by their `id` field. To add or modify tasks, edit `config_tasks.yml` and restart the data-collection service.

## Creating a New Deployment & Customization

If you have multiple stations or your station varies from the default setup with the Franka Vision & Manipulation Kit, set up a new station deployment:

1. **Copy the example station** as a template:

   ```bash
   cp -r deployments/example_station deployments/my_station
   cd deployments/my_station
   ```

2. **Update `config_station.yml`**:
   - Set a unique `metadata.station_id` (e.g., `lab_1`, `production_station_a`)
   - Configure `embodiment.teleop_robots` to match your robot setup
   - Configure `embodiment.observer_devices` to match your cameras/sensors

3. **Update `config_data_recorder.yml`**:
   - List all ROS 2 topics you want to record from your devices
   - Ensure topic names match the namespaces in `config_station.yml`

4. **Update device-specific configs**:
   - Edit `config_franka_robot.yml`, `config_gello.yml`, etc. to match your hardware
   - Update serial ports, device IDs, namespaces, and calibration offsets in the YAML files
   - Remove configs for devices you don't have

5. **Update `docker-compose.yml`**:
   - Remove or comment out services for devices not in your station (see [Services](#services) table)
   - Update volume mounts if you add or rename config files

   > **Note:** All ROS 2 services require `network_mode: host` and `stop_signal: SIGINT` in `docker-compose.yml`. `network_mode: host` is a hard requirement for DDS-based ROS 2 service discovery (UDP multicast). `stop_signal: SIGINT` ensures ros2 launch performs a clean shutdown when containers are stopped.

6. **Test the deployment**:

   See the [main README](../README.md) for the full deployment workflow (`task build`, `task start`, available dashboards, etc.).

## See Also

- [Main README](../README.md) - Repository overview and installation
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Development guidelines
