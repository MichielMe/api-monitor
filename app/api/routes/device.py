from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks

from app.services.device_service import DeviceService

router = APIRouter()


@router.post("/process", status_code=202)
async def process_devices(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    Process devices in the background

    This endpoint triggers the device processing workflow:
    1. Discovers API structure for each device
    2. Generates Telegraf configurations
    3. Creates Grafana dashboards

    The processing happens in the background and does not block the response.
    """
    background_tasks.add_task(DeviceService.process_devices)
    return {
        "status": "processing",
        "message": "Device processing started in the background",
    }
