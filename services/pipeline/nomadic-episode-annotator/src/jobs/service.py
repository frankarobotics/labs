"""Bounded background annotation jobs with explicit interruption semantics."""

import fcntl
import logging
import queue
import threading
from contextlib import suppress
from pathlib import Path
from typing import IO
from uuid import UUID, uuid4

from configs.annotator import AnnotationConfig
from jobs import station_key
from jobs.episodes import recording_path
from jobs.models import ACTIVE_STATES, AnnotationJob, AnnotationStatus, StationAccount, StationSetup
from jobs.ports import (
    AnnotationGateway,
    BillingDeclinedError,
    GatewayFactory,
    IndexResult,
    InvalidApiKeyError,
    KeyVerifier,
    RemoteFailedError,
)
from jobs.store import JobStore, JobStoreError
from jobs.workbench import api_keys_url, billing_url, signup_url, workbench_url
from recording_conversion.preparation import RecordingPreparer

logger = logging.getLogger(__name__)


def _billing_message(exc: BillingDeclinedError, *, uploaded: bool) -> str:
    if exc.reason == "uploads_not_enabled":
        return "Nothing was sent. Enable uploads in Nomadic billing, then start the annotation again."
    amounts = (
        f"This recording needs {exc.required:.2f} credits and the account has {exc.available:.2f}. "
        if exc.available is not None and exc.required is not None
        else ""
    )
    if uploaded:
        return f"{amounts}Nothing was charged. Top up, then retry; the recording is already uploaded."
    return f"{amounts}Nothing was sent or charged. Top up, then start the annotation again."


_ALREADY_CONNECTED = (
    "This station is already connected to Nomadic. An administrator can remove the station's key file to disconnect it."
)


class AnnotationConflictError(Exception):
    """A new request would duplicate remote work or exceed the worker's capacity."""


class AnnotationUnavailableError(Exception):
    """Local annotation storage is unavailable or cannot be read."""


class AnnotationService:
    """Serialize expensive preparation/upload jobs on one worker, off the request threads.

    Once a recording is uploaded, Nomadic does the remaining work; a follower thread waits for it so the worker can
    prepare and upload the next recording. At most max_pending_jobs uploads are in Nomadic's hands at once; the worker
    waits for a free slot before uploading another.
    """

    def __init__(
        self, config: AnnotationConfig, gateway_factory: GatewayFactory, key_verifier: KeyVerifier | None = None
    ) -> None:
        """Create a dormant service; disabled instances perform no filesystem or network work."""
        self.config = config
        self.gateway_factory = gateway_factory
        self.key_verifier = key_verifier
        # The key an operator connected from the episode page; the only source of the station's key.
        self._api_key = ""
        self.account: StationAccount | None = None
        self.store: JobStore | None = None
        self._lock_file: IO[str] | None = None
        self._guard = threading.Lock()
        self._queue: queue.Queue[AnnotationJob | None] = queue.Queue(maxsize=config.max_pending_jobs)
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        # Uploaded recordings are processed by Nomadic; following them must not hold up the next upload.
        self._follow_slots = threading.BoundedSemaphore(config.max_pending_jobs)
        self._followers: set[threading.Thread] = set()
        self._load_station_key()

    def unavailable_reason(self) -> str | None:
        """Explain unavailable configuration without returning secrets or filesystem paths."""
        if not self.config.enabled:
            return "Nomadic annotations are not enabled for this station."
        if not self._api_key:
            return "This station is not connected to Nomadic."
        try:
            workbench_url(self.config.dashboard_url, "batch", "video")
        except ValueError as exc:
            return str(exc)
        return None

    def _setup(self) -> StationSetup | None:
        """Offer account links only when an enabled station is missing just its API key."""
        if not self.config.enabled or self._api_key:
            return None
        try:
            return StationSetup(
                signup_url=signup_url(self.config.dashboard_url),
                api_keys_url=api_keys_url(self.config.dashboard_url),
            )
        except ValueError:
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

    def connect(self, api_key: str) -> StationAccount:
        """Verify an operator's key with Nomadic, then save it and start the worker; only for unconnected stations.

        A station that already has a key keeps it. Replacing a key from the page would let anyone who can open the UI
        redirect the station's uploads to another account.
        """
        api_key = api_key.strip()
        if not self.config.enabled:
            raise AnnotationConflictError("Nomadic annotations are not enabled for this station.")
        if self._api_key:
            raise AnnotationConflictError(_ALREADY_CONNECTED)
        if not api_key:
            raise ValueError("Paste a Nomadic API key.")
        # Keys travel in an HTTP header; text copied from a page can carry characters no key has.
        if not api_key.isascii() or not api_key.isprintable() or " " in api_key:
            raise ValueError(
                "This is not a Nomadic API key: it contains spaces or special characters. Copy the key again and "
                "paste only the key."
            )
        if self.key_verifier is None:
            raise AnnotationUnavailableError("This annotator cannot check API keys.")
        try:
            check = self.key_verifier(self.config, api_key)
        except InvalidApiKeyError:
            raise ValueError(
                "Nomadic did not accept this API key. Check that it was copied completely and has not expired."
            ) from None
        except Exception as exc:
            # SDK exceptions may contain request details. Do not chain or log them.
            logger.warning("Could not verify a Nomadic API key (%s)", type(exc).__name__)
            raise AnnotationUnavailableError(
                "Nomadic could not be reached to check the key. Check the station's internet connection and try again."
            ) from None
        return self._save_and_start(api_key, check.email)

    def _save_and_start(self, api_key: str, email: str | None) -> StationAccount:
        """Save a verified key and start the worker, leaving the station unconnected if the worker cannot start."""
        with self._guard:
            if self._api_key:
                raise AnnotationConflictError(_ALREADY_CONNECTED)
            try:
                station_key.save(self.config.state_path, api_key, email)
            except OSError as exc:
                raise AnnotationUnavailableError(
                    "The key could not be saved. Check the station's data directory."
                ) from exc
            self._api_key = api_key
            self.account = StationAccount(email=email)
        try:
            self.start()
        except Exception:
            # Leave the station unconnected, so the operator can connect again once the cause is fixed.
            with self._guard:
                self._api_key = ""
                self.account = None
                with suppress(OSError):
                    station_key.remove(self.config.state_path)
            raise
        return self.account

    def _load_station_key(self) -> None:
        """Use the key an operator connected from the episode page, if there is one."""
        if not self.config.enabled:
            return
        try:
            saved = station_key.load(self.config.state_path)
        except (OSError, ValueError, KeyError):
            logger.warning("The saved Nomadic API key could not be read; the station needs to be connected again")
            return
        if saved:
            self._api_key, email = saved
            self.account = StationAccount(email=email)

    def _billing_url(self) -> str | None:
        try:
            return billing_url(self.config.dashboard_url)
        except ValueError:
            return None

    def _running_store(self) -> JobStore:
        if self.store is None:
            raise AnnotationUnavailableError("The annotation worker is not running. Check the annotator's logs.")
        return self.store

    def status(self, episode_id: UUID) -> AnnotationStatus:
        """Read the latest persisted result without side effects."""
        reason = self.unavailable_reason()
        if reason:
            return AnnotationStatus(enabled=self.config.enabled, message=reason, setup=self._setup())
        job = self._running_store().latest(episode_id)
        status = AnnotationStatus(
            enabled=True,
            message="",
            job=job,
            account=self.account,
            can_resume=bool(job and self._resumable(job)),
            billing_url=self._billing_url(),
        )
        if job and job.video_id:
            job.viewer_url = workbench_url(self.config.dashboard_url, job.batch_id, job.video_id)
        if job and job.remote_started and not self._restartable(job):
            return status
        if job and (job.state in ACTIVE_STATES or job.state == "completed"):
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
        with self._guard:
            store = self._running_store()
            if self._stop.is_set():
                raise AnnotationConflictError("The annotation worker is stopping.")
            previous = store.latest(episode_id)
            if previous and previous.state in ACTIVE_STATES:
                return previous
            if previous and (
                previous.state == "completed" or (previous.remote_started and not self._restartable(previous))
            ):
                raise AnnotationConflictError(
                    "This episode already has remote work. Continue it or inspect its saved result instead."
                )
            if self._queue.full():
                raise AnnotationConflictError("The annotation queue is full. Try again after the current jobs finish.")
            self._source(episode_id)
            job = AnnotationJob(job_id=uuid4(), episode_id=episode_id)
            store.save(job)
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
        """Continue known remote work from where it stopped, never uploading the recording again."""
        if reason := self.unavailable_reason():
            raise AnnotationConflictError(reason)
        with self._guard:
            job = self._running_store().latest(episode_id)
            if job and (job.state in ACTIVE_STATES or job.state == "completed"):
                return job
            if not job or not self._resumable(job):
                raise AnnotationConflictError("No remote analysis reference is available to refresh.")
            if self._queue.full() or self._stop.is_set():
                raise AnnotationConflictError("The annotation worker is busy or stopping.")
            job.state, job.message, job.billing = "queued", "Waiting to continue with the saved upload.", None
            self._save(job)
            self._queue.put_nowait(job)
            return job

    @staticmethod
    def _resumable(job: AnnotationJob) -> bool:
        """Whether continuing can pick up the saved remote work without starting a second analysis.

        A saved analysis or batch is only fetched, and a saved annotation run or upload is waited on again. A recording
        is indexed again only when Nomadic declined the first request for credits, so no analysis exists.
        """
        if job.state != "interrupted" or not job.remote_started:
            return False
        if job.analysis_id or job.batch_id or job.index_run_id:
            return bool(job.video_id)
        if job.ingest_id and not job.video_id:
            return True
        return bool(job.video_id) and job.billing == "out_of_credits"

    @classmethod
    def _restartable(cls, job: AnnotationJob) -> bool:
        """Whether the episode may be submitted again: nothing is left to continue, so every stop has a way out.

        This holds when the job failed, including when Nomadic reported that its processing or annotation failed, and
        when an interrupted job has no saved reference to continue, such as an upload or an annotation start whose
        answer was lost. Starting again uploads the recording again.
        """
        return job.state == "failed" or (job.state == "interrupted" and not cls._resumable(job))

    def _fetch(self, job: AnnotationJob, gateway: AnnotationGateway) -> None:
        if job.video_id is None:
            raise ValueError("The Nomadic video identifier is missing.")
        job.viewer_url = workbench_url(self.config.dashboard_url, job.batch_id, job.video_id)
        job.state, job.message = "fetching", "Loading action annotations."
        self._save(job)
        if not job.analysis_id and job.batch_id:
            job.analysis_id = gateway.analysis_id(job.batch_id, job.video_id)
            self._save(job)
        if not job.analysis_id:
            raise ValueError("The remote analysis has not been created yet.")
        job.events = gateway.events(job.video_id, job.analysis_id)
        job.state, job.message = "completed", f"{len(job.events)} action windows available."
        self._save(job)

    def _run(self, job: AnnotationJob) -> None:
        """Prepare and upload on the worker, then let a follower wait for Nomadic so the next upload can start."""
        gateway = None
        reserved = False
        stage = "preparing"
        prepared = self.config.state_path / "prepared" / f"{job.job_id}.mcap"
        try:
            if job.remote_started and (job.analysis_id or job.batch_id):
                stage = "fetching"
                gateway = self.gateway_factory(self.config, self._api_key)
                self._fetch(job, gateway)
                return
            if job.remote_started:
                # Continue the saved upload: wait for its processing or annotation run again, or annotate it after a
                # credit refusal.
                job.state = "ingesting" if job.video_id is None else "indexing"
                stage = job.state
                self._reserve_follower()
                reserved = True
                gateway = self.gateway_factory(self.config, self._api_key)
                job.message = (
                    "Nomadic is processing the recording." if stage == "ingesting" else "Analyzing robotic actions."
                )
                self._save(job)
                self._hand_off(job, gateway)
                gateway, reserved = None, False
                return
            job.state, job.message = "preparing", "Preparing cameras and robot signals."
            self._save(job)
            source = self._source(job.episode_id)
            job.source_sha256, job.warnings = RecordingPreparer(
                self.config.spec_path, self.config.policy_contract_path
            ).prepare(source, prepared, job.episode_id)
            self._reserve_follower()
            reserved = True
            stage = "connecting"
            gateway = self.gateway_factory(self.config, self._api_key)
            stage = "uploading"
            job.state, job.message, job.remote_started = "uploading", "Uploading recording to Nomadic.", True
            self._save(job)
            job.ingest_id = gateway.upload(str(prepared))
            job.state, job.message = "ingesting", "Nomadic is processing the recording."
            stage = "ingesting"
            self._save(job)
            self._hand_off(job, gateway)
            gateway, reserved = None, False
        except Exception as exc:
            self._fail(job, stage, exc)
        finally:
            self._close(job, gateway)
            if reserved:
                self._follow_slots.release()
            with suppress(OSError):
                prepared.unlink(missing_ok=True)

    def _reserve_follower(self) -> None:
        """Wait before uploading while max_pending_jobs uploads are still being processed by Nomadic."""
        while not self._follow_slots.acquire(timeout=1):
            if self._stop.is_set():
                raise InterruptedError("Worker is stopping.")

    def _hand_off(self, job: AnnotationJob, gateway: AnnotationGateway) -> None:
        """Follow an uploaded recording on its own thread, using the slot reserved before the upload."""
        follower = threading.Thread(
            target=self._follow, args=(job, gateway), name=f"nomadic-follow-{job.job_id}", daemon=True
        )
        with self._guard:
            self._followers.add(follower)
        follower.start()

    def _follow(self, job: AnnotationJob, gateway: AnnotationGateway) -> None:
        """Wait for Nomadic to ingest, annotate and return the uploaded recording."""
        stage = "ingesting"
        try:
            if job.video_id is None:
                job.video_id = gateway.ingest(job.ingest_id or "")
            job.state, job.message = "indexing", "Analyzing robotic actions."
            stage = "indexing"
            self._save(job)
            self._index(job, gateway)
            stage = "fetching"
            self._fetch(job, gateway)
        except Exception as exc:
            self._fail(job, stage, exc)
        finally:
            self._close(job, gateway)
            with self._guard:
                self._followers.discard(threading.current_thread())
            self._follow_slots.release()

    def _fail(self, job: AnnotationJob, stage: str, exc: Exception) -> None:
        if isinstance(exc, BillingDeclinedError):
            job.billing = exc.reason
            if stage == "uploading":
                # Nomadic refused the upload, so nothing was sent and the episode can be submitted again.
                job.remote_started = False
        # Nomadic reporting a failure ends the remote work, so the episode can be started again.
        job.state = "interrupted" if job.remote_started and not isinstance(exc, RemoteFailedError) else "failed"
        if stage == "indexing" and not job.index_run_id and not isinstance(exc, BillingDeclinedError):
            stage = "starting"
        # SDK exceptions may contain request details. Do not persist or log them.
        job.message = self._failure_message(stage, exc)
        logger.warning("Annotation job %s stopped during processing (%s)", job.job_id, type(exc).__name__)
        if self.store:
            try:
                self.store.save(job)
            except JobStoreError:
                logger.error("Annotation job %s could not be saved after it stopped", job.job_id)

    @staticmethod
    def _close(job: AnnotationJob, gateway: AnnotationGateway | None) -> None:
        if gateway:
            try:
                gateway.close()
            except Exception:
                logger.warning("Could not close the Nomadic session for job %s", job.job_id)

    def _index(self, job: AnnotationJob, gateway: AnnotationGateway) -> None:
        """Save the run reference as soon as indexing starts, then wait for that run, never starting a second one."""
        if job.video_id is None:
            raise ValueError("The Nomadic video identifier is missing.")
        if job.index_run_id is None:
            result = gateway.start_index(job.video_id)
            self._keep_index_references(job, result)
            if not result.completed:
                if job.index_run_id is None:
                    raise ValueError("Nomadic did not return a reference for the annotation run.")
                result = gateway.wait_index(job.video_id, job.index_run_id)
        else:
            result = gateway.wait_index(job.video_id, job.index_run_id)
        self._keep_index_references(job, result)
        if not result.completed:
            raise ValueError("Indexing has not completed.")
        if result.has_warnings:
            job.warnings.append("Some supporting evidence was unavailable; review the Nomadic analysis.")

    def _keep_index_references(self, job: AnnotationJob, result: IndexResult) -> None:
        job.batch_id = result.batch_id or job.batch_id
        job.index_run_id = result.run_id or job.index_run_id
        job.analysis_id = result.analysis_id or job.analysis_id
        job.video_id = result.video_id or job.video_id
        self._save(job)

    def _failure_message(self, stage: str, exc: Exception) -> str:
        """Give an actionable stage-specific message without exposing SDK request details."""
        if isinstance(exc, BillingDeclinedError):
            return _billing_message(exc, uploaded=stage != "uploading")
        if isinstance(exc, RemoteFailedError):
            return f"{exc} Start the annotation again."
        if stage == "preparing" and isinstance(exc, FileNotFoundError | ValueError):
            message = str(exc)
            return message.replace(self._api_key, "[redacted]") if self._api_key else message
        messages = {
            "preparing": (
                "The recording could not be prepared. Check the processed MCAP and station mapping, then retry."
            ),
            "connecting": (
                "Nomadic could not be initialized. Check the installed SDK and station settings, then retry. "
                "Nothing was uploaded."
            ),
            "uploading": (
                "The upload could not be confirmed. Check the station's connection, then start the annotation again."
            ),
            "ingesting": (
                "Nomadic did not confirm that it processed the recording. Continue with the saved upload to wait "
                "for it again, or start the annotation again."
            ),
            "starting": (
                "Nomadic did not confirm that the annotation started. Check Nomadic Workbench; if the recording "
                "has no analysis there, start the annotation again."
            ),
            "indexing": (
                "Nomadic did not confirm that the action annotations are complete. Continue to wait for the same "
                "annotation run; it is not started again."
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
        with self._guard:
            followers = list(self._followers)
        for follower in followers:
            follower.join(timeout=1)
        # The next start() marks unfinished jobs interrupted. Doing it here could overwrite references that a
        # follower still running its last SDK call saves after the join timeout.
        # A still-running SDK call retains the lock until process exit. A new
        # process must not claim ownership while this worker or a follower can still write.
        threads = [self._worker, *followers]
        if self._lock_file and not any(thread and thread.is_alive() for thread in threads):
            self._lock_file.close()
