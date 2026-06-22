from configs.data_collection import DataCollectionConfig
from models.device import DeviceResponse, DeviceType
from repos.devices import DeviceRecord, DeviceRepo


class DeviceService:
    """Service for managing and retrieving device information."""

    def __init__(self, repo: DeviceRepo, config: DataCollectionConfig) -> None:
        """Initialize the device service."""
        self.repo: DeviceRepo = repo
        self.config: DataCollectionConfig = config

    def get_devices(self, device_type: str | None = None) -> list[DeviceResponse]:
        """Return a list of devices for the configured project."""
        records: list[DeviceRecord] = self.repo.get_all()

        devices: list[DeviceResponse] = []
        for device in records:
            if device_type and device.type != DeviceType(device_type):
                continue
            devices.append(
                DeviceResponse(
                    id=device.id,
                    type=device.type,
                    status=device.status,
                    config=device.config,
                )
            )
        return devices

    def get_device_by_id(self, device_id: str) -> DeviceResponse | None:
        """Get a device by its ID."""
        device: DeviceRecord | None = self.repo.get_by_id(device_id)
        if not device:
            return None

        return DeviceResponse(
            id=device.id,
            type=device.type,
            status=device.status,
            config=device.config,
        )
