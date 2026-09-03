# Dataset Builder Service

Converts processed MCAP episodes into dataset artifacts ready for training robot learning models.

## Quick Start

```bash
# Build a dataset from all processed episodes:
task dataset-builder-create DATASET_NAME=my-dataset

# Filter by date range:
task dataset-builder-create DATASET_NAME=may-data FROM=2026-05-01 TO=2026-05-31

# Filter by task description and include failed episodes:
task dataset-builder-create DATASET_NAME=pick-red TASK_DESC="Pick red box" INCLUDE_FAILED=1

# Explicit single file:
task dataset-builder-create DATASET_NAME=test \
  INPUT_MCAP=/workspace/data/processed_episodes/2026/05/01/<uuid>/mcap/mcap_0.mcap

# Preview matched episodes without converting:
task dataset-builder-create DRY_RUN=1
```

Override default Task variables or pass extra CLI flags:

```bash
task dataset-builder-create \
  DATASET_NAME=my-dataset \
  DEPLOYMENT_DIR=/workspace/deployments/my_station \
  CLI_ARGS="--fps 30"
```

### Without Task (uv / Docker)

```bash
# uv — all episodes with filters
uv run src/main.py \
  --dataset-name my-dataset \
  --deployment-dir /workspace/deployments/fr3_duo_example \
  --from 2026-05-01 --to 2026-05-31

# uv — explicit file(s)
uv run src/main.py \
  --dataset-name my-dataset \
  --deployment-dir /workspace/deployments/fr3_duo_example \
  --input /workspace/data/processed_episodes/2026/05/01/<uuid>/mcap/mcap_0.mcap

# Docker
docker run --rm \
  -v /path/to/data:/workspace/data \
  -v /path/to/deployments:/workspace/deployments \
  registry.localhost/labs/dataset-builder:latest \
  ./entrypoint.sh \
    --dataset-name my-dataset \
    --deployment-dir /workspace/deployments/fr3_duo_example \
    --from 2026-05-01
```

## Overview

`dataset-builder` is the pipeline service responsible for dataset export. It is intentionally separate from
`data-processor` so that dataset formats, metadata conventions, and packaging logic can evolve independently of the raw
episode processing daemon.

Supported target formats:

| Format    | Description                                                                                                              |
| --------- | ------------------------------------------------------------------------------------------------------------------------ |
| `lerobot` | LeRobot v2.1 dataset structure with Parquet observations and MP4 videos; includes GR00T-specific files and observations. |

The service is structured so additional formats can be plugged in behind the same CLI and service interface — see
`src/services/dataset_builder.py`.

### Episode discovery

By default the builder scans `/workspace/data/processed_episodes/` which follows the
`YYYY/MM/DD/<uuid>/mcap/mcap_0.mcap` layout produced by `data-processor`. Filters narrow the selection:

| Filter             | How it works                                                                                                                        |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| `--from/to`        | Cheap path-only date comparison.                                                                                                    |
| `--include-failed` | Include episodes marked as failed (read from `episode_metadata.json` label). They are excluded without this flag.                   |
| `--episode-id`     | Match by UUID from the directory name.                                                                                              |
| `--exclude-id`     | Exclude specific UUIDs.                                                                                                             |
| `--task`           | Reads MCAP metadata section (fast, no message iteration) to match `episode_context.task_description` as case-insensitive substring. |
| `--limit`          | Cap the number of episodes after all other filters.                                                                                 |

Use `--dry-run` to preview the matched episodes without converting.

`--input` provides explicit MCAP path(s) and is **mutually exclusive** with discovery filters.

### Policy contract

A policy contract is the **required** input that defines what a dataset contains and `meta/modality.json` is generated
from this contract. Every contract member the builder consumes:

| Contract                     | Effect on the dataset                                                           |
| ---------------------------- | ------------------------------------------------------------------------------- |
| `policy.control_rate_hz`     | Resampling target (`--fps` overrides it)                                        |
| `policy.dtype`               | dtype of every state/action column and feature                                  |
| `cameras[].topic`            | Live image topic; the `.../compressed_video` stream to read is derived from it  |
| `cameras[].policy_key`       | `observation.images.<policy_key>` feature and video directory                   |
| `state[]` / `action[]` order | Concatenation order of `observation.state` and `action`                         |
| `state[].policy_key`         | `observation.state.<policy_key>` column, and its span in `meta/modality.json`   |
| `state[].field`              | Which JointState array is read (`position` / `velocity` / `effort`)             |
| `state[].element_names`      | Elements a segment contributes, reordered against the message's own `name` list |
| `annotations[]`              | `annotation.<policy_key>` columns in the Parquet and `meta/modality.json`       |

An episode that does not contain data for every declared segment is rejected.

## CLI Reference

```
usage: main.py [-h] [--verbose] [--format {lerobot}]
               --dataset-name DATASET_NAME [--output OUTPUT]
               [--fps FPS]
               [--deployment-dir DEPLOYMENT_DIR]
               [--policy-type POLICY_TYPE]
               [--policy-contract POLICY_CONTRACT]
               [--input INPUT]
               [--episodes-dir EPISODES_DIR]
               [--from YYYY-MM-DD] [--to YYYY-MM-DD]
               [--task TASK] [--episode-id UUID]
               [--exclude-id UUID] [--limit N]
               [--include-failed] [--dry-run]
```

## Key flags

| Flag                | Default                                              | Description                                                      |
| ------------------- | ---------------------------------------------------- | ---------------------------------------------------------------- |
| `--dataset-name`    | _(required)_                                         | Dataset name                                                     |
| `--output`          | `/workspace/data/datasets/lerobot/<dataset-name>`    | Output directory (derived from `--dataset-name` when omitted)    |
| `--format`          | `lerobot`                                            | Target dataset format                                            |
| `--fps`             | contract's `policy.control_rate_hz`                  | Override the resampling target                                   |
| `--deployment-dir`  | `/workspace/deployments/fr3_duo_example`             | Resolves policy contract path automatically                      |
| `--policy-type`     | `gr00t`                                              | Policy model the contract targets                                |
| `--policy-contract` | `<deployment-dir>/config_contract_<policy-type>.yml` | Override the policy contract path (required input)               |
| `--input`           | —                                                    | Explicit MCAP path (repeatable, mutually exclusive with filters) |
| `--episodes-dir`    | `/workspace/data/processed_episodes`                 | Root of the processed episodes tree                              |
| `--from`            | —                                                    | Include episodes on or after this date (inclusive)               |
| `--to`              | —                                                    | Include episodes on or before this date (inclusive)              |
| `--task`            | —                                                    | Substring match on task description (repeatable)                 |
| `--episode-id`      | —                                                    | Include specific episode UUID (repeatable)                       |
| `--exclude-id`      | —                                                    | Exclude specific episode UUID (repeatable)                       |
| `--limit`           | —                                                    | Max episodes to include                                          |
| `--include-failed`  | —                                                    | Include failed episodes                                          |
| `--dry-run`         | —                                                    | Preview matched episodes without converting                      |

## Task reference

| Task                            | Description                                                                                                                                  |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `dataset-builder-create`        | **Primary task** — build a dataset from processed episodes (set `DATASET_NAME`; optionally `FROM`, `TO`, `TASK_DESC`, `INPUT_MCAP`, `LIMIT`) |
| `dataset-builder-run`           | Run any command inside the container, defaults to an interactive shell (`CMD=/bin/bash`)                                                     |
| `build SERVICE=dataset-builder` | Build the Docker image                                                                                                                       |

## Notes

- The service expects MCAP input that already contains `foxglove.CompressedVideo` messages (i.e. output from
  `data-processor`, not raw `data-recorder` output).
- `lerobot` is installed inside the container image so its dependencies are not required on the host for local
  development.
- Set `DATA_ROOT` (default `../../../data`) and `DEPLOYMENTS_ROOT` (default `../../../deployments`) environment
  variables to point the Docker volume mounts at a non-default location.
