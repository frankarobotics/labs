"""Bounded background annotation jobs with explicit interruption semantics."""

import fcntl
import importlib.util
import logging
import queue
import threading
from collections.abc import Callable
from contextlib import suppress
from functools import lru_cache
from pathlib import Path
from typing import IO
from uuid import UUID, uuid4

from annotations.config import AnnotationConfig, get_annotation_config
from annotations.episodes import recording_path
from annotations.models import ACTIVE_STATES, AnnotationJob, AnnotationStatus
from annotations.nomadic_client import NomadicGateway, annotation_events, primary_video, workbench_url
from annotations.store import JobStore, JobStoreError

logger = logging.getLogger(__name__)


class AnnotationConflictError(Exception):
    """A new request would duplicate remote work or exceed the worker's capacity."""


class AnnotationUnavailableError(Exception):
    """Local annotation storage is unavailable or cannot be read."""


class AnnotationService:
    """Serialize expensive preparation/upload jobs independently of ROS requests."""

    def __init__(
        self, config: AnnotationConfig, gateway_factory: Callable[[AnnotationConfig], NomadicGateway] = NomadicGateway
    ) -> None:
        """Create a dormant service; disabled instances perform no filesystem or network work."""
        self.config = config
        self.gateway_factory = gateway_factory
        self.store: JobStore | None = None
        self._lock_file: IO[str] | None = None
        self._guard = threading.Lock()
        self._queue: queue.Queue[AnnotationJob | None] = queue.Queue(maxsize=config.max_pending_jobs)
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None

    def unavailable_reason(self) -> str | None:
        """Explain unavailable configuration without returning secrets or filesystem paths."""
        if not self.config.enabled:
            return "Nomadic annotations are not enabled for this station."
        if not self.config.api_key.get_secret_value():
            return "The station's Nomadic API key is not configured."
        if any(importlib.util.find_spec(name) is None for name in ("nomadic", "av", "mcap_protobuf")):
            return "Install the Nomadic integration dependencies on the data-collection service."
        try:
            workbench_url(self.config.dashboard_url, "batch", "video")
        except ValueError as exc:
            return str(exc)
        return None

    def start(self) -> None:
        """Acquire single-worker ownership and recover interrupted local jobs."""
        with self._guard:
            if self.store or self.unavailable_reason():
                return
            try:
                self.config.state_path.mkdir(parents=True, exist_ok=True)
                lock = (self.config.state_path / "worker.lock").open("a")
            except OSError as exc:
                raise AnnotationUnavailableError(
                    "Annotation storage is unavailable. Check the station's data directory."
                ) from exc
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lock.close()
                raise AnnotationConflictError("Another annotation worker owns this storage directory.") from None
            try:
                store = JobStore(self.config.state_path)
                store.recover()
            except (OSError, JobStoreError, ValueError) as exc:
                lock.close()
                raise AnnotationUnavailableError(
                    "Annotation storage could not be loaded. Ask the station administrator to check it."
                ) from exc
            self._lock_file, self.store = lock, store
            self._worker = threading.Thread(target=self._work, name="nomadic-annotations", daemon=True)
            self._worker.start()

    def status(self, episode_id: UUID) -> AnnotationStatus:
        """Read the latest persisted result, starting the worker only when enabled."""
        reason = self.unavailable_reason()
        if reason:
            return AnnotationStatus(enabled=self.config.enabled, message=reason)
        self.start()
        job = self.store.latest(episode_id) if self.store else None
        status = AnnotationStatus(enabled=True, message="", job=job)
        if job and job.video_id:
            job.viewer_url = workbench_url(self.config.dashboard_url, job.batch_id, job.video_id)
        if job and (job.state in ACTIVE_STATES or job.remote_started or job.state == "completed"):
            return status
        try:
            self._source(episode_id)
        except (FileNotFoundError, ValueError, OSError) as exc:
            status.message = self._failure_message("preparing", exc)
            return status
        status.can_submit = True
        return status

    def submit(self, episode_id: UUID) -> AnnotationJob:
        """Queue one explicitly requested upload, never automatically retrying remote work."""
        if reason := self.unavailable_reason():
            raise ValueError(reason)
        self.start()
        with self._guard:
            if self.store is None or self._stop.is_set():
                raise AnnotationConflictError("The annotation worker is stopping.")
            previous = self.store.latest(episode_id)
            if previous and previous.state in ACTIVE_STATES:
                return previous
            if previous and (previous.remote_started or previous.state == "completed"):
                raise AnnotationConflictError(
                    "This episode already has remote work. Inspect its saved result before resubmitting."
                )
            if self._queue.full():
                raise AnnotationConflictError("The annotation queue is full. Try again after the current jobs finish.")
            self._source(episode_id)
            job = AnnotationJob(job_id=uuid4(), episode_id=episode_id)
            self.store.save(job)
            self._queue.put_nowait(job)
            return job

    def _save(self, job: AnnotationJob) -> None:
        if self._stop.is_set():
            raise InterruptedError("Worker is stopping.")
        if self.store:
            self.store.save(job)

    def _source(self, episode_id: UUID) -> Path:
        """Check submission-only requirements without restricting saved results."""
        if self.config.spec_path and not self.config.spec_path.is_file():
            raise ValueError("The Nomadic recording mapping is unavailable. Check NOMADIC_SPEC_PATH on the station.")
        return recording_path(self.config, episode_id)

    def refresh(self, episode_id: UUID) -> AnnotationJob:
        """Retry retrieval of known remote work, without another upload or analysis."""
        if reason := self.unavailable_reason():
            raise AnnotationConflictError(reason)
        self.start()
        with self._guard:
            job = self.store.latest(episode_id) if self.store else None
            if not job or not job.video_id or not (job.analysis_id or job.batch_id):
                raise AnnotationConflictError("No remote analysis reference is available to refresh.")
            if job.state in ACTIVE_STATES or job.state == "completed":
                return job
            if self._queue.full() or self._stop.is_set():
                raise AnnotationConflictError("The annotation worker is busy or stopping.")
            job.state, job.message = "queued", "Waiting to refresh the saved Nomadic result."
            self._save(job)
            self._queue.put_nowait(job)
            return job

    def _fetch(self, job: AnnotationJob, gateway: NomadicGateway) -> None:
        if job.video_id is None:
            raise ValueError("The Nomadic video identifier is missing.")
        job.viewer_url = workbench_url(self.config.dashboard_url, job.batch_id, job.video_id)
        job.state, job.message = "fetching", "Loading action annotations."
        self._save(job)
        if not job.analysis_id and job.batch_id:
            batch = gateway.batch(job.batch_id)
            job.analysis_id = next(
                (row.get("analysis_id") for row in batch.get("results", []) if row.get("video_id") == job.video_id),
                None,
            )
            self._save(job)
        if not job.analysis_id:
            raise ValueError("The remote analysis has not been created yet.")
        job.events = annotation_events(gateway.analysis(job.video_id, job.analysis_id), job.analysis_id)
        job.state, job.message = "completed", f"{len(job.events)} action windows available."
        self._save(job)

    def _run(self, job: AnnotationJob) -> None:
        gateway = None
        stage = "preparing"
        prepared = self.config.state_path / "prepared" / f"{job.job_id}.mcap"
        try:
            if job.remote_started and (job.analysis_id or job.batch_id):
                stage = "fetching"
                gateway = self.gateway_factory(self.config)
                self._fetch(job, gateway)
                return
            from annotations.preparation import RecordingPreparer  # noqa: PLC0415 -- Optional dependencies stay lazy.

            job.state, job.message = "preparing", "Preparing cameras and robot signals."
            self._save(job)
            source = self._source(job.episode_id)
            job.source_sha256, job.warnings = RecordingPreparer(
                self.config.spec_path, self.config.policy_contract_path
            ).prepare(source, prepared, job.episode_id)
            stage = "connecting"
            gateway = self.gateway_factory(self.config)
            stage = "uploading"
            job.state, job.message, job.remote_started = "uploading", "Uploading recording to Nomadic.", True
            self._save(job)
            upload = gateway.upload(str(prepared))
            job.ingest_id = upload.get("mcap_ingest_id")
            if not job.ingest_id:
                raise ValueError("The SDK did not return an MCAP ingest identifier.")
            job.state, job.message = "ingesting", "Nomadic is processing the recording."
            stage = "ingesting"
            self._save(job)
            job.video_id = primary_video(gateway.ingest(job.ingest_id))
            job.state, job.message = "indexing", "Analyzing robotic actions."
            stage = "indexing"
            self._save(job)
            self._index(job, gateway)
            stage = "fetching"
            self._fetch(job, gateway)
        except Exception as exc:
            job.state = "interrupted" if job.remote_started else "failed"
            # SDK exceptions may contain request details. Do not persist or log them.
            job.message = self._failure_message(stage, exc)
            logger.warning("Annotation job %s stopped during processing (%s)", job.job_id, type(exc).__name__)
            if self.store:
                self.store.save(job)
        finally:
            if gateway:
                try:
                    gateway.close()
                except Exception:
                    logger.warning("Could not close the Nomadic session for job %s", job.job_id)
            with suppress(OSError):
                prepared.unlink(missing_ok=True)

    def _index(self, job: AnnotationJob, gateway: NomadicGateway) -> None:
        """Save returned references before checking whether indexing completed."""
        if job.video_id is None:
            raise ValueError("The Nomadic video identifier is missing.")
        result = gateway.index(job.video_id)
        job.batch_id = result.get("batch_id")
        job.index_run_id = result.get("run_id")
        job.analysis_id = result.get("analysis_id")
        job.video_id = result.get("index_video_id") or job.video_id
        self._save(job)
        if result.get("status") != "completed":
            raise ValueError("Indexing has not completed.")
        if result.get("warnings"):
            job.warnings.append("Some supporting evidence was unavailable; review the Nomadic analysis.")

    def _failure_message(self, stage: str, exc: Exception) -> str:
        """Give an actionable stage-specific message without exposing SDK request details."""
        if stage == "preparing" and isinstance(exc, FileNotFoundError | ValueError):
            message = str(exc)
            secret = self.config.api_key.get_secret_value()
            return message.replace(secret, "[redacted]") if secret else message
        messages = {
            "preparing": (
                "The recording could not be prepared. Check the processed MCAP and station mapping, then retry."
            ),
            "connecting": (
                "Nomadic could not be initialized. Check the installed SDK and station settings, then retry. "
                "Nothing was uploaded."
            ),
            "uploading": (
                "The upload could not be confirmed. Check the API key, connectivity and Nomadic workspace "
                "before another submission."
            ),
            "ingesting": (
                "Nomadic could not finish processing the recording. Check its saved upload reference "
                "before another submission."
            ),
            "indexing": (
                "Nomadic did not confirm that the action annotations are complete. "
                "Check Nomadic Workbench and the saved references before another submission."
            ),
            "fetching": (
                "The saved annotations could not be loaded. Use Refresh saved result to retry "
                "without uploading or analyzing again."
            ),
        }
        return messages[stage]

    def _work(self) -> None:
        while not self._stop.is_set():
            job = self._queue.get()
            try:
                if job is None or self._stop.is_set():
                    return
                self._run(job)
            except Exception as exc:
                logger.error(
                    "Annotation worker could not persist job %s (%s)",
                    job.job_id if job else "shutdown",
                    type(exc).__name__,
                )
            finally:
                self._queue.task_done()

    def close(self) -> None:
        """Stop accepting jobs and retain interrupted remote work without resubmitting it."""
        self._stop.set()
        with suppress(queue.Full):
            self._queue.put_nowait(None)
        if self._worker:
            self._worker.join(timeout=1)
        if self.store:
            with suppress(JobStoreError, ValueError):
                self.store.recover()
        # A still-running SDK call retains the lock until process exit. A new
        # process must not claim ownership while this worker can still write.
        if self._lock_file and (self._worker is None or not self._worker.is_alive()):
            self._lock_file.close()


@lru_cache
def get_annotation_service() -> AnnotationService:
    """Return this process's optional annotation worker."""
    return AnnotationService(get_annotation_config())
