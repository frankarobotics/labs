# Data Collection Service

Collects robotic teleoperation and demonstration data by coordinating ROS 2 nodes for devices, the operator UI, and the downstream data-recorder/processing pipeline.

## Overview

The service exposes a FastAPI control plane that keeps human-operated teleop sessions, robot actuators, and observer sensors in sync. It owns the canonical episode metadata in JSON, loads task definitions from YAML configuration, proxies start/stop commands to the Data Recorder service, and keeps device health up to date for UI consumption.

### Runtime Responsibilities

1. **Lifecycle orchestration**: `RecordingStateMachine` manages the IDLE → RECORDING → REVIEWING flow, while `FrankaWorkflowStateMachine` manages the IDLE → READY → SYNCING → FOLLOWING teleoperation flow (plus an `AUTORECOVERY` state entered when a controller dies). Both guard transitions made through the REST API. Recording can only start while the workflow is in FOLLOWING, and an active recording is auto-stopped (moved to review) when the workflow leaves FOLLOWING.
2. **Episode management**: `EpisodeService` talks to the metadata repo and the Data Recorder HTTP API to create, stop, save, discard, and label episodes.
3. **Device health tracking**: `DeviceMonitor` mirrors the station configuration into the in-memory device store and continuously inspects ROS topics to mark devices ONLINE/OFFLINE/UNKNOWN.
4. **Operator and task APIs**: Task, device, teleop, operator, and camera handlers expose read endpoints for the web UI and other services. Tasks are loaded from YAML configuration files.
5. **Configuration fan-out**: Station- and project-level settings are loaded once at startup and injected into services via the `dependencies.py` wiring.

### Architecture

- **FastAPI application** (`src/main.py`): Creates the app with a lifespan hook that initializes rclpy, launches the `DeviceMonitor`, wires CORS, and mounts routers from `handlers/`.
- **State machines** (`src/state_machine/`): `RecordingStateMachine` manages episode recording lifecycle; `FrankaWorkflowStateMachine` (extending `BaseWorkflowStateMachine`) manages the teleoperation workflow, including an `AUTORECOVERY` state that mirrors controller-coordinator recovery. Both are backed by `python-statemachine` and log every transition. `RecordingAutoStopListener` (`recording_autostop.py`) bridges the two one-way: it listens to the workflow leaving FOLLOWING and stops any active recording off-thread, keeping the workflow non-blocking.
- **Device monitor daemon** (`src/services/device_monitor.py`): Background thread that mirrors configured teleop robots and observer devices into the DB, polls ROS topics, and reinitializes its node when contexts become invalid instead of crashing.
- **Service layer** (`src/services/`): `EpisodeService`, `TaskService`, `DeviceService`, and peers combine repositories, the state machine, and Data Recorder RPCs to implement business logic.
- **Repositories** (`src/repos/`): Typed adapters for HTTP clients such as `DataRecorderRepo`.
- **Handlers** (`src/handlers/`): FastAPI routers that expose health/auth endpoints along with episode, task, teleop, device, operator, camera, and system operations.

### Configuration

All configuration is loaded from `deployments/<station>/config_data_collection.yml` (mounted to `/workspace/config_data_collection.yml`). See [Deployment README](../../../deployments/README.md).

Device definitions come from the station YAML files, and episode listings are derived from the episode directories on disk at runtime.

**`data_collection` section** — service settings:

- `url`: Host/port FastAPI binds to (default `0.0.0.0:3001`).
- `device_status_poll_interval_sec`: Polling interval for the device monitor.

**`data_recorder` section** — client connection to the data-recorder service:

- `url`: Base URL of the data-recorder REST API (default `http://localhost:3002`).
- `request_timeout`: HTTP request timeout in seconds.

See [Deployment README](../../../deployments/README.md).
