# Changelog

## [0.2.0] - UNRELEASED

**Breaking Change**

- **Removed PostgreSQL database** from the data-collection service to simplify the software stack:
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
  4. Remove `database_url` from your deployments `config_data_collection.yml` if present.
  5. All previously recorded episode metadata stored in the database will be lost after removal.
     Existing episode files on disk remain untouched.

- **Removed deprecated episode fields**: `shipped` / `EpisodeShipped`, `object_url`, `episode_metadata_version` from episode models across all pipeline services.
- **Removed deprecated record fields**: `output_path`, `metadata_path`, `recording_path`, `record_metadata_version`, `file_size_human`, float `start_timestamp` / `end_timestamp` from `RecordMetadata`.
- **Episode list UI**: increased limit to 1000 episodes, show episode count, display full UUID instead of truncated suffix.
- **Fixed a bug**: the episode duration/length in the episode list of the UI was incorrect.
- **Architecture diagrams**: renamed `labs-architecture.dsl/json` → `workspace.dsl/json`; fixed workflow state machine transitions; added README with instructions for Structurizr Local.
- Expanded dataset-builder service to create datasets from multiple episodes based on filters such as date range, task description, and more.
  The service supports dry-run mode for previewing matched episodes without conversion.
- Increased GOP (Group of Pictures) size to 30 to improve compression efficiency and reduce processing time.
  The exported datasets remain having a GOP size of 2 for compatibility with LeRobot format.
- Added `camera_info` topics to the data recorder configuration for all deployments to capture camera calibration data.

## [0.1.1] - 2026-06-01

- Fixed a bug where data processing could overload the system.

## [0.1.0] - 2026-06-01

- Initial prototype release of the LABS software platform.
