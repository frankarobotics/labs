import uuid
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
import uuid7  # type: ignore[import-untyped]

from pipeline_episodes import episode_directory


def test_episode_lives_under_its_creation_date() -> None:
    episode_id = uuid7.create(datetime(2026, 3, 14, 9, 30, tzinfo=UTC))

    assert episode_directory(Path("/data"), episode_id) == Path(f"/data/2026/03/14/{episode_id}")


def test_creation_date_is_taken_in_utc_not_local_time() -> None:
    local_after_midnight = datetime(2026, 3, 1, 0, 30, tzinfo=timezone(timedelta(hours=2)))

    episode_id = uuid7.create(local_after_midnight)

    assert episode_directory(Path("/data"), episode_id).parent == Path("/data/2026/02/28")


def test_non_uuid7_identifier_is_rejected() -> None:
    with pytest.raises(ValueError, match="UUIDv7"):
        episode_directory(Path("/data"), uuid.uuid4())
