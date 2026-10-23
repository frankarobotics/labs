"""Transactional job persistence separate from episode recording metadata."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from annotations.models import ACTIVE_STATES, AnnotationJob, now


class JobStoreError(Exception):
    """Annotation state could not be read or written."""


class JobStore:
    """Persist annotation attempts and retrieve the latest attempt per episode."""

    def __init__(self, root: Path) -> None:
        """Create the annotation database and episode lookup index."""
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "jobs.sqlite3"
        with self.connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, episode TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            connection.execute("CREATE INDEX IF NOT EXISTS jobs_episode ON jobs(episode)")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Open a short-lived connection safe to use from request and worker threads."""
        connection = None
        try:
            connection = sqlite3.connect(self.path, timeout=10)
            with connection:
                yield connection
        except sqlite3.Error as exc:
            raise JobStoreError(
                "Annotation storage is unavailable. Ask the station administrator to check it."
            ) from exc
        finally:
            if connection:
                connection.close()

    def latest(self, episode_id: UUID) -> AnnotationJob | None:
        """Return the latest attempt for an episode."""
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM jobs WHERE episode = ? ORDER BY rowid DESC LIMIT 1", (str(episode_id),)
            ).fetchone()
        try:
            return AnnotationJob.model_validate_json(row[0]) if row else None
        except ValueError as exc:
            raise JobStoreError(
                "The saved annotation record could not be read. Ask the station administrator to check it."
            ) from exc

    def save(self, job: AnnotationJob) -> None:
        """Atomically write a job, retaining the identity and original insertion order."""
        job.updated_at = now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO jobs VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (str(job.job_id), str(job.episode_id), job.model_dump_json()),
            )

    def recover(self) -> None:
        """Fence old in-flight work after this process has acquired the worker lock."""
        with self.connect() as connection:
            rows = connection.execute("SELECT payload FROM jobs").fetchall()
        for row in rows:
            job = AnnotationJob.model_validate_json(row[0])
            if job.state in ACTIVE_STATES:
                job.state = "interrupted"
                job.message = (
                    "The annotation worker stopped. Remote work may still be running; inspect the saved identifiers "
                    "in Nomadic before starting another analysis."
                    if job.remote_started
                    else "Preparation was interrupted. The recording was not sent; it is safe to try again."
                )
                self.save(job)
