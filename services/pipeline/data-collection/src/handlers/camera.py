"""Camera handler.

This module provides endpoints for camera streaming and management.
"""

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from loguru import logger
from pipeline_configs.station import (
    ObserverDevice,
    RealSenseCameraConfig,
    StationConfig,
    ZedCameraConfig,
    load_station_config,
)

from services.camera import CameraService

router = APIRouter()


def get_camera_service() -> CameraService:
    """Dependency for getting the camera service.

    Returns:
        The camera service instance.
    """
    station_config: StationConfig = load_station_config()
    return CameraService(station_config)


@router.websocket("/api/v1/ws/cameras/{id}")
async def camera_stream(  # noqa: C901, PLR0912
    id: str,  # noqa: A002
    websocket: WebSocket,
    stream_type: str = Query("rgb", pattern="^(rgb|depth)$"),
    camera_service: CameraService = Depends(get_camera_service),
) -> None:
    """WebSocket endpoint for streaming camera images.

    Args:
        id: The ID of the camera to stream.
        websocket: The WebSocket connection.
        stream_type: 'rgb' or 'depth' to select the stream.
        camera_service: The camera service.

    Returns:
        None

    Raises:
        WebSocketDisconnect: If the client disconnects.
        Exception: For any other error during streaming.
    """
    logger.info(f"[WS] /api/v1/ws/cameras/{id} | Connection requested | stream_type={stream_type}")
    await websocket.accept()
    logger.info(f"Connection established. stream_type={stream_type}")

    observer_devices: list[ObserverDevice] = camera_service.station_config.embodiment.observer_devices or []
    observer_device: list[ObserverDevice] = [device for device in observer_devices if device.id == id]
    if len(observer_device) == 0:
        await websocket.close(code=4404)
        logger.error(f"Camera device not found for id={id}")
        return
    if len(observer_device) > 1:
        await websocket.close(code=4404)
        logger.error(f"Multiple camera devices found for id={id}")
        return

    device: ObserverDevice = observer_device[0]
    topic: str | None = None
    if isinstance(device.config, RealSenseCameraConfig):
        if stream_type == "rgb" and device.config.rgb and device.config.rgb.topic:
            topic = device.config.rgb.topic
        elif stream_type == "depth" and device.config.depth and device.config.depth.topic:
            topic = device.config.depth.topic
        elif device.config.rgb and device.config.rgb.topic:
            # Fallback to RGB topic
            topic = device.config.rgb.topic
    elif isinstance(device.config, ZedCameraConfig):
        if stream_type == "rgb" and device.config.rgb and device.config.rgb.topic:
            topic = device.config.rgb.topic
        elif stream_type == "rgb_left" and device.config.rgb_left and device.config.rgb_left.topic:
            topic = device.config.rgb_left.topic
        elif stream_type == "rgb_right" and device.config.rgb_right and device.config.rgb_right.topic:
            topic = device.config.rgb_right.topic
    else:
        await websocket.close(code=4403)
        logger.error(f"Device {id} has unsupported config type: {type(device.config)}")
        return

    if not topic:
        await websocket.close(code=4403)
        logger.error(f"Device {id} does not have a valid {stream_type} camera topic.")
        return

    logger.info(f"Starting camera stream | topic={topic} | stream_type={stream_type}")
    camera_service.start(name=f"camera_node_{id}_{stream_type}", topic=topic)
    try:
        await camera_service.stream(websocket)
        logger.info(f"Camera stream ended for camera {id} [{stream_type}]")
    except WebSocketDisconnect:
        logger.info(f"WebSocket connection closed for camera {id}")
    except Exception as e:
        logger.error(f"Error in WebSocket connection for camera {id}: {e}")
    finally:
        camera_service.stop()
        logger.info(f"Camera service stopped for camera {id}")
