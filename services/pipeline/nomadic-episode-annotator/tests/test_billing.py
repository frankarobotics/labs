"""Nomadic declining work for billing reasons, and retrying without a second upload."""

import threading
from types import SimpleNamespace
from typing import ClassVar

import pytest
from test_annotations import (
    FakeGateway,
    saved_episode,
    started,
    wait_for_job,
)

from adapters.nomadic_gateway import billing_declined
from configs.annotator import AnnotationConfig
from jobs.ports import BillingDeclinedError, IndexResult
from jobs.service import AnnotationService


class CountingGateway(FakeGateway):
    """Uploads at once and counts remote calls; subclasses decide how Nomadic answers."""

    uploads: ClassVar[int] = 0
    indexes: ClassVar[int] = 0
    lock = threading.Lock()

    def upload(self, path: str) -> str:
        with self.lock:
            type(self).uploads += 1
        return "ingest-1"

    def start_index(self, video_id: str) -> IndexResult:
        with self.lock:
            type(self).indexes += 1
        return super().start_index(video_id)


@pytest.fixture(autouse=True)
def reset_counts() -> None:
    for gateway in (CountingGateway, NoCredits, UploadsDisabled, EarlyIngest, BrokenIndex):
        gateway.uploads = gateway.indexes = 0


class NoCredits(CountingGateway):
    """Declines the first annotation for credits, as Nomadic does before creating any analysis."""

    def start_index(self, video_id: str) -> IndexResult:
        if type(self).indexes == 0:
            type(self).indexes += 1
            raise BillingDeclinedError("out_of_credits", 0.05, 0.13)
        return super().start_index(video_id)


class UploadsDisabled(CountingGateway):
    def upload(self, path: str) -> str:
        raise BillingDeclinedError("uploads_not_enabled")


class EarlyIngest(CountingGateway):
    """The first ingest answer arrives before Nomadic has linked the primary view."""

    ingests: ClassVar[int] = 0

    def ingest(self, ingest_id: str) -> str:
        type(self).ingests += 1
        if type(self).ingests == 1:
            raise ValueError("Nomadic did not identify a primary camera view.")
        return super().ingest(ingest_id)


class BrokenIndex(CountingGateway):
    def start_index(self, video_id: str) -> IndexResult:
        raise ConnectionError("connection reset while indexing")


def test_402_answers_are_recognized_with_their_amounts() -> None:
    declined = billing_declined(
        SimpleNamespace(status_code=402, message="Insufficient credits. Available 0.05; required 0.13.")
    )
    assert declined and (declined.reason, declined.available, declined.required) == ("out_of_credits", 0.05, 0.13)
    upload = billing_declined(
        SimpleNamespace(status_code=402, message="Video upload is not available on the free trial.")
    )
    assert upload and upload.reason == "uploads_not_enabled"
    assert billing_declined(SimpleNamespace(status_code=402, message="Organisation credits exhausted")).reason == (
        "out_of_credits"
    )
    assert billing_declined(SimpleNamespace(status_code=500, message="Insufficient credits")) is None


def test_out_of_credits_keeps_the_upload_and_retries_only_the_annotation(config: AnnotationConfig) -> None:
    episode, _ = saved_episode(config)
    service = started(AnnotationService(config, NoCredits))
    try:
        service.submit(episode)
        job = wait_for_job(service, episode, "interrupted")
        assert job.billing == "out_of_credits"
        assert "needs 0.13 credits and the account has 0.05" in job.message and "already uploaded" in job.message
        status = service.status(episode)
        assert status.can_resume and not status.can_submit and status.billing_url
        service.refresh(episode)
        assert wait_for_job(service, episode, "completed").billing is None
        assert (NoCredits.uploads, NoCredits.indexes) == (1, 2)
    finally:
        service.close()


def test_uploads_not_enabled_sends_nothing_and_can_be_submitted_again(config: AnnotationConfig) -> None:
    episode, _ = saved_episode(config)
    service = started(AnnotationService(config, UploadsDisabled))
    try:
        service.submit(episode)
        job = wait_for_job(service, episode, "failed")
        assert job.billing == "uploads_not_enabled" and not job.remote_started
        assert "Enable uploads in Nomadic billing" in job.message
        status = service.status(episode)
        assert status.can_submit and not status.can_resume
    finally:
        service.close()


def test_a_saved_upload_resumes_from_the_ingest_wait(config: AnnotationConfig) -> None:
    episode, _ = saved_episode(config)
    service = started(AnnotationService(config, EarlyIngest))
    try:
        service.submit(episode)
        job = wait_for_job(service, episode, "interrupted")
        assert job.ingest_id and not job.video_id and service.status(episode).can_resume
        service.refresh(episode)
        wait_for_job(service, episode, "completed")
        assert (EarlyIngest.uploads, EarlyIngest.indexes) == (1, 1)
    finally:
        service.close()


def test_an_annotation_whose_start_was_not_confirmed_can_be_started_again(config: AnnotationConfig) -> None:
    episode, _ = saved_episode(config)
    service = started(AnnotationService(config, BrokenIndex))
    try:
        service.submit(episode)
        job = wait_for_job(service, episode, "interrupted")
        assert job.video_id and not job.index_run_id and job.billing is None
        assert "Check Nomadic Workbench" in job.message
        status = service.status(episode)
        assert status.can_submit and not status.can_resume
    finally:
        service.close()
