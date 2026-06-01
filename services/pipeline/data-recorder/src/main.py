import contextlib
import os
from collections.abc import AsyncGenerator

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from configs.cors import CORSConfig, load_cors_config
from configs.data_recorder import DataRecorderConfig, load_data_recorder_config
from configs.logger import LoggerConfig, load_logger_config
from handlers import record
from helpers.logging import setup_logging
from middleware.interceptors import init_error_handlers
from repos.record_metadata import RecordMetadataRepo
from services.record import RecordService


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    Handles initialization and cleanup of resources when the application starts and stops.

    Args:
        app: The FastAPI application instance.

    Yields:
        None
    """
    # Load configuration
    config: DataRecorderConfig = load_data_recorder_config()

    # Create metadata repository
    metadata_repo = RecordMetadataRepo(base_path=config.output_path)

    # Initialize RecordService as a singleton
    logger.info("Initializing RecordService as a singleton")
    RecordService(config, metadata_repo)

    yield

    # Perform any cleanup needed during application shutdown
    logger.info("Cleaning up resources during application shutdown")
    RecordService.reset()


app: FastAPI = FastAPI(
    title="Data Recorder",
    description="Data Recorder Service",
    version="0.1.0",
    lifespan=lifespan,  # Use our lifespan context manager
)

# Initialize error handlers
init_error_handlers(app)

# Load CORS configuration
cors_config: CORSConfig = load_cors_config()
logger.info(f"Setting up CORS with configuration: {cors_config}")

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
app.include_router(record.router, tags=["Record"])


@app.get("/", tags=["Root"])
def read_root() -> dict[str, str]:
    """Root endpoint that returns basic service info."""
    return {
        "service": "Data Recorder",
        "version": "0.1.0",
        "status": "operational",
    }


if __name__ == "__main__":
    # Load environment variables
    load_dotenv()

    # Load configuration
    config: DataRecorderConfig = load_data_recorder_config()
    logger_config: LoggerConfig = load_logger_config()

    # Setup logging with loguru
    setup_logging(logger_config)

    logger.info(f"Application configuration: {config}")

    # Run the app
    uvicorn.run(
        "main:app",
        host=config.url.rsplit(":", 1)[0],
        port=int(config.url.rsplit(":", 1)[1]),
        reload=os.getenv("RELOAD", "false").lower() == "true",
        access_log=False,
    )
