from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pipeline_configs.cors import CORSConfig, load_cors_config
from pipeline_configs.station import StationConfig, load_station_config

from configs.data_collection import DataCollectionConfig, load_data_collection_config
from configs.logger import LoggerConfig, load_logger_config
from dependencies import (
    get_device_repo,
    get_robot_service,
    get_teleop_service,
    get_workflow_state_machine,
)
from handlers import camera, devices, episode, health, recording, system, tasks, teleop
from helpers.logging import setup_logging
from helpers.rclpy_guard import is_initialized, safe_init, safe_shutdown
from services.device_monitor import DeviceMonitor
from services.franka_robot import FrankaRobotService
from state_machine.franka_workflow import FrankaWorkflowStateMachine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Async lifespan context manager for FastAPI."""
    # Initialize singletons
    robot_service: FrankaRobotService = get_robot_service()
    workflow_state_machine: FrankaWorkflowStateMachine = get_workflow_state_machine(robot_service=robot_service)
    get_teleop_service(state_machine=workflow_state_machine, robot_service=robot_service)

    # Initialize ROS at lifespan startup
    try:
        safe_init()
        logger.info("rclpy initialized at application startup: %s", is_initialized())
    except Exception as e:
        logger.error("Failed to initialize rclpy during app startup: %s", e)
        raise

    # Start thread for monitoring devices
    logger.info("Starting device monitor daemon thread")
    config: DataCollectionConfig = load_data_collection_config()
    station_config: StationConfig = load_station_config()
    device_repo = get_device_repo()
    monitor = DeviceMonitor(config, station_config, device_repo=device_repo)
    monitor.start(app)

    try:
        yield
    finally:
        logger.info("Exiting application lifespan: stopping device monitor")
        try:
            monitor.stop()
        except Exception as e:
            logger.error("Error while stopping device monitor: %s", e)

        # Shutdown rclpy if running.
        try:
            safe_shutdown()
            logger.info("rclpy shutdown at application shutdown")
        except Exception as e:
            logger.error("Error shutting down rclpy during app shutdown: %s", e)

        logger.info("Exiting application lifespan: shutdown complete")


app: FastAPI = FastAPI(
    title="Data Collection",
    description="Data Collection Service",
    version="0.1.0",
    lifespan=lifespan,
)

# Load CORS configuration
cors_config: CORSConfig = load_cors_config()
logger.info(f"Loaded CORS configuration: {cors_config}")

# Add CORS middleware with explicit configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_config.allow_origins,
    allow_credentials=cors_config.allow_credentials,
    allow_methods=cors_config.allow_methods,
    allow_headers=cors_config.allow_headers,
    expose_headers=cors_config.expose_headers,
    max_age=cors_config.max_age,
)

# Include routers for different handlers
app.include_router(health.router, tags=["Health"])
app.include_router(teleop.router, tags=["Teleoperation"])
app.include_router(episode.router, tags=["Episode"])
app.include_router(recording.router, tags=["Recording"])
app.include_router(devices.router, tags=["Devices"])
app.include_router(camera.router, tags=["Camera"])
app.include_router(system.router, tags=["System"])
app.include_router(tasks.router, tags=["Tasks"])


@app.get("/", tags=["Root"])
def read_root() -> dict[str, str]:
    """Root endpoint that returns basic service info."""
    return {
        "service": "Data Collection",
        "version": "0.1.0",
        "status": "operational",
    }


if __name__ == "__main__":
    # Load environment variables
    load_dotenv()

    # Load configuration
    config: DataCollectionConfig = load_data_collection_config()
    logger.info(f"Loaded data collection config: {config}")
    logger_config: LoggerConfig = load_logger_config()
    logger.info(f"Loaded logger config: {logger_config}")

    # Setup logging
    setup_logging(logger_config)
    logger.info("Logging is set up")

    # Run the app
    uvicorn.run(
        "main:app",
        host=config.url.rsplit(":", 1)[0],
        port=int(config.url.rsplit(":", 1)[1]),
        reload=os.getenv("RELOAD", "false").lower() == "true",
        access_log=False,
    )
