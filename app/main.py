#!/usr/bin/env python3
import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI

from app.api.routes import api_router
from app.core.config import settings
from app.core.errors import setup_exception_handlers
from app.core.tasks import start_background_tasks

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("api-monitor")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager

    Handles startup and shutdown events:
    - Startup: Initialize background tasks
    - Shutdown: Cleanup resources
    """
    # Startup: Process devices and set up periodic refresh
    background_tasks = BackgroundTasks()
    await start_background_tasks(background_tasks)

    logger.info("API Monitor started successfully")
    yield

    # Shutdown: Clean up resources if needed
    logger.info("Shutting down API Monitor")


def create_application() -> FastAPI:
    """
    Create and configure the FastAPI application
    """
    app = FastAPI(
        title="API Monitor",
        description="Automated monitoring of API endpoints",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Set up exception handlers
    setup_exception_handlers(app)

    # Include routers
    app.include_router(api_router, prefix="/api")

    return app


# Create the application instance
app = create_application()


# Root endpoint
@app.get("/")
async def root():
    """
    Root endpoint

    Provides information about the API Monitor service.
    """
    return {
        "service": "API Monitor",
        "status": "running",
        "version": "1.0.0",
        "api_docs": "/docs",
    }
