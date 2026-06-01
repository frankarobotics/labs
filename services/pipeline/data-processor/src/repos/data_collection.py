"""Repo to query the data-collection service."""

from collections.abc import Iterable
from typing import Any
from uuid import UUID

import requests
from loguru import logger

from configs.data_collection import DataCollectionConfig
from models.episode import EpisodeProcessed, EpisodeResponse, EpisodeShipped, EpisodeStatus

HTTP_OK: int = 200


class DataCollectionRepo:
    """Repository for communicating with data-collection via HTTP."""

    def __init__(self, config: DataCollectionConfig) -> None:
        """Initialize the client with an optional DataCollectionConfig."""
        self.config: DataCollectionConfig = config
        self.base_url: str = self.config.url
        self.request_timeout: float = self.config.request_timeout

    def get_episodes(
        self,
        status: EpisodeStatus | None = None,
        processed: EpisodeProcessed | None = None,
        shipped: EpisodeShipped | None = None,
        limit: int = 10000,
        offset: int = 0,
    ) -> list[EpisodeResponse]:
        """Fetch episodes from data-collection, optionally filtered by `status` and/or `shipped`.

        Args:
            status: Optional episode status filter.
            processed: Optional processed status filter.
            shipped: Optional episode shipped status filter.
            limit: Max number of episodes to return.
            offset: Pagination offset.

        Returns:
            A list of episode dicts as returned by data-collection.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status is not None:
            params["status"] = status.value
        if processed is not None:
            params["processed"] = processed.value
        if shipped is not None:
            params["shipped"] = shipped.value

        url: str = f"{self.base_url}/api/v1/episodes"
        try:
            logger.debug("Requesting episodes from data-collection: {} params={}", url, params)
            resp: requests.Response = requests.get(url, params=params, timeout=self.request_timeout)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "items" in data:
                items: Iterable[Any] = data.get("items", [])
            elif isinstance(data, list):
                items = data
            else:
                items = []

            results: list[EpisodeResponse] = []
            for it in items:
                try:
                    results.append(EpisodeResponse.parse_obj(it))
                except Exception:
                    logger.warning("Skipping malformed episode payload from data-collection: {}", it)
            return results
        except requests.RequestException as e:
            logger.error("HTTP error fetching episodes from data-collection: {}", e)
            raise
        except Exception as e:
            logger.error("Unexpected error fetching episodes from data-collection: {}", e)
            raise

    def patch_episode(
        self,
        episode_id: UUID,
        processed: EpisodeProcessed | None = None,
        shipped: EpisodeShipped | None = None,
        message: str | None = None,
    ) -> EpisodeResponse:
        """Update episode shipping status and message via PATCH request.

        Args:
            episode_id: Episode UUID to update.
            processed: Optional processed status to set on the episode.
            shipped: New shipping status.
            message: New message content.

        Returns:
            Updated EpisodeResponse.

        Raises:
            requests.RequestException: On HTTP errors.
            ValueError: If neither shipped nor message is provided.
        """
        if processed is None and shipped is None and message is None:
            raise ValueError("At least one of processed, shipped or message must be provided")

        payload: dict[str, Any] = {}
        if processed is not None:
            payload["processed"] = processed.value
        if shipped is not None:
            payload["shipped"] = shipped.value
        if message is not None:
            payload["message"] = message

        url: str = f"{self.base_url}/api/v1/episodes/{episode_id}"
        try:
            logger.debug("Patching episode {}: {} to {}", episode_id, payload, url)
            resp: requests.Response = requests.patch(url, json=payload, timeout=self.request_timeout)
            resp.raise_for_status()
            data = resp.json()
            return EpisodeResponse.parse_obj(data)
        except requests.RequestException as e:
            logger.error("HTTP error patching episode {}: {}", episode_id, e)
            raise
        except Exception as e:
            logger.error("Unexpected error patching episode {}: {}", episode_id, e)
            raise

    def health_check(self) -> bool:
        """Perform a simple health check on the data-collection service.

        Returns:
            True if service is available, False otherwise.
        """
        url: str = f"{self.base_url}/healthz"
        try:
            logger.debug("Health check to data-collection: {}", url)
            resp: requests.Response = requests.get(url, timeout=self.request_timeout)
            return resp.status_code == HTTP_OK
        except requests.RequestException as e:
            logger.debug("Data-collection health check failed: {}", e)
            return False
        except Exception as e:
            logger.debug("Unexpected error during data-collection health check: {}", e)
            return False
