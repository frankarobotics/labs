from collections.abc import Iterator
from pathlib import Path

import pytest
import uuid7
from fastapi.testclient import TestClient

from configs.annotator import get_annotation_config
from jobs.service import AnnotationService, AnnotationUnavailableError, get_annotation_service
from main import app


@pytest.fixture
def station(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("NOMADIC_ENABLED", "true")
    monkeypatch.setenv("NOMADIC_API_KEY", "test-key-never-send")
    monkeypatch.setenv("NOMADIC_PROCESSED_EPISODES_PATH", str(tmp_path / "processed"))
    monkeypatch.setenv("NOMADIC_STATE_PATH", str(tmp_path / "state"))
    get_annotation_config.cache_clear()
    get_annotation_service.cache_clear()
    yield tmp_path / "state"
    get_annotation_config.cache_clear()
    get_annotation_service.cache_clear()


def test_lifespan_starts_the_worker_and_releases_it_on_shutdown(station: Path) -> None:
    with TestClient(app) as client:
        response = client.get(f"/api/v1/episodes/{uuid7.create()}/annotations")
        assert response.status_code == 200
        assert response.json()["enabled"] is True
    successor = AnnotationService(get_annotation_config())
    try:
        successor.start()
        assert successor.store is not None
    finally:
        successor.close()


def test_startup_fails_when_storage_is_unavailable(station: Path) -> None:
    station.write_text("not a directory")
    with pytest.raises(AnnotationUnavailableError), TestClient(app):
        pass


def test_disabled_station_serves_status_without_storage(station: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOMADIC_ENABLED", "false")
    get_annotation_config.cache_clear()
    with TestClient(app) as client:
        response = client.get(f"/api/v1/episodes/{uuid7.create()}/annotations")
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert not station.exists()
