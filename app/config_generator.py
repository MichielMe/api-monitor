#!/usr/bin/env python3
import logging
import os

import jinja2

logger = logging.getLogger("api-monitor.config-generator")


class TelegrafConfigGenerator:
    def __init__(self, device_config, api_structure):
        self.device_config = device_config
        self.api_structure = api_structure
        self.template_loader = jinja2.FileSystemLoader(
            searchpath=os.path.join(os.path.dirname(__file__), "templates")
        )
        self.template_env = jinja2.Environment(loader=self.template_loader)

    def generate(self):
        """Generate Telegraf configuration for the device"""
        device_type = self.device_config.get("type", "generic")
        device_name = self.device_config.get("name", "unknown")

        # Try to find a template for this device type
        try:
            template = self.template_env.get_template(f"telegraf_{device_type}.conf.j2")
        except jinja2.exceptions.TemplateNotFound:
            # Fallback to generic template
            template = self.template_env.get_template("telegraf_generic.conf.j2")

        # Check if auth failed and log it
        if self.device_config.get("auth_failed", False):
            logger.warning(
                f"Generating limited configuration for {device_name} due to auth failure: {self.device_config.get('auth_error', 'Unknown error')}"
            )

        # Prepare template variables - ensure global is included properly
        template_vars = {
            "device": self.device_config,
            "api": self.api_structure,
            # Get global from device_config if available, otherwise provide an empty dict
            "global": self.device_config.get("global", {}),
            "auth_failed": self.device_config.get("auth_failed", False),
            "auth_error": self.device_config.get("auth_error", None),
        }

        # Render the template
        try:
            config = template.render(**template_vars)
            # Remove any agent or output sections to avoid conflicts with the main config
            config = self.remove_conflicting_sections(config)
            return config
        except Exception as e:
            logger.error(f"Error rendering Telegraf config for {device_name}: {str(e)}")
            # Generate a minimal configuration that won't break Telegraf
            return self._generate_minimal_config(device_name, device_type)

    def _generate_minimal_config(self, device_name, device_type):
        """Generate a minimal working configuration when template rendering fails"""
        minimal_config = f"""# Minimal configuration for {device_name} due to error
# This device experienced configuration errors but won't break Telegraf

[[inputs.http_response]]
  urls = ["http://localhost:8080/healthz"]  # Dummy URL that will fail safely
  method = "GET"
  name_override = "device_error_monitor"
  follow_redirects = false
  
  [inputs.http_response.tags]
    device = "{device_name}"
    device_name = "{device_name}"
    device_type = "{device_type}"
    status = "error"
    error = "Configuration generation failed"
"""
        return minimal_config

    def save_config(self, filename):
        """Save the generated configuration to a file"""
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        # Check if we're saving to a separate file or to the main config
        if self.device_config["name"] + ".conf" in filename:
            # For device-specific configs, always write a new file
            with open(filename, "w") as f:
                f.write(self.generate())

            logger.info(
                f"Saved configuration for {self.device_config['name']} to {filename}"
            )
        else:
            # For the main config, just write it as is
            with open(filename, "w") as f:
                f.write(self.generate())

            logger.info(f"Saved Telegraf configuration to {filename}")

    def remove_conflicting_sections(self, config):
        """Remove conflicting sections from the configuration to avoid conflicts"""
        lines = config.split("\n")
        result_lines = []
        skip_section = False

        for line in lines:
            # Skip conflicting sections that would be duplicated
            if line.startswith("[agent]") or line.startswith("[global_tags]"):
                skip_section = True
            elif line.startswith("[[outputs."):
                skip_section = True
            elif skip_section and line.startswith("["):
                skip_section = False

            if not skip_section:
                result_lines.append(line)

        return "\n".join(result_lines)
