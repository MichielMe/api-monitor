import asyncio
import logging

from fastapi import BackgroundTasks

from app.core.config import settings
from app.services.device_service import DeviceService

logger = logging.getLogger("api-monitor.tasks")


async def start_background_tasks(background_tasks: BackgroundTasks) -> None:
    """Start all background tasks"""
    # Initial device processing
    background_tasks.add_task(DeviceService.process_devices)

    # Start periodic refresh task
    background_tasks.add_task(periodic_refresh)


async def periodic_refresh() -> None:
    """Periodically refresh device configurations"""
    while True:
        await asyncio.sleep(settings.refresh_interval)
        logger.info("Refreshing device configurations...")

        try:
            await DeviceService.process_devices()
            logger.info("Device configurations refreshed successfully")
        except Exception as e:
            logger.error(f"Error refreshing device configurations: {str(e)}")
