# Changelog

## [0.2.0] - UNRELEASED

- **Breaking Change:** Removed PostgreSQL database from the data-collection service to simplify the software stack:
  - Episode management now solely relies on the `episode_metadata.json` files of the episodes in the data directory.
  - Device status is now managed in memory.

  **Upgrade steps** (Delete database leftovers from existing deployments):

  > The episode metadata stored in the database is a subset of the information stored in each episode's
  > `episode_metadata.json` file. Unless you have manually modified database records after they were written, the
  > database can be safely removed without data loss.
  1. Navigate to deployment station folder
  2. Stop and remove the postgres and migrate containers:
     ```sh
     docker compose stop postgres migrate
     docker compose rm -f postgres migrate
     ```
  3. Remove the postgres data volume:
     ```sh
     docker volume rm <station_name>_postgres_data
     ```
  4. Remove `database_url` from `config_data_collection.yml` and any references to the `postgres` and `migrate` services
     from your station-specific `docker-compose.yml`, `Taskfile.yml` and `Tiltfile`.
  5. All previously recorded episode metadata stored in the database will be lost after removal. Existing episode files
     on disk remain untouched.

- **Breaking Change:** Switched the `robotiq-gripper` service to the officially supported [robotiq/ros](https://github.com/robotiq/ros)
  driver. The ROS interface stayed the same but you have to initialize the new submodule before the builds correctly.

  **Upgrade steps** (Add new submodule):
  - Run `task update-submodules` at the top level

- Removed deprecated episode fields `shipped` / `EpisodeShipped`, `object_url`, `episode_metadata_version` from episode
  models across all pipeline services.
- Removed deprecated record fields `output_path`, `metadata_path`, `recording_path`, `record_metadata_version`,
  `file_size_human`, float `start_timestamp` / `end_timestamp` from `RecordMetadata`.
- Episode list now shows up to 1000 episodes, the total count and full UUIDs in the UI.
- Fixed a bug where the episode duration/length in the episode list of the UI was incorrect.
- Renamed architecture diagram files from `labs-architecture.dsl/json` to `workspace.dsl/json`, fixed workflow state
  machine transitions and added a README with Structurizr Local setup instructions.
- Expanded dataset-builder service to create datasets from multiple episodes based on filters such as date range, task
  description, and more. The service supports dry-run mode for previewing matched episodes without conversion.
- Increased GOP (Group of Pictures) size to 30 to improve compression efficiency and reduce processing time. The
  exported datasets remain having a GOP size of 2 for compatibility with LeRobot format.
- Added `camera_info` topics to the data recorder configuration for all deployments to capture camera calibration data.
- Introduced an `AUTORECOVERY` state in the controller coordinator and the workflow state machine. If a controller dies
  during `READY`, `SYNCING`, or `FOLLOWING`, the coordinator attempts to clear robot errors, re-activate the hardware
  interface and the ready controller, then returns to `READY`, falling back to `IDLE` on failure. The workflow mirrors
  this across all coordinators. A toast notification is shown in the UI during recovery.
- Recording can now only be started while the workflow is in `FOLLOWING`, and any active recording is automatically
  stopped (moved to review) when the workflow leaves `FOLLOWING`.
- Reduced device status poll interval to 0.5s, so the system status UI reflects device changes faster.
- All Docker containers were upgraded to use `ROS 2 Jazzy` (no longer a mix of `ROS 2 Humble` and `ROS 2 Jazzy`)
- The version of the `robotiq`, `realsense`, `franka_follower_controllers` packages were updated to their newest
  respective versions
- **Breaking Change:** An update to `franka_follower_controllers` requires the renaming of `arm_id` to `robot_type` in
  the `config_franka_robot.yml` configuration file of every deployment.
- The `example_station` deployment got renamed to `fr3_duo_example`. Users who edited this deployment might need to
  stash their changes before pulling and then re-apply them.
- Services can now be started offline after a prior online build
- Refactor config loaders (CORS and station) in a common library shared by multiple services
- **Breaking Change:** `config_station.yml` is now the single source of truth for the recorded ROS 2 topics.

  **Upgrade steps:**
  1. Remove `ros_topics` from `config_data_recorder.yml` — the data-recorder now rejects the key at startup.
  2. In `config_station.yml`, declare each camera's calibration stream as an `info.topic` next to its image streams
     (previously the recorder appended `camera_info` implicitly).
  3. In `config_station.yml`, add the ROS graph topics under the new `embodiment.other_topics` section as a `ROS_INFRA`
     entry (previously hard-coded in the recorder), and any extra topics you record as `USER_TOPICS` entries. See the
     [Deployment README](deployments/README.md#recorded-topics) and `deployments/fr3_duo_example/config_station.yml`.

- **Breaking Change:** Add a `packages` folder to `services` for shared libraries, and move the station and CORS config
  loaders there.

  **Upgrade steps:**
  1. Copy `packages_context_custom_build` of the example station's `Tiltfile` to your deployment's `Tiltfile`.
  2. Use this function for the packages that need access to the station and CORS config loaders, e.g.: data-collection
     and data-recorder. See the example station's `Tiltfile` for usage examples.

- Create `config_contract_gr00t.yml` in deployments to define the contract for GR00T models that the dataset-builder
  service uses for the creation of the dataset.
- Fix the processing of the `geometry_msgs/TwistStamped` message type in `config_station.yml`.
- **Breaking Change:** dataset-builder now builds datasets from a policy contract instead of `config_station.yml` +
  `config_data_recorder.yml`:
  - `--station-config`, `--recorder-config` and `--modality-config` are replaced by `--policy-contract`.
    `--deployment-dir` keeps working and resolves the policy contract from the deployment folder.
  - Added `--policy-type` (default `gr00t`) to select `config_contract_<policy-type>.yml` from `--deployment-dir`
  - The contract is required; the previous fallback to ROS schema-name heuristics is gone, since it could not produce
    the declared state/action vector layout.
  - `--fps` now defaults to the contract's `policy.control_rate_hz` rather than `20.0`, and only acts as an override.
  - Parquet state columns are named `observation.state.<policy_key>` (previously derived from the topic name), and
    `meta/modality.json` is generated from the contract instead of copied from the deployment.
  - Several segments may now read the same topic, so a `sensor_msgs/JointState` topic can contribute positions,
    velocities and efforts to one dataset, each reordered to the contract's `element_names`.
  - An episode missing any topic the contract declares is rejected instead of silently producing shorter vectors.
  - Camera segments can set `resize: true` to letterbox recordings to the declared contract shape while preserving the
    source aspect ratio.

  **Upgrade steps:** Add a `config_contract_gr00t.yml` to each custom deployment, following the `fr3_duo_example` one
  (see the [dataset-builder README](services/pipeline/dataset-builder/README.md#policy-contract)), and delete the now
  unused `modality.json`.

## [0.1.1] - 2026-06-01

- Fixed a bug where data processing could overload the system.

## [0.1.0] - 2026-06-01

- Initial prototype release of the LABS software platform.
