# Changelog

## [0.2.0] - 2026-09-03

- **Breaking Change:** Removed PostgreSQL database from the data-collection service. Episode management now relies
  solely on `episode_metadata.json` files, and device status is managed in memory. User deployments must remove database
  leftovers (see migration notes below).
- **Breaking Change:** `franka_follower_controllers` requires renaming a configuration parameter in every user-created
  deployment (see migration notes below).
- **Breaking Change:** Switched the `robotiq-gripper` service to the officially supported
  [robotiq/ros](https://github.com/robotiq/ros) driver. The ROS interface stayed the same, but the new submodule has to
  be initialized before the service builds (see migration notes below).
- **Breaking Change:** `config_station.yml` is now the single source of truth for the recorded ROS 2 topics. The
  data-recorder rejects `ros_topics` in `config_data_recorder.yml` and no longer appends camera or ROS graph topics
  implicitly (see migration notes below).
- **Breaking Change:** Added a `packages` folder to `services` for shared libraries and moved the station and CORS
  config loaders there. Deployments must give the services using them access to that folder (see migration notes below).
- **Breaking Change:** dataset-builder now builds datasets from a policy contract instead of `config_station.yml` and
  `config_data_recorder.yml`. Every deployment needs a `config_contract_gr00t.yml` (see migration notes below):
  - `--station-config`, `--recorder-config` and `--modality-config` are replaced by `--policy-contract`.
    `--deployment-dir` keeps working and resolves the policy contract from the deployment folder.
  - Added `--policy-type` (default `gr00t`) to select `config_contract_<policy-type>.yml` from `--deployment-dir`.
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
- Expanded dataset-builder service to create datasets from multiple episodes with filters (date range, task description,
  etc.) and dry-run mode for previewing matches.
- Introduced `AUTORECOVERY` state in controller coordinator and workflow state machine. If a controller dies during
  `READY`, `SYNCING`, or `FOLLOWING`, the system attempts to clear robot errors and re-activate the hardware interface
  and the ready controller; a UI notification indicates recovery progress.
- The controller coordinator now detects reflex errors within ~20ms via a dedicated `robot_state` staleness monitor,
  instead of relying solely on the hardware interface, which can take up to ~2 seconds to reflect a reflex.
- Recording now can only be started in `FOLLOWING` state and stops automatically when the workflow leaves it.
- Upgraded all Docker containers to `ROS 2 Jazzy` (previously a mix of Humble and Jazzy).
- Services can now be started offline after a prior online build.
- Camera calibration (`camera_info`) streams are now part of the recorded topics of all deployments.
- The `example_station` deployment got renamed to `fr3_duo_example`.
- Episode list now displays up to 1000 episodes with total count and full UUIDs.
- Fixed incorrect episode duration/length display in the episode list UI.
- Fixed the processing of the `geometry_msgs/TwistStamped` message type in `config_station.yml`.
- Reduced device status poll interval to 0.5s for faster UI updates.
- Increased GOP (Group of Pictures) size of processed episodes to 30 for improved compression and reduced processing
  time (exported datasets retain GOP size of 2 for LeRobot compatibility).
- Updated `robotiq`, `realsense`, and `franka_follower_controllers` submodules to their latest versions.
- Removed deprecated episode fields: `shipped` / `EpisodeShipped`, `object_url`, `episode_metadata_version`.
- Removed deprecated record fields: `output_path`, `metadata_path`, `recording_path`, `record_metadata_version`,
  `file_size_human`, and `start_timestamp` / `end_timestamp`.
- Updated the architecture diagrams and added a README for editing them with a local Structurizr setup.
- Removed unmaintained per-service `version` fields from `pyproject.toml` files; services are versioned as a whole via
  this changelog.

### Migration notes

1. If you edited the `example_station` deployment, stash the changes before upgrading.
2. Initialize the new `robotiq/ros` submodule by running `task update-submodules` at the top level.
3. Stop and remove the postgres and migrate containers:
   ```sh
   docker compose stop postgres migrate
   docker compose rm -f postgres migrate
   ```
4. Remove postgres data volumes from your deployments (check `volumes` in `docker-compose.yml`):
   ```sh
   docker volume rm <station_name>_postgres_data
   ```
   > **Note:** All episode data is preserved in each episode's `episode_metadata.json` file, so the volumes can be
   > safely removed unless you have manually modified database records.
5. Search your deployments for "postgres", "migrate", and "database", then remove all related parameters, services,
   variables, and commands from these files: `docker-compose.yml`, `Taskfile.yml`, `Tiltfile`, and
   `config_data_collection.yml`.
6. In each deployment's `config_franka_robot.yml`, rename all occurrences of `arm_id` to `robot_type`.
7. Move the recorded topics into `config_station.yml`:
   - Remove `ros_topics` from `config_data_recorder.yml` — the data-recorder now rejects the key at startup.
   - Declare each camera's calibration stream as an `info.topic` next to its image streams.
   - Add the ROS graph topics under the new `embodiment.other_topics` section as a `ROS_INFRA` entry, and any extra
     topics you record as `USER_TOPICS` entries. See the [Deployment README](deployments/README.md#recorded-topics) and
     `deployments/fr3_duo_example/config_station.yml`.
8. Give your deployment access to the shared packages:
   - Copy `packages_context_custom_build` of the example station's `Tiltfile` to your deployment's `Tiltfile`.
   - Use this function for the packages that need access to the station and CORS config loaders, e.g. data-collection
     and data-recorder. See the example station's `Tiltfile` for usage examples.
9. Add a `config_contract_gr00t.yml` to each custom deployment, following the `fr3_duo_example` one (see the
   [dataset-builder README](services/pipeline/dataset-builder/README.md#policy-contract)), and delete the now unused
   `modality.json`.

## [0.1.1] - 2026-06-01

- Fixed a bug where data processing could overload the system.

## [0.1.0] - 2026-06-01

- Initial prototype release of the LABS software platform.
