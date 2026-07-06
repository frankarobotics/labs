# Data Processor Service

Converts raw MCAP episodes into compressed, Foxglove-compatible artifacts ready for long-term storage and downstream
consumption.

## Overview

The processor runs as a background daemon inside the data-collection stack. It periodically polls the data-collection
API for newly recorded episodes, validates the raw files on disk, converts image topics to AV1 video, re-packages the
MCAP with reversible metadata, and optionally deletes the raw payload after a successful conversion.

### Runtime Responsibilities

1. **Poll and filter episodes** using `DataCollectionRepo`, limited by `episode_limit_per_poll`, and gated by a health
   check.
2. **Resolve file locations** from the episode UUID7 timestamp and ensure `raw_data_path/YYYY/MM/DD/<episode>` contains
   `mcap/mcap_0.mcap`.
3. **Convert MCAP contents**: `MCAPReader` splits image and non-image topics, `VideoEncoder` encodes each camera stream
   (AV1 by default, with FFmpeg fallback codecs supported), `MetadataManager` builds reversibility metadata, and
   `MCAPWriter` reassembles the processed MCAP with Foxglove `CompressedVideo` schemas alongside the untouched non-image
   topics.
4. **Persist artifacts** by copying auxiliary YAML/JSON files, emitting `conversion_metadata.json`, creating a
   `.processing_complete` marker, and marking the episode as `SUCCESS` via the data-collection API.
5. **Cleanup** optionally removes the original episode directory when `delete_raw_episode: true`.

### Architecture

- **Main daemon** (`src/main.py`): Loads `DataProcessorConfig`, honors `enabled`, installs signal handlers, and drives
  the polling loop.
- **Orchestrator** (`src/services/data_processor.py`): Implements the end-to-end workflow, including filesystem layout,
  conversion orchestration, validation, and status patching.
- **MCAPReader** (`src/services/mcap_reader.py`): Discovers `sensor_msgs/msg/Image` topics, decodes ROS 2 messages, and
  separates image payloads from other topics while maintaining ordering.
- **VideoEncoder** (`src/services/video_encoder.py`): Feeds ordered frames to FFmpeg (SVT-AV1 by default) and emits
  encoded video bytes plus detailed encoding metadata; supports alternate codecs via configuration.
- **MCAPWriter** (`src/services/mcap_writer.py`): Writes the converted videos as Foxglove `CompressedVideo` messages,
  replays the untouched non-image data, and preserves original MCAP metadata blocks.
- **DataCollectionRepo** (`src/repos/data_collection.py`): Thin HTTP client for episode queries, status updates, and
  health checks against the data-collection service.
- **MetadataManager** (`src/services/metadata_manager.py`): Captures mapping data required for reversibility (frame
  timestamps, codec parameters, topic mapping, etc.).

### Configuration

All configuration is loaded from `deployments/<station>/config_data_processor.yml` (mounted to
`/workspace/config_data_processor.yml`). See [Deployment README](../../../deployments/README.md).

**`data_processor` section** — service settings:

- `enabled`: Toggle the daemon without tearing down the container.
- `poll_interval_seconds` / `episode_limit_per_poll`: Polling cadence and batch size.
- `raw_data_path` / `processed_data_path`: Input/output directories.
- `av1_preset`, `av1_gop_size`, `av1_pixel_format`, `av1_threads`: FFmpeg SVT-AV1 encoding settings.
- `delete_raw_episode`: Remove source data after successful conversion.

**`data_collection` section** — client connection to the data-collection service:

- `url`: Base URL of the data-collection REST API (default `http://localhost:3001`).
- `request_timeout`: HTTP request timeout in seconds.

See [Deployment README](../../../deployments/README.md).
