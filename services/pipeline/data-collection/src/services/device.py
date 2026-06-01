from configs.data_collection import DataCollectionConfig
from models.db import DeviceDB
from models.device import DeviceResponse, DeviceStatus, DeviceType
from repos.devices import DeviceRepo


class DeviceService:
    """Service for managing and retrieving device information."""

    def __init__(self, repo: DeviceRepo, config: DataCollectionConfig) -> None:
        """Initialize the device service."""
        self.repo: DeviceRepo = repo
        self.config: DataCollectionConfig = config

    def get_devices(self, device_type: str | None = None) -> list[DeviceResponse]:
        """Return a list of devices for the configured project."""
        db_devices: list[DeviceDB] = list(self.repo.get_all())

        devices: list[DeviceResponse] = []
        for device in db_devices:
            devices.append(
                DeviceResponse(
                    id=device.id,
                    type=DeviceType(device.type.value),
                    status=DeviceStatus(device.status.value),
                    config=device.config,
                )
            )
        return devices

    def get_device_by_id(self, device_id: str) -> DeviceResponse | None:
        """Get a device by its ID."""
        device: DeviceDB | None = self.repo.get_by_id(device_id)
        if not device:
            return None

        return DeviceResponse(
            id=device.id,
            type=DeviceType(device.type.value),
            status=DeviceStatus(device.status.value),
            config=device.config,
        )
