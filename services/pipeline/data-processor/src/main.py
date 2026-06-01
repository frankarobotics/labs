"""Main entry point for the data processor service."""

import signal
import sys
import time

from loguru import logger

from configs.data_processor import DataProcessorConfig, load_data_processor_config
from helpers.logging import setup_logging
from services.data_processor import DataProcessor


def setup_signal_handlers(processor: DataProcessor) -> None:
    """Setup signal handlers for graceful shutdown.

    Args:
        processor: DataProcessor instance to shutdown on signal
    """

    def signal_handler(signum: int, frame: object) -> None:
        logger.info("Received signal {}, initiating graceful shutdown...", signum)
        processor.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def main() -> None:
    """Main entry point for the data processor service."""
    logger.info("Starting Data Processor service...")

    try:
        # Load configuration to check if service is enabled
        config: DataProcessorConfig = load_data_processor_config()
        logger.info(f"Data Processor config: {config.model_dump()}")

        if not config.enabled:
            logger.info("Data Processor service is disabled, sleeping indefinitely...")
            try:
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt, shutting down...")
            return

        # Initialize processor
        processor = DataProcessor()

        # Setup signal handlers for graceful shutdown
        setup_signal_handlers(processor)

        # Start processing loop
        logger.info("Data Processor service is enabled, starting processing loop...")
        processor.start()

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error("Fatal error in main: {}", e)
        sys.exit(1)
    finally:
        logger.info("Data Processor service stopped")


if __name__ == "__main__":
    # Setup logging
    setup_logging()

    # Run main function
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
    except Exception as e:
        logger.error("Failed to start service: {}", e)
        sys.exit(1)
