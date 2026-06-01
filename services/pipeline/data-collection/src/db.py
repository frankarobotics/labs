"""SQLAlchemy engine and session management for FastAPI."""

from __future__ import annotations

import time
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from configs.data_collection import load_data_collection_config

DATABASE_URL: str = load_data_collection_config().database_url

engine: Engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal: sessionmaker[Session] = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, class_=Session, future=True
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a SQLAlchemy session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def wait_for_db(timeout_sec: float = 60.0, interval_sec: float = 0.5) -> None:
    """Block until the database is accepting connections or timeout.

    Tries to open a connection using the SQLAlchemy engine. Raises a RuntimeError when the timeout is exceeded.
    """
    deadline: datetime = datetime.now(UTC) + timedelta(seconds=timeout_sec)
    last_err: Exception | None = None
    while datetime.now(UTC) < deadline:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                time.sleep(1)  # give some time for the DB (and tables) to fully come up
            return
        except Exception as e:
            last_err = e
            time.sleep(interval_sec)
    raise RuntimeError(f"Database not available after {timeout_sec}s: {last_err}")
