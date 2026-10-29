import json

import pytest
from pydantic import ValidationError

from pipeline_episodes import (
    DeviceInfo,
    DeviceStatus,
    DeviceType,
    EpisodeLabel,
    EpisodeMetadata,
    EpisodeProcessed,
    EpisodeStatus,
)

# Shape of an episode_metadata.json as data-collection writes it today
ON_DISK = {
    "episode_id": "019a2a6e-1c3b-7c4d-8e5f-0a1b2c3d4e5f",
    "status": "SAVED",
    "label": "REVIEW_SUCCESS",
    "processed": "SUCCESS",
    "message": "",
    "tags": ["pick"],
    "created_at": "2026-10-28T10:00:00+00:00",
    "updated_at": "2026-10-28T10:05:00+00:00",
    "task_id": "019a2a6e-0000-7000-8000-000000000001",
    "task_name": "pick cube",
    "task_description": "Pick the red cube",
    "task_version": None,
    "task_language_instructions": ["pick up the red cube"],
    "task_metadata": {"difficulty": 2},
    "station_id": "fr3-duo-01",
    "devices": [
        {
            "device_id": "head_camera",
            "device_type": "ZED_CAMERA",
            "device_status": "ONLINE",
            "device_config": {"fps": 30},
        }
    ],
}


def test_metadata_file_parses_into_typed_fields() -> None:
    metadata = EpisodeMetadata.model_validate_json(json.dumps(ON_DISK))

    assert metadata.status is EpisodeStatus.SAVED
    assert metadata.label is EpisodeLabel.REVIEW_SUCCESS
    assert metadata.processed is EpisodeProcessed.SUCCESS
    assert metadata.devices == [
        DeviceInfo(
            device_id="head_camera",
            device_type=DeviceType.ZED_CAMERA,
            device_status=DeviceStatus.ONLINE,
            device_config={"fps": 30},
        )
    ]


def test_metadata_round_trips_to_the_same_json() -> None:
    metadata = EpisodeMetadata.model_validate(ON_DISK)

    assert json.loads(metadata.model_dump_json()) == ON_DISK


def test_unknown_status_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EpisodeMetadata.model_validate({**ON_DISK, "status": "ARCHIVED"})
