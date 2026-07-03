# Changelog

## [0.2.0] - UNRELEASED

- **Breaking Change:** Removed PostgreSQL database from the data-collection service to simplify the software stack:
  - Episode management now solely relies on the `episode_metadata.json` files of the episodes in the data directory.
  - Device status is now managed in memory.

  **Upgrade steps** (Delete database leftovers from existing deployments):

  > The episode metadata stored in the database is a subset of the information stored in
  > each episode's `episode_metadata.json` file. Unless you have manually modified
  > database records after they were written, the database can be safely removed without
  > data loss.
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
  4. Remove `database_url` from `config_data_collection.yml` and any references to the `postgres` and `migrate`
     services from your station-specific `docker-compose.yml`, `Taskfile.yml` and `Tiltfile`.
  5. All previously recorded episode metadata stored in the database will be lost after removal.
     Existing episode files on disk remain untouched.

- Removed deprecated episode fields `shipped` / `EpisodeShipped`, `object_url`, `episode_metadata_version` from
  episode models across all pipeline services.
- Removed deprecated record fields `output_path`, `metadata_path`, `recording_path`, `record_metadata_version`,
  `file_size_human`, float `start_timestamp` / `end_timestamp` from `RecordMetadata`.
- Episode list now shows up to 1000 episodes, the total count and full UUIDs in the UI.
- Fixed a bug where the episode duration/length in the episode list of the UI was incorrect.
- Renamed architecture diagram files from `labs-architecture.dsl/json` to `workspace.dsl/json`, fixed workflow
  state machine transitions and added a README with Structurizr Local setup instructions.
- Expanded dataset-builder service to create datasets from multiple episodes based on filters such as date range,
  task description, and more. The service supports dry-run mode for previewing matched episodes without conversion.
- Increased GOP (Group of Pictures) size to 30 to improve compression efficiency and reduce processing time.
  The exported datasets remain having a GOP size of 2 for compatibility with LeRobot format.
- Added `camera_info` topics to the data recorder configuration for all deployments to capture camera calibration data.
- Introduced an `AUTORECOVERY` state in the controller coordinator and the workflow state machine.
  When a controller dies during `READY`/`SYNCING`/`FOLLOWING`, the coordinator attempts to re-activate the hardware interface and
  the ready controller and returns to `READY`, falling back to `IDLE` on failure. The workflow mirrors
  this across all coordinators. A toast notification is shown in the UI while recovery is in progress.
- Recording can now only be started while the workflow is in `FOLLOWING`, and any active recording is
  automatically stopped (moved to review) when the workflow leaves `FOLLOWING`.
- Reduced device status poll interval to 0.5s, so the system status UI reflects device changes faster.
- All Docker containers were upgraded to use `ROS 2 Jazzy` (no longer a mix of `ROS 2 Humble` and `ROS 2 Jazzy`)
- The version of the `robotiq`, `realsense`, `franka_follower_controllers` packages were updated to their newest respective versions
- **Breaking Change:** An update to `franka_follower_controllers` requires the renaming of `arm_id` to `robot_type` in the `config_franka_robot.yml` configuration file of every deployment.
- The `example_station` deployment got renamed to `fr3_duo_example`. Users who edited this deployment might need to stash their changes before pulling and then re-apply them.

## [0.1.1] - 2026-06-01

- Fixed a bug where data processing could overload the system.

## [0.1.0] - 2026-06-01

- Initial prototype release of the LABS software platform.
