# Data Recorder

A ROS2-based data recording service built with FastAPI, designed for high-performance robotics data
collection, storage, and management.

## Overview

Data Recorder service captures ROS 2 topic data to MCAP format files. It provides a FastAPI REST interface for controlling recording sessions, subprocess-based ROS 2 bag recording, and thread-safe metadata persistence.

### Runtime Responsibilities

1. **Recording lifecycle**: Singleton `RecordService` manages start/stop of ROS 2 bag recording subprocesses with thread-safe state management.
2. **Subprocess isolation**: Spawns `ros2 bag record` as external process for ROS 2 context isolation and robust signal handling.
3. **Metadata persistence**: `RecordMetadataRepo` performs atomic JSON writes for episode metadata (`record_metadata.json`).
4. **Directory management**: Creates date-based episode directories (`YYYY/MM/DD/<UUID7>/mcap/`) for MCAP file storage.
5. **Health monitoring**: Exposes health endpoint and recording status via REST API.

### Architecture

- **FastAPI application** (`src/main.py`): Entry point with CORS middleware and lifespan management for graceful shutdown.
- **Handlers** (`src/handlers/record.py`): REST API endpoints for start/stop recording and status queries.
- **RecordService** (`src/services/record.py`): Singleton managing subprocess lifecycle, recording state, and metadata operations.
- **RecordMetadataRepo** (`src/repos/record_metadata.py`): Thread-safe CRUD operations for episode metadata files.

### Configuration

All configuration is loaded from `deployments/<station>/config_data_recorder.yml` (mounted to `/workspace/config_data_recorder.yml`). See [Deployment README](../../../deployments/README.md).

- `url`: FastAPI bind address (default `0.0.0.0:3002`).
- `output_path`: Base directory for MCAP recordings (default `/workspace/data/raw_episodes`).
- `ros_topics`: List of ROS 2 topics to record. An empty list records nothing.
