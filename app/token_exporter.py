#!/usr/bin/env python3

import json
import logging
import os
import sys
from pathlib import Path

import requests
import yaml

logger = logging.getLogger("api-monitor.token-exporter")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


class TokenExporter:
    """
    Exports authentication tokens to environment variables for Telegraf to use.
    Creates a file with environment variables that can be sourced by the shell.
    """

    def __init__(self, config_path, output_path):
        self.config_path = config_path
        self.output_path = output_path
        self.env_vars = {}
        self.device_config = None

    def load_config(self):
        """Load the device configuration from YAML"""
        try:
            with open(self.config_path, "r") as f:
                self.device_config = yaml.safe_load(f)
            logger.info(f"Loaded configuration from {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"Error loading configuration: {str(e)}")
            return False

    def extract_nested_value(self, data, path):
        """Extract a value from nested JSON using a dot-separated path"""
        parts = path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

        return current

    def get_auth_token(self, device):
        """Get authentication token for a device"""
        try:
            api_config = device["api"]
            base_url = api_config["base_url"]
            auth_type = api_config.get("auth_type", "none")

            if auth_type != "token_from_auth":
                return None

            if "auth_endpoint" not in api_config:
                logger.error(f"Missing auth_endpoint for device {device['name']}")
                return None

            # Extract auth configuration
            auth_endpoint = api_config["auth_endpoint"]
            auth_method = api_config.get("auth_method", "POST")
            username = api_config["username"]
            password = api_config["password"]

            # Handle environment variable references for password
            if password.startswith("${") and password.endswith("}"):
                env_var = password[2:-1]
                password = os.environ.get(env_var, "")
                if not password:
                    logger.error(
                        f"Environment variable {env_var} not set for device {device['name']}"
                    )
                    return None

            # Prepare auth payload based on config
            auth_payload = api_config.get("auth_payload", {})

            # If auth_payload doesn't specify username/password fields, use defaults
            if not auth_payload:
                auth_payload = {"username": username, "password": password}
            else:
                # Replace template placeholders in the payload
                for key, value in auth_payload.items():
                    if value == "{{username}}":
                        auth_payload[key] = username
                    elif value == "{{password}}":
                        auth_payload[key] = password

            # Make the auth request
            url = f"{base_url.rstrip('/')}/{auth_endpoint.lstrip('/')}"
            logger.info(f"Getting auth token for {device['name']} from {url}")

            if auth_method.upper() == "POST":
                response = requests.post(url, json=auth_payload, timeout=10)
            else:
                response = requests.get(url, params=auth_payload, timeout=10)

            response.raise_for_status()

            # Parse response for token
            data = response.json()

            # Extract token based on the path specified in config
            token_path = api_config.get("token_path", "token")
            token = self.extract_nested_value(data, token_path)

            if token:
                logger.info(f"Successfully obtained auth token for {device['name']}")
                return token
            else:
                logger.error(
                    f"Could not extract token from response using path '{token_path}'"
                )
                return None

        except Exception as e:
            logger.error(f"Error getting auth token for {device['name']}: {str(e)}")
            return None

    def process_devices(self):
        """Process all devices that need tokens"""
        if not self.device_config:
            logger.error("No configuration loaded")
            return False

        devices = self.device_config.get("devices", [])

        for device in devices:
            try:
                if (
                    "api" in device
                    and device["api"].get("auth_type") == "token_from_auth"
                ):
                    token = self.get_auth_token(device)
                    if token:
                        env_var_name = f"DEVICE_{device['name'].upper()}_TOKEN"
                        self.env_vars[env_var_name] = token
                        logger.info(f"Set token for {device['name']} in {env_var_name}")
            except Exception as e:
                logger.error(f"Error processing device {device['name']}: {str(e)}")

        return True

    def write_env_file(self):
        """Write environment variables to a file that can be sourced"""
        if not self.env_vars:
            logger.warning("No tokens to export")
            return False

        try:
            with open(self.output_path, "w") as f:
                f.write("# Generated by API Monitor - Do not edit manually\n")
                for name, value in self.env_vars.items():
                    f.write(f'export {name}="{value}"\n')

            logger.info(f"Wrote {len(self.env_vars)} tokens to {self.output_path}")
            return True
        except Exception as e:
            logger.error(f"Error writing environment file: {str(e)}")
            return False

    def run(self):
        """Run the token exporter"""
        if not self.load_config():
            return False

        if not self.process_devices():
            return False

        return self.write_env_file()


if __name__ == "__main__":
    config_path = os.environ.get("CONFIG_PATH", "/config/devices.yml")
    output_path = os.environ.get("TOKEN_ENV_PATH", "/config/telegraf/auth_tokens.env")

    exporter = TokenExporter(config_path, output_path)
    success = exporter.run()

    if success:
        logger.info("Token export completed successfully")
        sys.exit(0)
    else:
        logger.error("Token export failed")
        sys.exit(1)
