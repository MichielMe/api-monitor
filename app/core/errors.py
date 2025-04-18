import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger("api-monitor.errors")


class ApiMonitorException(Exception):
    """Base exception for API Monitor application"""

    def __init__(self, status_code: int, detail: str, error_code: Optional[str] = None):
        self.status_code = status_code
        self.detail = detail
        self.error_code = error_code or "api_monitor_error"
        super().__init__(self.detail)


class ConfigurationError(ApiMonitorException):
    """Exception for configuration errors"""

    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            error_code="configuration_error",
        )


class DeviceError(ApiMonitorException):
    """Exception for device-related errors"""

    def __init__(self, device_name: str, detail: str):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error with device {device_name}: {detail}",
            error_code="device_error",
        )


class AuthenticationError(ApiMonitorException):
    """Exception for authentication errors"""

    def __init__(self, device_name: str, detail: str):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed for device {device_name}: {detail}",
            error_code="authentication_error",
        )


class DiscoveryError(ApiMonitorException):
    """Exception for API discovery errors"""

    def __init__(self, device_name: str, detail: str):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"API discovery failed for device {device_name}: {detail}",
            error_code="discovery_error",
        )


def setup_exception_handlers(app: FastAPI) -> None:
    """Configure exception handlers for the application"""

    @app.exception_handler(ApiMonitorException)
    async def api_monitor_exception_handler(request: Request, exc: ApiMonitorException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.error_code,
                "detail": exc.detail,
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled exception: {str(exc)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "server_error",
                "detail": f"An unexpected error occurred: {str(exc)}",
            },
        )
