import logging
from typing import Any, Dict, List, Optional, Set

import yaml

from app.core.config import settings

logger = logging.getLogger("api-monitor.device-config")


class AttributeDict(dict):
    """Dictionary subclass that allows attribute access to dictionary keys."""

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"'dict object' has no attribute '{key}'")

    def __setattr__(self, key, value):
        self[key] = value


def load_config() -> Dict[str, Any]:
    """Load configuration from the config file"""
    try:
        with open(settings.config_path, "r") as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        logger.error(f"Error loading configuration: {str(e)}")
        return {"devices": [], "global": {}}


def get_devices() -> List[AttributeDict]:
    """Get the list of devices from the configuration"""
    config = load_config()
    devices = config.get("devices", []) or []

    # Convert each device to AttributeDict and include global config
    global_config = AttributeDict(config.get("global", {}))

    result = []
    for device in devices:
        device_config = AttributeDict(device.copy())
        device_config["global"] = global_config
        result.append(device_config)

    return result


def get_device_names() -> Set[str]:
    """Get the set of current device names for cleanup"""
    devices = get_devices()
    return set(device["name"] for device in devices if "name" in device)
