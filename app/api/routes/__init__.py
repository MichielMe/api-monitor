from fastapi import APIRouter

from app.api.routes import device, health

# Create the main API router
api_router = APIRouter()

# Include all sub-routers
api_router.include_router(device.router, prefix="/devices", tags=["devices"])
api_router.include_router(health.router, prefix="/health", tags=["health"])
