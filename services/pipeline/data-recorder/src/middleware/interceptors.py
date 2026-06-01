import logging
import time

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger: logging.Logger = logging.getLogger(__name__)


def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all unhandled exceptions."""
    logger.exception(f"Unhandled exception occurred during request to {request.url}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


class RequestResponseLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging incoming requests and outgoing responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process a request and response, logging details about both.

        Args:
            request: The incoming request
            call_next: The next middleware or endpoint handler

        Returns:
            The response from the next handler
        """
        start_time: float = time.time()

        # Log request details
        logger.debug(
            f"--> REQUEST: {request.method} {request.url.path} "
            f"(Client: {request.client.host if request.client else 'Unknown'})"
        )

        # Process the request and get the response
        response: Response = await call_next(request)

        # Calculate processing time
        process_time: float = time.time() - start_time

        # Log response details
        logger.debug(
            f"<-- RESPONSE: {request.method} {request.url.path} "
            f"Status: {response.status_code} "
            f"Duration: {process_time:.3f}s"
        )

        return response


def init_error_handlers(app: FastAPI) -> None:
    """Initialize error handlers and middleware for the FastAPI app."""
    # Add exception handlers
    app.add_exception_handler(Exception, general_exception_handler)

    # Add request/response logging middleware
    app.add_middleware(RequestResponseLoggingMiddleware)
