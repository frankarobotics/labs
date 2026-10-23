# Nomadic annotations

Generate action annotations for saved episodes from the LABS episode page. Results include timestamped actions and, when
available, acting hands, objects, gripper transitions and object interactions.

Recording, teleoperation and LABS processing continue through the existing services. Annotation starts only when an
operator selects **Auto Annotate with Nomadic**.

## Setup

The integration runs in LABS' existing `data-collection` backend and adds controls to its `data-collection-ui` web
interface. Keep the API key on the backend; no Nomadic credential is needed by the browser.

For the FR3 Duo example station:

1. Set `NOMADIC_API_KEY` in the shell environment, or supply an environment file with Compose's `--env-file` option.
   Keep the key out of version control.
2. Use the existing station configuration and `config_contract_gr00t.yml`. The integration derives its recording mapping
   from this contract; a separate spec file is not needed for the reference setup.
3. From a checkout containing the integration, run from the repository root:

```sh
docker compose \
  -f deployments/fr3_duo_example/docker-compose.yml \
  -f deployments/fr3_duo_example/nomadic.compose.yml \
  up -d --build data-collection data-collection-ui
```

The first Compose file supplies the normal station settings. The second adds the optional Nomadic dependencies, enables
annotations and mounts the configuration directory read-only. It uses the station's existing data mount and does not add
another service. Both the backend and UI are rebuilt with the integration code. The command recreates these services, so
run it between recording sessions.

Builds default to the repository's `dev` target; `BUILD_TARGET` selects another target. The reference contract supplies
camera and signal configuration. Review the mapping if the station changes its hardware or recording layout.

For another deployment, include the same build settings, environment variables and configuration mount in its deployment
files. Setting `NOMADIC_ENABLED=true` at runtime enables annotations only when the optional dependencies are already
installed in the backend image.

### Select a different configuration file

The following environment variables are read by the example Compose override:

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

Then run the same Compose command above. The directory must exist and the selected file must be readable. Relative
`NOMADIC_CONFIG_DIR` paths resolve from `deployments/fr3_duo_example`, the directory of the first Compose file.

For an already Nomadic-compatible recording, select an explicit spec instead:

```sh
export NOMADIC_CONFIG_DIR=/absolute/path/to/nomadic-config
export NOMADIC_SPEC_FILE=my-spec.json
```

Without `NOMADIC_SPEC_FILE`, an embedded `nomadic_spec` takes precedence over the reference contract. Custom specs
require Nomadic-compatible messages. The contract-based ROS conversion supports the FR3 Duo reference layout described
below.

Set `NOMADIC_ENABLED=false` to disable annotations while keeping the rest of LABS available. With annotations enabled
and no API key, the episode page explains that the key is not configured and does not offer submission.

### Installation outside containers

For an installation outside containers, install the optional dependencies with `uv sync --extra nomadic`, then set
`NOMADIC_ENABLED=true`, `NOMADIC_API_KEY` and `NOMADIC_POLICY_CONTRACT_PATH` on the data-collection service. The
contract path should point to the station's existing `config_contract_gr00t.yml`.

For an already Nomadic-compatible recording, `NOMADIC_SPEC_PATH` selects an explicit spec. The selection order is an
explicit spec, an embedded `nomadic_spec`, then the configured reference contract.

### Defaults and overrides

For the reference Docker setup, only the API key requires a new value. The processed recording directory is read from
LABS' `data_collection.processed_data_path`. Annotation state defaults to `nomadic_annotations` alongside that
directory. Retain this data directory across container replacement to keep saved results and prevent duplicate
submissions.

The settings below are read by the data-collection service. To change a setting that is not already referenced in
`nomadic.compose.yml`, add it to that service's `environment` in a deployment override.

| Variable                          | Default                           | When to override                                               |
| --------------------------------- | --------------------------------- | -------------------------------------------------------------- |
| `NOMADIC_ENABLED`                 | `false`                           | Enable annotations; the example override sets this to `true`.  |
| `NOMADIC_API_KEY`                 | Unset                             | Required Nomadic account credential.                           |
| `NOMADIC_POLICY_CONTRACT_PATH`    | Unset; set by the Docker override | Existing LABS reference I/O contract.                          |
| `NOMADIC_SPEC_PATH`               | Unset                             | Override with a spec for an already compatible recording.      |
| `NOMADIC_FOLDER`                  | `Franka LABS`                     | Choose the destination folder in Nomadic.                      |
| `NOMADIC_PROCESSED_EPISODES_PATH` | Existing LABS configuration       | Use a different processed recording directory.                 |
| `NOMADIC_STATE_PATH`              | Beside processed episodes         | Use a separate persistent state directory.                     |
| `NOMADIC_BASE_URL`                | `https://api-prod.nomadicml.com`  | Connect to a different Nomadic API deployment.                 |
| `NOMADIC_DASHBOARD_URL`           | `https://app.nomadicml.com`       | Open Workbench in a different Nomadic deployment.              |
| `NOMADIC_TIMEOUT_SECONDS`         | `3600`                            | Change the wait limit for recording processing and annotation. |
| `NOMADIC_MAX_PENDING_JOBS`        | `4`                               | Change the queue bound; one worker handles annotation jobs.    |
| `NOMADIC_MAX_RECORDING_BYTES`     | `4294967296` (4 GiB)              | Change the accepted recording size.                            |

The API key's Nomadic account must have access to MCAP uploads and robot action annotation. The SDK calls this
annotation mode `index(..., mode="robotics")`.

## Use

1. Record and save an episode as usual.
2. Wait for LABS to finish processing it.
3. Open the episode under **Episodes** and select **Auto Annotate with Nomadic**.
4. Follow the progress on the episode page. Recording other episodes can continue.
5. Review the action table, expand **Details**, download the annotations, or select **Open in Nomadic Workbench** for
   further review.

The integration uploads a prepared copy and generates action annotations through the Nomadic SDK. Original recordings
are retained unchanged. Results are saved on the station; refreshing or reopening the page does not submit another job.
The local results are a snapshot of the completed analysis; subsequent edits in Nomadic are not automatically
synchronized.

Hand and Objects columns appear only when data is present. Every returned action class is shown as a tag. The JSON
download includes the complete returned `structured_output`, including fields not displayed in the table. Missing fields
are left empty rather than inferred from descriptions.

## Recordings

An episode must be saved and have the processor's `.processing_complete` marker. A single processed MCAP is required;
raw recordings and multi-file stitching are not supported by this integration.

LABS whole-video camera messages are converted to H.264 frames. For the reference station, camera clocks are anchored to
the recorded capture stamps and aligned to the head camera's fixed playback rate. Short gaps repeat the nearest frame;
the prepared spec records camera offsets and repeated frames. Long gaps, mismatched frame counts and non-increasing
timestamps are rejected before upload. Existing supported compressed frames or images are preserved. Original sensor
messages, metadata and attachments remain in the prepared copy.

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
both bases are recorded at the same position, the integration warns that the viewer shows nominal placement. A correctly
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
  again. The integration does not automatically repeat uploads or analyses after an uncertain outcome.
- **Saved result could not be loaded:** use **Refresh saved result** when offered. This retrieves the existing analysis
  without uploading or analyzing again.
- **Station restarted during annotation:** the job is marked interrupted. Known Nomadic identifiers are retained for
  inspection or retrieval.
- **Storage unavailable:** check that the station's data directory is writable and persistent. Do not remove annotation
  state to retry a job that may already exist in Nomadic.

The rest of the episode page remains available when Nomadic cannot be reached.

## Development checks

```sh
uv run --extra nomadic pytest tests -o addopts=""
```

The tests use generated recordings and mock the SDK transport. They do not upload recordings or run remote analyses.
`test_reference_station.py` checks the actual station/contract and driver conventions. Its upstream-processor check also
requires the data-processor's `foxglove-sdk`, `ffmpeg-python` and an FFmpeg executable with AV1 support; it is skipped
when those optional test dependencies are absent. It runs generated ROS messages through LABS' real converter and then
the Nomadic adapter. A station/container check with a representative LABS recording is also required when validating a
deployment.
