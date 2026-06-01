"""SQLAlchemy models for the database schema."""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import uuid7  # type: ignore[import-untyped]
from sqlalchemy import JSON, DateTime, Enum, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Type-safe declarative base for SQLAlchemy models."""

    pass


class EpisodeStatusDB(str, enum.Enum):
    """Enum for episode status."""

    INIT = "INIT"
    RECORDING = "RECORDING"
    RECORDED = "RECORDED"
    SAVED = "SAVED"
    DISCARDED = "DISCARDED"
    ERROR = "ERROR"


class EpisodeLabelDB(str, enum.Enum):
    """Enum for episode label."""

    REVIEW_SUCCESS = "REVIEW_SUCCESS"
    REVIEW_FAILED = "REVIEW_FAILED"


class EpisodeProcessedDB(str, enum.Enum):
    """Enum for episode processed status."""

    DEFAULT = "DEFAULT"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class EpisodeShippedDB(str, enum.Enum):
    """Enum for episode shipped status."""

    DEFAULT = "DEFAULT"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class DeviceTypeDB(str, enum.Enum):
    """Enum for device type."""

    TELEOP_ROBOT = "TELEOP_ROBOT"
    REALSENSE_CAMERA = "REALSENSE_CAMERA"
    ZED_CAMERA = "ZED_CAMERA"
    ROBOT_OBSERVER = "ROBOT_OBSERVER"


class DeviceStatusDB(str, enum.Enum):
    """Enum for device status."""

    UNKNOWN = "UNKNOWN"
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    ERROR = "ERROR"


class DeviceDB(Base):
    """SQLAlchemy model for the 'devices' table."""

    __tablename__: str = "devices"

    id: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    type: Mapped[DeviceTypeDB] = mapped_column(Enum(DeviceTypeDB, name="DEVICE_TYPE", native_enum=True), nullable=False)
    status: Mapped[DeviceStatusDB] = mapped_column(
        Enum(DeviceStatusDB, name="DEVICE_STATUS", native_enum=True), nullable=False, default=DeviceStatusDB.UNKNOWN
    )
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class EpisodeDB(Base):
    """SQLAlchemy model for the 'episodes' table."""

    __tablename__: str = "episodes"
    __table_args__: tuple[Index, Index, Index, Index, Index, Index] = (
        Index("idx_episodes_task_id", "task_id"),
        Index("idx_episodes_station_id", "station_id"),
        Index("idx_episodes_status", "status"),
        Index("idx_episodes_label", "label"),
        Index("idx_episodes_processed", "processed"),
        Index("idx_episodes_shipped", "shipped"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    # Task ID references a task from YAML configuration (see configs.tasks.Task)
    task_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    station_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[EpisodeStatusDB] = mapped_column(
        Enum(EpisodeStatusDB, name="EPISODE_STATUS", native_enum=True), nullable=False
    )
    label: Mapped[EpisodeLabelDB | None] = mapped_column(
        Enum(EpisodeLabelDB, name="EPISODE_LABEL", native_enum=True), nullable=True
    )
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    shipped: Mapped[EpisodeShippedDB] = mapped_column(
        Enum(EpisodeShippedDB, name="EPISODE_SHIPPED", native_enum=True),
        nullable=False,
        default=EpisodeShippedDB.DEFAULT,
    )
    processed: Mapped[EpisodeProcessedDB] = mapped_column(
        Enum(EpisodeProcessedDB, name="EPISODE_PROCESSED", native_enum=True),
        nullable=False,
        default=EpisodeProcessedDB.DEFAULT,
    )
    object_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
