"""Connecting a station to Nomadic from the episode page."""

import json
import stat
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
import uuid7
from fastapi import FastAPI
from fastapi.testclient import TestClient

from configs.annotator import AnnotationConfig
from dependencies import get_annotation_service
from handlers.station import router
from jobs.ports import AccountCheck, InvalidApiKeyError
from jobs.service import AnnotationConflictError, AnnotationService, AnnotationUnavailableError
from jobs.workbench import signup_url

KEY = "station-key-never-echo"


@pytest.fixture(autouse=True)
def no_live_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Tests must never call a live service")

    monkeypatch.setattr(requests.sessions.Session, "request", reject)


@pytest.fixture
def config(tmp_path: Path) -> AnnotationConfig:
    return AnnotationConfig(enabled=True, state_path=tmp_path / "annotations", processed_episodes_path=tmp_path)


def verifier(check: AccountCheck | Exception) -> Mock:
    return Mock(side_effect=check) if isinstance(check, Exception) else Mock(return_value=check)


@pytest.fixture
def services() -> Iterator[list[AnnotationService]]:
    created: list[AnnotationService] = []
    yield created
    for service in created:
        service.close()


def test_unconnected_station_offers_setup_links(config: AnnotationConfig) -> None:
    status = AnnotationService(config, Mock()).status(uuid7.create())
    assert not status.can_submit and status.setup is not None
    assert status.setup.signup_url == signup_url(config.dashboard_url)
    assert "partner=franka-labs" in status.setup.signup_url and "returnTo=%2Fprofile" in status.setup.signup_url


def test_connect_saves_the_key_privately_and_starts_the_worker(
    config: AnnotationConfig, services: list[AnnotationService]
) -> None:
    check = verifier(AccountCheck(email="operator@lab.example"))
    service = AnnotationService(config, Mock(), check)
    services.append(service)
    account = service.connect(f"  {KEY}\n")
    check.assert_called_once_with(config, KEY)
    saved = config.state_path / "station_key.json"
    assert stat.S_IMODE(saved.stat().st_mode) == 0o600
    assert json.loads(saved.read_text()) == {"api_key": KEY, "email": "operator@lab.example"}
    assert account.email == "operator@lab.example"
    assert service.store is not None
    status = service.status(uuid7.create())
    assert status.setup is None and status.account == account
    assert KEY not in status.model_dump_json()


def test_restart_reuses_the_saved_key(config: AnnotationConfig, services: list[AnnotationService]) -> None:
    first = AnnotationService(config, Mock(), verifier(AccountCheck(email="operator@lab.example")))
    first.connect(KEY)
    first.close()
    gateway_factory = Mock()
    restarted = AnnotationService(config, gateway_factory)
    services.append(restarted)
    restarted.start()
    status = restarted.status(uuid7.create())
    assert status.setup is None and status.account is not None and status.account.email == "operator@lab.example"
    assert restarted.store is not None


def test_rejected_key_is_not_saved(config: AnnotationConfig) -> None:
    service = AnnotationService(config, Mock(), verifier(InvalidApiKeyError("rejected")))
    with pytest.raises(ValueError, match="did not accept this API key"):
        service.connect(KEY)
    assert not (config.state_path / "station_key.json").exists()
    assert service.status(uuid7.create()).setup is not None


@pytest.mark.parametrize("pasted", [f"{KEY}\u200b", f"{KEY}…", f"{KEY[:6]} {KEY[6:]}"])
def test_pasted_text_that_cannot_be_a_key_is_not_sent(config: AnnotationConfig, pasted: str) -> None:
    check = verifier(AccountCheck(email="operator@example.com"))
    with pytest.raises(ValueError, match="not a Nomadic API key"):
        AnnotationService(config, Mock(), check).connect(pasted)
    check.assert_not_called()


def test_unreachable_nomadic_does_not_leak_the_key(config: AnnotationConfig) -> None:
    service = AnnotationService(config, Mock(), verifier(ConnectionError(f"POST /api/keys/verify X-API-Key: {KEY}")))
    with pytest.raises(AnnotationUnavailableError, match="could not be reached") as caught:
        service.connect(KEY)
    assert KEY not in str(caught.value) and caught.value.__cause__ is None
    assert not (config.state_path / "station_key.json").exists()


def test_key_is_forgotten_when_the_worker_cannot_start(
    config: AnnotationConfig, services: list[AnnotationService], monkeypatch: pytest.MonkeyPatch
) -> None:
    service = AnnotationService(config, Mock(), verifier(AccountCheck(email="operator@lab.example")))
    services.append(service)
    monkeypatch.setattr(service, "start", Mock(side_effect=AnnotationUnavailableError("storage")))
    with pytest.raises(AnnotationUnavailableError):
        service.connect(KEY)
    assert not (config.state_path / "station_key.json").exists()
    assert service.status(uuid7.create()).setup is not None and service.account is None
    monkeypatch.undo()
    assert service.connect(KEY).email == "operator@lab.example"


def test_connected_station_keeps_its_key(config: AnnotationConfig, services: list[AnnotationService]) -> None:
    first = AnnotationService(config, Mock(), verifier(AccountCheck(email="operator@lab.example")))
    services.append(first)
    first.connect(KEY)
    saved = (config.state_path / "station_key.json").read_text()
    check = verifier(AccountCheck(email="other@lab.example"))
    for service in (first, AnnotationService(config, Mock(), check)):
        with pytest.raises(AnnotationConflictError, match="already connected"):
            service.connect("another-key")
    check.assert_not_called()
    assert (config.state_path / "station_key.json").read_text() == saved


def test_a_key_in_the_environment_is_not_used(config: AnnotationConfig, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOMADIC_API_KEY", KEY)
    station = AnnotationConfig(enabled=True, state_path=config.state_path, processed_episodes_path=config.state_path)
    status = AnnotationService(station, Mock()).status(uuid7.create())
    assert not status.can_submit and status.setup is not None


def test_connect_endpoint_maps_outcomes_without_echoing_the_key(
    config: AnnotationConfig, services: list[AnnotationService]
) -> None:
    rejected = AnnotationService(config, Mock(), verifier(InvalidApiKeyError("rejected")))
    accepted = AnnotationService(config, Mock(), verifier(AccountCheck(email="operator@lab.example")))
    services.append(accepted)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        app.dependency_overrides[get_annotation_service] = lambda: rejected
        response = client.post("/api/v1/station/api-key", json={"api_key": KEY})
        assert response.status_code == 400 and KEY not in response.text
        app.dependency_overrides[get_annotation_service] = lambda: accepted
        response = client.post("/api/v1/station/api-key", json={"api_key": KEY})
        assert response.status_code == 200 and response.json()["email"] == "operator@lab.example"
        assert KEY not in response.text
        response = client.post("/api/v1/station/api-key", json={"api_key": "second-key"})
        assert response.status_code == 409
