import os
from typing import Optional

from pydantic import BaseModel


class Settings(BaseModel):
    """Application settings"""

    # Paths
    config_path: str = os.environ.get("CONFIG_PATH", "/config/devices.yml")
    telegraf_dir: str = os.environ.get("TELEGRAF_DIR", "/config/telegraf")
    grafana_dir: str = os.environ.get(
        "GRAFANA_DIR", "/config/grafana/provisioning/dashboards"
    )
    token_env_path: str = os.environ.get(
        "TOKEN_ENV_PATH", "/config/telegraf/auth_tokens.env"
    )

    # Application settings
    refresh_interval: int = int(os.environ.get("REFRESH_INTERVAL", "3600"))  # 1 hour
    debug: bool = os.environ.get("DEBUG", "false").lower() == "true"


# Initialize settings
settings = Settings()
