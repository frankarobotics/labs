from __future__ import annotations

import threading
import time
from uuid import UUID

import docker
from docker.errors import DockerException
from loguru import logger

from configs.station import StationConfig
from models.db import EpisodeDB
from models.system import ActiveEpisode, SystemGetResponse
from repos.episodes import EpisodeRepo
from state_machine.franka_workflow import FrankaWorkflowStateMachine
from state_machine.recording import RecordingStateMachine


class SystemService:
    """Service for managing and retrieving system information."""

    def __init__(
        self,
        recording_sm: RecordingStateMachine,
        workflow_sm: FrankaWorkflowStateMachine,
        episode_repo: EpisodeRepo,
        station_config: StationConfig,
    ) -> None:
        """Initialize the system service with required repos."""
        self.recording_sm: RecordingStateMachine = recording_sm
        self.workflow_sm: FrankaWorkflowStateMachine = workflow_sm
        self.episode_repo: EpisodeRepo = episode_repo
        self.station_config: StationConfig = station_config

    def get_system_info(self) -> SystemGetResponse:
        """Get consolidated system information."""
        active_episode: ActiveEpisode | None = None
        episode_id: UUID | None = self.recording_sm.current_episode_id
        if episode_id:
            try:
                ep: EpisodeDB | None = self.episode_repo.get_by_id(episode_id)
                if ep:
                    active_episode = ActiveEpisode(
                        id=str(ep.id),
                        status=str(ep.status.value),
                        started_on=ep.created_at.isoformat() if ep.created_at else None,
                        task_id=str(ep.task_id) if ep.task_id else None,
                    )
            except Exception as e:
                logger.error(f"Error fetching episode for system info: {e}")

        return SystemGetResponse(
            workflow_state=self.workflow_sm.current_state.name,
            recording_state=self.recording_sm.current_state.name,
            system_status="HEALTHY",
            station_id=self.station_config.metadata.station_id,
            active_episode=active_episode,
        )

    def restart_containers(self) -> dict[str, str]:  # noqa: C901, PLR0915
        """Restart all backend service containers.

        This method restarts all data collection service containers except:
        - Database containers (postgres)
        - Migration containers (migrate)
        - UI containers (data-collection-ui)

        Returns:
            dict with status and message

        Raises:
            DockerException: If Docker API connection fails
            RuntimeError: If container restart fails
        """
        logger.info("Initiating restart of backend containers")

        try:
            # Connect to Docker daemon
            client: docker.DockerClient = docker.from_env()

            # List of container name patterns to restart
            containers_to_restart: list[str] = [
                "data-collection",
                "data-recorder",
                "data-processor",
                "franka-robot-left",
                "franka-robot-right",
                "robotiq-gripper-left",
                "robotiq-gripper-right",
                "realsense-camera-head",
                "realsense-camera-wrist-left",
                "realsense-camera-wrist-right",
                "zed-camera",
                "franka-gello",
            ]

            # Containers to exclude from restart
            excluded_containers: list[str] = [
                "postgres",
                "migrate",
                "data-collection-ui",
            ]

            restarted_containers: list[str] = []
            failed_containers: list[str] = []
            data_collection_container = None

            # Get all containers
            all_containers = client.containers.list(all=True)

            for container in all_containers:
                container_name = container.name

                # Skip excluded containers
                if container_name in excluded_containers:
                    logger.debug(f"Skipping excluded container: {container_name}")
                    continue

                # Check if container matches any pattern to restart
                should_restart: bool = any(pattern in container_name for pattern in containers_to_restart)

                if should_restart:
                    # Save data-collection container to restart it last
                    if container_name == "data-collection":
                        data_collection_container = container
                        logger.debug("Saving data-collection container to restart last")
                        continue

                    try:
                        logger.info(f"Restarting container: {container_name}")
                        container.restart(timeout=10)
                        restarted_containers.append(container_name)
                        logger.info(f"Successfully restarted container: {container_name}")
                    except Exception as e:
                        logger.error(f"Failed to restart container {container_name}: {e}")
                        failed_containers.append(container_name)

            # Log summary before self-restart
            logger.info(f"Restart summary: {len(restarted_containers)} succeeded, {len(failed_containers)} failed")
            logger.info(f"Restarted containers: {restarted_containers}")
            if failed_containers:
                logger.warning(f"Failed containers: {failed_containers}")

            # Prepare response
            if failed_containers:
                response: dict[str, str] = {
                    "status": "partial",
                    "message": (
                        f"Restarted {len(restarted_containers)} containers, "
                        f"{len(failed_containers)} failed. Self-restart in 2s."
                    ),
                    "restarted": str(restarted_containers),
                    "failed": str(failed_containers),
                }
            else:
                response = {
                    "status": "success",
                    "message": f"Successfully restarted {len(restarted_containers)} containers. Self-restart in 2s.",
                    "restarted": str(restarted_containers),
                }

            # Schedule self-restart after returning response (if data-collection container found)
            if data_collection_container:
                logger.info("Scheduling data-collection container self-restart in 2 seconds...")

                def restart_self() -> None:
                    """Restart the data-collection container after delay."""
                    time.sleep(2)  # Wait 2 seconds to allow response to be sent
                    try:
                        logger.info("Restarting data-collection container (self) now - logs will terminate")
                        data_collection_container.restart(timeout=10)
                    except Exception as e:
                        logger.error(f"Failed to restart data-collection container: {e}")

                # Run restart in background thread
                restart_thread = threading.Thread(target=restart_self, daemon=True)
                restart_thread.start()
                logger.info("Self-restart scheduled in background thread")

            return response

        except DockerException as e:
            logger.error(f"Docker API error: {e}")
            raise RuntimeError(f"Failed to connect to Docker: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error during container restart: {e}")
            raise RuntimeError(f"Failed to restart containers: {e}") from e
