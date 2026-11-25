"""Fixtures shared by the annotator test modules."""

from pathlib import Path

import pytest
import requests

from configs.annotator import AnnotationConfig
from jobs import station_key


@pytest.fixture(autouse=True)
def no_live_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Tests must never call a live service")

    monkeypatch.setattr(requests.sessions.Session, "request", reject)


@pytest.fixture
def api_key() -> str:
    return "test-key-never-send"


@pytest.fixture
def config(tmp_path: Path, api_key: str) -> AnnotationConfig:
    """A station an operator has already connected from the episode page."""
    station_key.save(tmp_path / "annotations", api_key, "operator@lab.example")
    return AnnotationConfig(
        enabled=True,
        state_path=tmp_path / "annotations",
        processed_episodes_path=tmp_path / "processed",
        spec_path=tmp_path / "spec.json",
        timeout_seconds=1,
    )
