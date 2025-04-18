import asyncio
import logging
import os
from typing import Any, Dict, List, Set

from app.config_generator import TelegrafConfigGenerator
from app.core.config import settings
from app.core.device_config import AttributeDict, get_device_names, get_devices
from app.core.errors import ConfigurationError, DeviceError
from app.dashboard_generator import GrafanaDashboardGenerator
from app.discovery import ApiDiscovery
from app.token_exporter import TokenExporter

logger = logging.getLogger("api-monitor.device-service")


class DeviceService:
    """Service for device operations"""

    @staticmethod
    async def process_devices() -> Dict[str, int]:
        """Process all devices and generate configurations"""
        # Get device names for cleanup
        current_device_names = get_device_names()

        # Clean up removed devices
        await DeviceService._cleanup_removed_devices(current_device_names)

        # Export tokens for devices that need authentication
        DeviceService._export_tokens()

        # Create base telegraf config
        DeviceService._create_base_telegraf_config()

        # Process each device
        devices = get_devices()
        successful_devices = 0
        failed_devices = 0

        for device in devices:
            try:
                if await DeviceService._process_device(device):
                    successful_devices += 1
                else:
                    failed_devices += 1
            except Exception as e:
                logger.error(
                    f"Error processing device {device.get('name', 'unknown')}: {str(e)}"
                )
                failed_devices += 1

        logger.info(
            f"Device processing complete. Successful: {successful_devices}, Failed: {failed_devices}"
        )
        return {"successful": successful_devices, "failed": failed_devices}

    @staticmethod
    async def _process_device(device: AttributeDict) -> bool:
        """Process a single device"""
        device_name = device.get("name", "unknown")
        logger.info(f"Processing device: {device_name}")

        try:
            # Discover API structure
            discovery = ApiDiscovery(device)
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
                # Create a minimal structure for failed devices
                api_structure = {
                    "endpoints": [],
                    "error": str(discovery_error),
                    "status": "error",
                }

            # Mark auth failures in the device config
            if hasattr(discovery, "auth_failed") and discovery.auth_failed:
                device["auth_failed"] = True
                device["auth_error"] = discovery.auth_error

            # Generate Telegraf configuration
            try:
                generator = TelegrafConfigGenerator(device, api_structure)
                telegraf_config = generator.generate()

                # Write to device-specific config file
                device_conf_path = f"{settings.telegraf_dir}/{device_name}.conf"
                os.makedirs(os.path.dirname(device_conf_path), exist_ok=True)
                with open(device_conf_path, "w") as f:
                    f.write(telegraf_config)

                logger.info(f"Created Telegraf configuration for {device_name}")

                # Generate Grafana dashboard
                try:
                    dashboard_generator = GrafanaDashboardGenerator(
                        device, api_structure
                    )
                    dashboard = dashboard_generator.generate()

                    # Save dashboard
                    dashboard_path = f"{settings.grafana_dir}/{device_name}.json"
                    os.makedirs(os.path.dirname(dashboard_path), exist_ok=True)
                    dashboard_generator.save_dashboard(dashboard_path)

                    logger.info(f"Generated dashboard for {device_name}")
                except Exception as dash_error:
                    logger.error(
                        f"Dashboard generation failed for {device_name}: {str(dash_error)}"
                    )

                return True
            except Exception as config_error:
                logger.error(
                    f"Configuration generation failed for {device_name}: {str(config_error)}"
                )
                return False

        except Exception as e:
            logger.error(f"Error processing device {device_name}: {str(e)}")
            return False

    @staticmethod
    async def _cleanup_removed_devices(current_device_names: Set[str]) -> None:
        """Clean up configurations for removed devices"""
        try:
            # Clean up Telegraf configs
            if os.path.exists(settings.telegraf_dir):
                for config_file in os.listdir(settings.telegraf_dir):
                    if config_file.endswith(".conf") and config_file != "telegraf.conf":
                        device_name = config_file.replace(".conf", "")
                        if device_name not in current_device_names:
                            logger.info(
                                f"Removing configuration for removed device: {device_name}"
                            )
                            os.remove(os.path.join(settings.telegraf_dir, config_file))

            # Clean up Grafana dashboards
            if os.path.exists(settings.grafana_dir):
                for dashboard_file in os.listdir(settings.grafana_dir):
                    if dashboard_file.endswith(".json"):
                        device_name = dashboard_file.replace(".json", "")
                        if (
                            device_name not in current_device_names
                            and device_name not in ["default", "welcome"]
                        ):
                            logger.info(
                                f"Removing dashboard for removed device: {device_name}"
                            )
                            os.remove(
                                os.path.join(settings.grafana_dir, dashboard_file)
                            )
        except Exception as e:
            logger.error(f"Error cleaning up removed devices: {str(e)}")

    @staticmethod
    def _export_tokens() -> None:
        """Export authentication tokens for devices"""
        try:
            logger.info("Exporting authentication tokens for devices...")

            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(settings.token_env_path), exist_ok=True)

            exporter = TokenExporter(settings.config_path, settings.token_env_path)
            if exporter.run():
                logger.info("Successfully exported device tokens")
            else:
                logger.warning("Failed to export some device tokens")
        except Exception as e:
            logger.error(f"Error exporting authentication tokens: {str(e)}")

    @staticmethod
    def _create_base_telegraf_config() -> None:
        """Create a base telegraf.conf with system metrics"""
        try:
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
            os.makedirs(settings.telegraf_dir, exist_ok=True)
            with open(f"{settings.telegraf_dir}/telegraf.conf", "w") as f:
                f.write(base_config)

            logger.info("Created base telegraf.conf with system metrics")
        except Exception as e:
            logger.error(f"Error creating base telegraf config: {str(e)}")
