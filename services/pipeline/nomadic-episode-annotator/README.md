# Nomadic Episode Annotator

Optional service that sends one saved LABS episode at a time to Nomadic for action annotation, on an operator's request.
Results include timestamped actions and, when available, acting hands, objects, gripper transitions and object
interactions. Stations without this service run unchanged.

## Interface

- HTTP on port `3005`, under `/api/v1/episodes/{episode_id}/annotations`.
- Reads processed episodes from `/workspace/data/processed_episodes` (read-only).
- Keeps job state in `/workspace/data/nomadic_annotations` (read-write).
- Configured through `NOMADIC_*` environment variables; see [Configuration](#configuration).

Runs as a single process because the job store admits one worker. Only the `data-collection-ui` server calls it, and
only when that server has `NOMADIC_EPISODE_ANNOTATOR_PORT` set; otherwise the episode page shows no annotation panel.

## Data leaving the station

Read this before enabling the service, and confirm the decision with whoever owns the station's data.

- **What is uploaded:** a prepared copy of the episode's processed MCAP, containing:
  - every channel of the processed recording, copied unchanged except the camera streams, which are re-encoded to H.264.
    On the FR3 Duo this includes measured joint states, gripper states, external wrenches, arm and gripper commands,
    `/tf_static` and camera intrinsics;
  - channels derived on the station: named measurement signals, normalized gripper closedness, nominal flange poses and
    camera calibrations;
  - the MCAP's metadata and attachments, including the processor's `episode_context` (episode, task and station ids,
    task name, description, language instructions and task metadata);
  - the episode's task description from `episode_metadata.json`, the episode id and the SHA-256 of the processed file.
- **Where it goes:** the Nomadic API at `NOMADIC_BASE_URL` (default `https://api-prod.nomadicml.com`), into the
  `NOMADIC_FOLDER` folder (default `Franka LABS`) of the account that owns `NOMADIC_API_KEY`. Retention and deletion
  follow that account's terms with Nomadic, not LABS.
- **When:** only when an operator selects **Auto Annotate with Nomadic** for one saved episode. Nothing is sent in the
  background, and uploads or analyses with an uncertain outcome are never retried automatically. **Refresh saved
  result** only fetches an existing analysis.
- **What stays local:** the API key (never sent to the browser), raw episodes, the original processed recording, other
  episodes and the job store. The prepared copy is deleted from the station once the job ends.

## Setup

For the FR3 Duo example station:

1. Build the image from the repository root: `task build SERVICE=nomadic-episode-annotator`. `BUILD_TARGET` selects
   another target than `dev`.
2. Set `NOMADIC_API_KEY` in the shell environment, or supply an environment file with Compose's `--env-file` option.
   Keep the key out of version control.
3. Start the service and restart the UI so it shows the annotation panel:

```sh
cd deployments/fr3_duo_example
docker compose -f docker-compose.yml -f nomadic.compose.yml up -d nomadic-episode-annotator data-collection-ui
```

`nomadic.compose.yml` adds the annotator with read-only access to processed episodes and the configuration directory,
and sets `NOMADIC_EPISODE_ANNOTATOR_PORT` on the UI. `data-collection` is not recreated, so this can run during a
recording session; restarting the UI is the only interruption.

To disable it again, start the UI without the override and remove the service:

```sh
docker compose up -d data-collection-ui
docker compose -f docker-compose.yml -f nomadic.compose.yml rm -sf nomadic-episode-annotator
```

For another deployment, copy `nomadic.compose.yml` and adjust its mounts. The service's own `docker-compose.yml` runs it
standalone against `DATA_ROOT`.

### Select a different configuration file

The service derives its recording mapping from `config_contract_gr00t.yml`; a separate spec file is not needed for the
reference setup. The example override reads:

| Variable                       | Default                     | Meaning                                                                                         |
| ------------------------------ | --------------------------- | ----------------------------------------------------------------------------------------------- |
| `NOMADIC_CONFIG_DIR`           | The deployment directory    | Directory on the host containing the configuration files.                                       |
| `NOMADIC_POLICY_CONTRACT_FILE` | `config_contract_gr00t.yml` | LABS contract filename, relative to that directory.                                             |
| `NOMADIC_SPEC_FILE`            | Unset                       | Optional Nomadic spec filename, relative to that directory. Takes precedence over the contract. |

For example, select an existing LABS contract stored outside the deployment directory:

```sh
export NOMADIC_CONFIG_DIR=/absolute/path/to/station-config
export NOMADIC_POLICY_CONTRACT_FILE=my-contract.yml
```

Then run the same Compose command. The directory must exist and the selected file must be readable. Relative
`NOMADIC_CONFIG_DIR` paths resolve from `deployments/fr3_duo_example`.

For an already Nomadic-compatible recording, select an explicit spec instead:

```sh
export NOMADIC_CONFIG_DIR=/absolute/path/to/nomadic-config
export NOMADIC_SPEC_FILE=my-spec.json
```

The selection order is an explicit spec, an embedded `nomadic_spec`, then the reference contract. Custom specs require
Nomadic-compatible messages. The contract-based ROS conversion supports the FR3 Duo reference layout described below.

### Configuration

For the reference Docker setup, only the API key requires a new value. Keep the state directory across container
replacement to retain saved results and prevent duplicate submissions. To change a setting not referenced in
`nomadic.compose.yml`, add it to the service's `environment` in a deployment override.

| Variable                          | Default                               | When to override                                               |
| --------------------------------- | ------------------------------------- | -------------------------------------------------------------- |
| `NOMADIC_ENABLED`                 | `false`                               | Enable annotations; the example override sets this to `true`.  |
| `NOMADIC_API_KEY`                 | Unset                                 | Required Nomadic account credential.                           |
| `NOMADIC_POLICY_CONTRACT_PATH`    | Unset; set by the example override    | Existing LABS reference I/O contract.                          |
| `NOMADIC_SPEC_PATH`               | Unset                                 | Spec for an already compatible recording.                      |
| `NOMADIC_FOLDER`                  | `Franka LABS`                         | Choose the destination folder in Nomadic.                      |
| `NOMADIC_PROCESSED_EPISODES_PATH` | `/workspace/data/processed_episodes`  | Use a different processed recording directory.                 |
| `NOMADIC_STATE_PATH`              | `/workspace/data/nomadic_annotations` | Use a different persistent state directory.                    |
| `NOMADIC_BASE_URL`                | `https://api-prod.nomadicml.com`      | Connect to a different Nomadic API deployment.                 |
| `NOMADIC_DASHBOARD_URL`           | `https://app.nomadicml.com`           | Open Workbench in a different Nomadic deployment.              |
| `NOMADIC_TIMEOUT_SECONDS`         | `3600`                                | Change the wait limit for recording processing and annotation. |
| `NOMADIC_MAX_PENDING_JOBS`        | `4`                                   | Change the queue bound; one worker handles annotation jobs.    |
| `NOMADIC_MAX_RECORDING_BYTES`     | `4294967296` (4 GiB)                  | Change the accepted recording size.                            |

With `NOMADIC_ENABLED=false`, or without an API key, the episode page explains why and does not offer submission.

The API key's Nomadic account must have access to MCAP uploads and robot action annotation. The SDK calls this
annotation mode `index(..., mode="robotics")`.

## Use

1. Record and save an episode as usual.
2. Wait for LABS to finish processing it.
3. Open the episode under **Episodes** and select **Auto Annotate with Nomadic**.
4. Follow the progress on the episode page. Recording other episodes can continue.
5. Review the action table, expand **Details**, download the annotations, or select **Open in Nomadic Workbench** for
   further review.

Original recordings are retained unchanged. Results are saved on the station; refreshing or reopening the page does not
submit another job. The local results are a snapshot of the completed analysis; later edits in Nomadic are not
synchronized.

Hand and Objects columns appear only when data is present. Every returned action class is shown as a tag. The JSON
download includes the complete returned `structured_output`, including fields not displayed in the table. Missing fields
are left empty rather than inferred from descriptions.

## Recordings

An episode must be saved and have the processor's `.processing_complete` marker. A single processed MCAP is required;
raw recordings and multi-file stitching are not supported.

LABS whole-video camera messages are converted to H.264 frames. For the reference station, camera clocks are anchored to
the recorded capture stamps and aligned to the head camera's fixed playback rate. Short gaps repeat the nearest frame;
the prepared spec records camera offsets and repeated frames. Long gaps, mismatched frame counts and non-increasing
timestamps are rejected before upload. Existing supported compressed frames or images are preserved.

### Reference station mapping

The reference adapter derives camera and measurement mappings from the checked-in configuration:

- `config_station.yml` defines the recorded head and wrist cameras and robot observer topics.
- `config_contract_gr00t.yml` supplies processed camera topic names, measured fields and ordered joint names through the
  existing `pipeline-configs` models.
- The Robotiq driver documents its measured knuckle range: 0 radians open and 0.8 radians closed. The adapter retains
  the original angle and adds `angle / 0.8` as normalized gripper closedness: 0 fully open, 1 fully closed.

The adapter adds `nomadic.Signal` channels for measured joint positions, velocities, torques, gripper angles, gripper
velocities, normalized gripper closedness and external wrenches. Recorded arm and gripper commands are separate signals.
Measurements use ROS capture stamps; headerless commands use MCAP recording timestamps. The saved episode JSON supplies
the task instruction when present, taking precedence over embedded episode context.

Each arm also has a derived flange pose from the nominal FR3 geometry. The adapter applies the arm-base transforms in
`/tf_static` so both poses use the same recorded parent frame. Missing, conflicting or disconnected base transforms are
rejected. These are not measured gripper TCP poses, and recorded transforms do not establish physical calibration. If
both bases are recorded at the same position, the service warns that the viewer shows nominal placement. A correctly
positioned combined 3D view still requires station calibration. Recorded camera intrinsics are copied from `CameraInfo`;
camera extrinsics are not inferred. Joint measurements remain available as signals, while trajectory parts use flange
poses to avoid selecting an unrelated robot model in the viewer.

Unsupported contract layouts, missing channels, ambiguous joint names and invalid measurements fail before upload.
Verify the resulting camera views and trajectory on a representative station recording. Action definitions and boundary
accuracy should also be reviewed against the intended annotation task.

## Troubleshooting

- **Recording not ready:** wait for LABS processing to finish. If processing failed, check the processor before
  annotating.
- **Mapping or preparation error:** check the recording and mapping. Failures before upload can be corrected and
  submitted again.
- **Queue full:** wait for a running annotation to finish, then retry.
- **Upload, processing or annotation interrupted:** inspect the saved references and Nomadic workspace before submitting
  again. The service does not repeat uploads or analyses after an uncertain outcome.
- **Saved result could not be loaded:** use **Refresh saved result** when offered. This retrieves the existing analysis
  without uploading or analyzing again.
- **Service restarted during annotation:** the job is marked interrupted. Known Nomadic identifiers are retained for
  inspection or retrieval.
- **Storage unavailable:** check that the state directory is writable and persistent. Do not remove annotation state to
  retry a job that may already exist in Nomadic.
- **Annotation temporarily unavailable on the episode page:** the UI cannot reach the service; check that it is running
  on port `3005`. The rest of the episode page remains available.

## Development

```sh
uv run --frozen pytest
```

The tests use generated recordings and mock the SDK transport. They do not upload recordings or run remote analyses.
`test_reference_station.py` checks the actual station/contract and driver conventions. Its upstream-processor check also
requires the data-processor's `foxglove-sdk`, `ffmpeg-python` and an FFmpeg executable with AV1 support; it is skipped
when those are absent. A station check with a representative LABS recording is also required when validating a
deployment.
