#!/usr/bin/env python3
import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

import yaml
from fastapi import BackgroundTasks, FastAPI

from app.config_generator import TelegrafConfigGenerator
from app.dashboard_generator import GrafanaDashboardGenerator
from app.discovery import ApiDiscovery
from app.token_exporter import TokenExporter

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("api-monitor")


# AttributeDict to support both attribute and dictionary access
class AttributeDict(dict):
    """Dictionary subclass that allows attribute access to dictionary keys."""

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"'dict object' has no attribute '{key}'")

    def __setattr__(self, key, value):
        self[key] = value


# Load configuration
def load_config():
    config_path = os.environ.get("CONFIG_PATH", "/config/devices.yml")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config


# Process device configurations
async def process_devices(background_tasks):
    config = load_config()
    devices = (
        config.get("devices", []) or []
    )  # Ensure devices is at least an empty list
    global_config = AttributeDict(config.get("global", {}))

    logger.info(f"Loaded global config: {global_config}")
    logger.info(f"Found {len(devices)} devices in configuration")

    # Track current device names for cleanup
    current_device_names = (
        set(device["name"] for device in devices) if devices else set()
    )

    # Check for removed devices and clean up their configs
    try:
        telegraf_dir = "/config/telegraf"
        grafana_dir = "/config/grafana/provisioning/dashboards"

        # Clean up Telegraf configs
        for config_file in os.listdir(telegraf_dir):
            if config_file.endswith(".conf") and config_file != "telegraf.conf":
                device_name = config_file.replace(".conf", "")
                if device_name not in current_device_names:
                    logger.info(
                        f"Removing configuration for removed device: {device_name}"
                    )
                    os.remove(os.path.join(telegraf_dir, config_file))

        # Clean up Grafana dashboards
        if os.path.exists(grafana_dir):
            for dashboard_file in os.listdir(grafana_dir):
                if dashboard_file.endswith(".json"):
                    device_name = dashboard_file.replace(".json", "")
                    if device_name not in current_device_names and device_name not in [
                        "default",
                        "welcom",
                    ]:
                        logger.info(
                            f"Removing dashboard for removed device: {device_name}"
                        )
                        os.remove(os.path.join(grafana_dir, dashboard_file))
    except Exception as e:
        logger.error(f"Error cleaning up removed devices: {str(e)}")

    # First, export tokens for devices that need authentication
    try:
        logger.info("Exporting authentication tokens for devices...")
        config_path = os.environ.get("CONFIG_PATH", "/config/devices.yml")
        token_env_path = os.environ.get(
            "TOKEN_ENV_PATH", "/config/telegraf/auth_tokens.env"
        )

        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(token_env_path), exist_ok=True)

        exporter = TokenExporter(config_path, token_env_path)
        if exporter.run():
            logger.info("Successfully exported device tokens")
        else:
            logger.warning("Failed to export some device tokens")
    except Exception as e:
        logger.error(f"Error exporting authentication tokens: {str(e)}")

    # Create a base telegraf.conf with system metrics
    try:
        create_base_telegraf_config(telegraf_dir)
    except Exception as e:
        logger.error(f"Error creating base telegraf config: {str(e)}")

    # Process each device independently to ensure failures don't affect other devices
    successful_devices = 0
    failed_devices = 0

    for device in devices:
        device_name = device.get("name", "unknown")
        try:
            logger.info(f"Processing device: {device_name}")

            # Combine device config with global defaults
            device_config = AttributeDict(device.copy())
            # Ensure global config is available to the device and all modules
            device_config["global"] = global_config

            logger.info(f"Device config structure: {list(device_config.keys())}")

            # Discover API structure
            discovery = ApiDiscovery(device_config)
            try:
                api_structure = await discovery.discover()
                logger.info(f"API structure discovered for {device_name}")
            except Exception as discovery_error:
                logger.error(
                    f"API discovery failed for {device_name}: {str(discovery_error)}"
                )
                logger.info(
                    f"Creating minimal configuration for {device_name} due to discovery failure"
                )
                # Create a minimal structure for failed devices that still allows basic monitoring
                api_structure = {
                    "endpoints": [],
                    "error": str(discovery_error),
                    "status": "error",
                }

            # Mark auth failures in the device config for template handling
            if hasattr(discovery, "auth_failed") and discovery.auth_failed:
                device_config["auth_failed"] = True
                device_config["auth_error"] = discovery.auth_error

            # Generate Telegraf configuration
            try:
                generator = TelegrafConfigGenerator(device_config, api_structure)
                telegraf_config = generator.generate()

                # Write to a device-specific config file
                device_conf_path = f"{telegraf_dir}/{device_name}.conf"
                with open(device_conf_path, "w") as f:
                    f.write(telegraf_config)

                logger.info(
                    f"Created Telegraf configuration for {device_name} at {device_conf_path}"
                )

                # Generate Grafana dashboard
                try:
                    dashboard_generator = GrafanaDashboardGenerator(
                        device_config, api_structure
                    )
                    dashboard = dashboard_generator.generate()
                    dashboard_generator.save_dashboard(
                        f"/config/grafana/provisioning/dashboards/{device_name}.json"
                    )
                    logger.info(f"Generated dashboard for {device_name}")
                except Exception as dash_error:
                    logger.error(
                        f"Dashboard generation failed for {device_name}: {str(dash_error)}"
                    )

                successful_devices += 1
                logger.info(f"Successfully configured monitoring for {device_name}")
            except Exception as config_error:
                logger.error(
                    f"Configuration generation failed for {device_name}: {str(config_error)}"
                )
                failed_devices += 1

        except Exception as e:
            logger.error(f"Error processing device {device_name}: {str(e)}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            failed_devices += 1

    # Log summary
    logger.info(
        f"Device processing complete. Successful: {successful_devices}, Failed: {failed_devices}"
    )

    # Reload Telegraf configurations
    try:
        logger.info("Reloading Telegraf configurations...")
        # This assumes telegraf is configured to watch the config directory
        # Alternatively, we could send a signal to reload
        # os.system("docker-compose exec telegraf kill -HUP 1")
    except Exception as e:
        logger.error(f"Error reloading Telegraf: {str(e)}")

    return {"successful": successful_devices, "failed": failed_devices}


def create_base_telegraf_config(telegraf_dir):
    """Create a base telegraf.conf with system metrics"""
    base_config = """# Telegraf Configuration - Minimal version
# This file includes system monitoring for devices

[agent]
  interval = "60s"
  round_interval = true
  metric_batch_size = 1000
  metric_buffer_limit = 10000
  collection_jitter = "0s"
  flush_interval = "10s"
  flush_jitter = "0s"
  precision = ""
  hostname = ""
  omit_hostname = false

[[outputs.prometheus_client]]
  listen = ":9273"
  metric_version = 2
  path = "/metrics"

# Basic system monitoring
[[inputs.cpu]]
  percpu = true
  totalcpu = true
  collect_cpu_time = false
  report_active = false

[[inputs.disk]]
  ignore_fs = ["tmpfs", "devtmpfs", "devfs", "iso9660", "overlay", "aufs", "squashfs"]

[[inputs.mem]]

[[inputs.system]]

# Monitor Telegraf itself
[[inputs.internal]]
  collect_memstats = true
"""
    with open(f"{telegraf_dir}/telegraf.conf", "w") as f:
        f.write(base_config)
    logger.info(f"Created base telegraf.conf with system metrics")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Process devices and set up periodic refresh
    background_tasks = BackgroundTasks()

    # Process devices on startup
    background_tasks.add_task(process_devices, background_tasks)

    # Set up periodic configuration refresh
    async def refresh_configs():
        while True:
            await asyncio.sleep(3600)  # Refresh every hour
            logger.info("Refreshing device configurations...")
            await process_devices(background_tasks)

    background_tasks.add_task(refresh_configs)

    yield  # Server is running and ready to handle requests

    # Shutdown: Clean up resources if needed
    logger.info("Shutting down API Monitor")


app = FastAPI(title="API Monitor", lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "running", "message": "API Monitor is running"}


@app.post("/refresh")
async def refresh(background_tasks: BackgroundTasks):
    background_tasks.add_task(process_devices, background_tasks)
    return {"status": "refreshing", "message": "Refreshing device configurations"}


# Manually process devices
@app.post("/process-devices")
async def process_devices_endpoint(background_tasks: BackgroundTasks):
    await process_devices(background_tasks)
    return {"status": "success", "message": "Devices processed successfully"}
