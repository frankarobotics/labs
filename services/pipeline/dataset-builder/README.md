# Dataset Builder Service

Converts processed MCAP episodes into dataset artifacts ready for training robot learning models.

## Quick Start

```bash
# Run from the repo root:
task dataset-builder-convert-episode \
  INPUT_MCAP=/workspace/data/processed_episodes/<date>/<uuid>/mcap/mcap_0.mcap \
  DATASET_NAME=my-dataset
```

Override default Task variables or pass extra CLI flags:

```bash
task dataset-builder-convert-episode \
  INPUT_MCAP=... \
  DATASET_NAME=... \
  DEPLOYMENT_DIR=/workspace/deployments/my_station \
  CLI_ARGS="--fps 30"
```

### Without Task (uv / Docker)

```bash
# uv (local dev environment)
uv run src/main.py \
  --dataset-name <dataset-name> \
  --deployment-dir /workspace/deployments/example_station \
  single --input /workspace/data/processed_episodes/<date>/<uuid>/mcap/mcap_0.mcap

# Docker
docker run --rm \
  -v /path/to/data:/workspace/data \
  -v /path/to/deployments:/workspace/deployments \
  registry.localhost/labs/dataset-builder:latest \
  ./entrypoint.sh \
    --dataset-name <dataset-name> \
    --deployment-dir /workspace/deployments/example_station \
    single --input /workspace/data/processed_episodes/<date>/<uuid>/mcap/mcap_0.mcap
```

## Overview

`dataset-builder` is the pipeline service responsible for dataset export. It is intentionally
separate from `data-processor` so that dataset formats, metadata conventions, and packaging
logic can evolve independently of the raw episode processing daemon.

Supported target formats:

| Format    | Description                                                                                                              |
| --------- | ------------------------------------------------------------------------------------------------------------------------ |
| `lerobot` | LeRobot v2.1 dataset structure with Parquet observations and MP4 videos; includes GR00T-specific files and observations. |

The service is structured so additional formats can be plugged in behind the same CLI and
service interface — see `src/services/dataset_builder.py`.

### Topic manifest

When `--deployment-dir` (or explicit config flags) is provided, the builder loads a
`DatasetTopicManifest` from `config_station.yml` and `config_data_recorder.yml`. The manifest
classifies every topic as `image`, `state`, `action`, or `ignored`, enforces the ordering
defined in the station config, and filters out topics that were not actually recorded.

Without a manifest, the reader falls back to schema-name heuristics, which is not recommended
for production datasets.

## CLI Reference

```
usage: main.py [-h] [--verbose] [--format {lerobot}]
               --dataset-name DATASET_NAME [--output OUTPUT]
               [--fps FPS]
               [--deployment-dir DEPLOYMENT_DIR]
               [--station-config STATION_CONFIG]
               [--recorder-config RECORDER_CONFIG]
               [--modality-config MODALITY_CONFIG]
               {single} ...

subcommands:
  single    Convert a single MCAP file
    --input   Path to input .mcap file (required)
```

## Key flags

| Flag                | Default                                           | Description                                                                                  |
| ------------------- | ------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `--dataset-name`    | _(required)_                                      | Dataset name                                                                                 |
| `--output`          | `/workspace/data/datasets/lerobot/<dataset-name>` | Output directory (derived from `--dataset-name` when omitted)                                |
| `--format`          | `lerobot`                                         | Target dataset format                                                                        |
| `--fps`             | `20.0`                                            | Target frame rate for synchronization                                                        |
| `--deployment-dir`  | `/workspace/deployments/example_station`          | Resolves `config_station.yml`, `config_data_recorder.yml`, and `modality.json` automatically |
| `--station-config`  | `<deployment-dir>/config_station.yml`             | Override station config path                                                                 |
| `--recorder-config` | `<deployment-dir>/config_data_recorder.yml`       | Override recorder config path                                                                |
| `--modality-config` | `<deployment-dir>/modality.json`                  | Override modality.json path                                                                  |

## Task reference

| Task                              | Description                                                                              |
| --------------------------------- | ---------------------------------------------------------------------------------------- |
| `dataset-builder-convert-episode` | **Primary task** — convert one MCAP episode (set `INPUT_MCAP`, `DATASET_NAME`)           |
| `dataset-builder-run`             | Run any command inside the container, defaults to an interactive shell (`CMD=/bin/bash`) |
| `build SERVICE=dataset-builder`   | Build the Docker image                                                                   |

## Notes

- The service expects MCAP input that already contains `foxglove.CompressedVideo` messages
  (i.e. output from `data-processor`, not raw `data-recorder` output).
- `lerobot` is installed inside the container image so its dependencies are not required on
  the host for local development.
- Set `DATA_ROOT` (default `../../../data`) and `DEPLOYMENTS_ROOT`
  (default `../../../deployments`) environment variables to point the Docker volume mounts
  at a non-default location.
