from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from dependencies import get_device_service
from models.device import DeviceResponse
from services.device import DeviceService

router: APIRouter = APIRouter()


@router.get("/api/v1/devices", response_model=list[DeviceResponse])
def get_devices(
    device_service: DeviceService = Depends(get_device_service),
    device_type: str | None = Query(None, alias="type", description="Filter devices by type"),
) -> list[DeviceResponse]:
    """Retrieve all available device information, optionally filtered by type.

    Args:
        device_service: Injected DeviceService dependency.
        device_type: Optional device type filter from query parameter 'type'.

    Returns:
        List[DeviceResponse]: List of device information objects.

    Raises:
        HTTPException: If an error occurs while retrieving devices.
    """
    # logger.info(f"[GET] /api/v1/devices | Filters: type={device_type}")
    try:
        devices: list[DeviceResponse] = device_service.get_devices(device_type)
        # logger.info(f"Retrieved {len(devices)} devices (type={device_type})")
        return devices
    except Exception as e:
        logger.error(f"Failed to get devices: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get devices: {e}") from e
