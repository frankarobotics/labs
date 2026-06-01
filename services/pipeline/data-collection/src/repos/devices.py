"""Repository for managing devices (DeviceDB)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from models.db import DeviceDB, DeviceStatusDB, DeviceTypeDB


class DeviceRepo:
    """Repository for CRUD operations on devices."""

    def __init__(self, db: Session) -> None:
        """Initialize the DeviceRepo with a SQLAlchemy session.

        Args:
            db: SQLAlchemy Session
        """
        self.db: Session = db

    def get_by_id(self, device_id: str) -> DeviceDB | None:
        """Get a device by id."""
        stmt: Select[tuple[DeviceDB]] = select(DeviceDB).where(DeviceDB.id == device_id)
        return self.db.scalar(stmt)

    def get_all(self, device_type: str | None = None, limit: int = 100, offset: int = 0) -> Sequence[DeviceDB]:
        """Get all devices with optional filters."""
        stmt: Select[tuple[DeviceDB]] = select(DeviceDB)
        if device_type:
            stmt = stmt.where(DeviceDB.type == device_type)
        # Ensure deterministic ordering (ascending id)
        stmt = stmt.order_by(DeviceDB.id.asc()).offset(offset).limit(limit)
        return self.db.scalars(stmt).all()

    def upsert(
        self, device_id: str, device_type: str | DeviceTypeDB, status: str | DeviceStatusDB, config: dict[str, Any]
    ) -> DeviceDB:
        """Create or update a device record."""
        device: DeviceDB | None = self.get_by_id(device_id)
        if not device:
            device = DeviceDB(id=device_id)
            self.db.add(device)

        device.type = DeviceTypeDB(device_type)
        device.status = DeviceStatusDB(status)
        device.config = config
        device.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(device)
        return device

    def delete_all(self) -> None:
        """Hard delete all devices (remove rows)."""
        stmt: Select[tuple[DeviceDB]] = select(DeviceDB)
        all_devices: Sequence[DeviceDB] = self.db.scalars(stmt).all()
        for d in all_devices:
            logger.debug(f"Deleting device {d.id}")
            self.db.delete(d)
        self.db.commit()
