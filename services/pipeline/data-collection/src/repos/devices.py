"""In-memory repository for devices, populated from station configuration."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from loguru import logger

from models.device import DeviceStatus, DeviceType


@dataclass
class DeviceRecord:
    """In-memory snapshot of a single device's runtime state.

    Updated in place as heartbeats and status changes arrive - not persisted to disk.
    """

    id: str
    type: DeviceType
    status: DeviceStatus
    config: dict[str, Any]
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_heartbeat: datetime | None = None


class DeviceRepo:
    """Thread-safe in-memory repository for device records."""

    def __init__(self) -> None:
        """Initialize with an empty device store."""
        self._devices: dict[str, DeviceRecord] = {}
        self._lock = threading.Lock()

    def get_all(self) -> list[DeviceRecord]:
        """Return all device records sorted by id."""
        with self._lock:
            return sorted(self._devices.values(), key=lambda d: d.id)

    def get_by_id(self, device_id: str) -> DeviceRecord | None:
        """Get a device record by id."""
        with self._lock:
            return self._devices.get(device_id)

    def upsert(
        self,
        device_id: str,
        device_type: str | DeviceType,
        status: str | DeviceStatus,
        config: dict[str, Any],
    ) -> DeviceRecord:
        """Create or update a device record in memory."""
        dtype = DeviceType(device_type) if isinstance(device_type, str) else device_type
        dstatus = DeviceStatus(status) if isinstance(status, str) else status
        with self._lock:
            if device_id in self._devices:
                rec = self._devices[device_id]
                rec.type = dtype
                rec.status = dstatus
                rec.config = config
                rec.updated_at = datetime.now(UTC)
            else:
                rec = DeviceRecord(id=device_id, type=dtype, status=dstatus, config=config)
                self._devices[device_id] = rec
                logger.debug(f"Added device {device_id} to in-memory store")
            return rec

    def delete_all(self) -> None:
        """Clear all device records from memory."""
        with self._lock:
            for device_id in list(self._devices):
                logger.debug(f"Removing device {device_id} from in-memory store")
            self._devices.clear()
