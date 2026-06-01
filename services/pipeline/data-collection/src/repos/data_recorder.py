"""Repository for interacting with the data recorder service via REST API."""

from typing import Any
from uuid import UUID

import requests
from loguru import logger

from configs.data_recorder import DataRecorderConfig
from models.record import RecordResponse, RecordStateResponse, RecordStatusResponse

# HTTP status constants
HTTP_OK: int = 200


class DataRecorderRepo:
    """Repository for communicating with the data recorder service using RESTful interface."""

    def __init__(self, config: DataRecorderConfig) -> None:
        """Initialize the data recorder repository.

        Args:
            config: Configuration for the data recorder service. If None, loads from environment.
        """
        self.config: DataRecorderConfig = config
        self.base_url: str = self.config.url
        self.request_timeout: float = self.config.request_timeout

    def start_recording(self, episode_id: UUID) -> RecordResponse:
        """Start recording data for the given episode.

        Args:
            episode_id: The UUID of the episode to start recording.

        Returns:
            RecordResponse with the result of the operation.

        Raises:
            requests.RequestException: If the HTTP request fails.
            Exception: If there's an error processing the response.
        """
        url: str = f"{self.base_url}/api/v1/record/start"
        payload: dict[str, str] = {"episode_id": str(episode_id)}

        logger.info(f"Starting recording for episode {episode_id}")

        try:
            response: requests.Response = requests.post(url, json=payload, timeout=self.request_timeout)
            response.raise_for_status()
            data: dict[str, Any] = response.json()

            logger.info(f"Successfully started recording for episode {episode_id}")
            return RecordResponse(status=data.get("status", ""), message=data.get("message", ""))

        except requests.RequestException as e:
            logger.error(f"HTTP error starting recording for episode {episode_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error starting recording for episode {episode_id}: {e}")
            raise

    def stop_recording(self, episode_id: UUID) -> RecordResponse:
        """Stop recording data.

        Args:
            episode_id: The UUID of the episode (used for logging only).

        Returns:
            RecordResponse with the result of the operation.

        Raises:
            requests.RequestException: If the HTTP request fails.
            Exception: If there's an error processing the response.
        """
        url: str = f"{self.base_url}/api/v1/record/stop"

        logger.info(f"Stopping recording for episode {episode_id}")

        try:
            response: requests.Response = requests.post(url, timeout=self.request_timeout)
            response.raise_for_status()
            data: dict[str, Any] = response.json()

            logger.info(f"Successfully stopped recording for episode {episode_id}")
            return RecordResponse(status=data.get("status", ""), message=data.get("message", ""))

        except requests.RequestException as e:
            logger.error(f"HTTP error stopping recording for episode {episode_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error stopping recording for episode {episode_id}: {e}")
            raise

    def get_recording_status(self, episode_id: UUID) -> RecordStatusResponse:
        """Get the recording status for the given episode.

        Args:
            episode_id: The UUID of the episode to check status for.

        Returns:
            RecordStatusResponse with the current recording status.

        Raises:
            requests.RequestException: If the HTTP request fails.
            Exception: If there's an error processing the response.
        """
        url: str = f"{self.base_url}/api/v1/record/status/{episode_id}"

        logger.debug(f"Getting recording status for episode {episode_id}")

        try:
            response: requests.Response = requests.get(url, timeout=self.request_timeout)
            response.raise_for_status()
            data: dict[str, Any] = response.json()

            logger.debug("Retrieved recording status for episode {}: {}", episode_id, data)
            return RecordStatusResponse(
                status=str(data.get("status", "")),
                is_recording=bool(data.get("is_recording", False)),
                episode_id=UUID(data.get("episode_id")) if data.get("episode_id") else None,
            )

        except requests.RequestException as e:
            logger.error(f"HTTP error getting recording status for episode {episode_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error getting recording status for episode {episode_id}: {e}")
            raise

    def delete_recording(self, episode_id: UUID) -> RecordResponse:
        """Delete the recording for the given episode.

        Args:
            episode_id: The UUID of the episode to delete.

        Returns:
            RecordResponse with the result of the operation.

        Raises:
            requests.RequestException: If the HTTP request fails.
            Exception: If there's an error processing the response.
        """
        url: str = f"{self.base_url}/api/v1/record/{episode_id}"

        logger.info(f"Deleting recording for episode {episode_id}")

        try:
            response: requests.Response = requests.delete(url, timeout=self.request_timeout)
            response.raise_for_status()
            data: dict[str, Any] = response.json()

            logger.info(f"Successfully deleted recording for episode {episode_id}")
            return RecordResponse(status=data.get("status", ""), message=data.get("message", ""))

        except requests.RequestException as e:
            logger.error(f"HTTP error deleting recording for episode {episode_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error deleting recording for episode {episode_id}: {e}")
            raise

    def health_check(self) -> bool:
        """Perform a health check on the data recorder service.

        Returns:
            True if the service is healthy, False otherwise.
        """
        try:
            response: requests.Response = requests.get(f"{self.base_url}/health", timeout=5.0)
            return response.status_code == HTTP_OK
        except Exception as e:
            logger.warning(f"Health check failed for data recorder service: {e}")
            return False

    def get_recorder_state(self) -> RecordStateResponse:
        """Get the recorder state for the given episode.

        Returns:
            RecordStateResponse with the current recorder state.

        Raises:
            requests.RequestException: If the HTTP request fails.
            Exception: If there's an error processing the response.
        """
        url: str = f"{self.base_url}/api/v1/record/state"

        logger.debug("Getting recorder state")

        try:
            response: requests.Response = requests.get(url, timeout=self.request_timeout)
            response.raise_for_status()
            data: dict[str, Any] = response.json()

            status_val: str = str(data.get("status", ""))
            is_recording_val: bool = bool(data.get("is_recording", False))
            episode_id_val = data.get("episode_id", "")
            logger.debug(
                "Retrieved recorder state: status={}, is_recording={}, episode_id={}",
                status_val,
                is_recording_val,
                episode_id_val,
            )
            return RecordStateResponse(
                status=str(status_val),
                is_recording=is_recording_val,
                episode_id=UUID(episode_id_val) if episode_id_val else None,
            )

        except requests.RequestException as e:
            logger.error(f"HTTP error getting recorder status: {e}")
            raise
        except Exception as e:
            logger.error(f"Error getting recorder status: {e}")
            raise
