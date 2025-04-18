#!/usr/bin/env python3
import json
import logging
import os
import uuid

import jinja2

logger = logging.getLogger("api-monitor.dashboard-generator")


class GrafanaDashboardGenerator:
    def __init__(self, device_config, api_structure):
        self.device_config = device_config
        self.api_structure = api_structure

        # Ensure global configuration exists
        if "global" not in self.device_config:
            self.device_config["global"] = {}

        self.template_loader = jinja2.FileSystemLoader(
            searchpath=os.path.join(os.path.dirname(__file__), "templates")
        )
        self.template_env = jinja2.Environment(loader=self.template_loader)

    def generate(self):
        """Generate Grafana dashboard for the device"""
        device_type = self.device_config.get("type", "generic")
        device_name = self.device_config.get("name", "device")

        # Try to find a template for this device type
        try:
            template = self.template_env.get_template(
                f"dashboard_{device_type}.json.j2"
            )
        except jinja2.exceptions.TemplateNotFound:
            # Fallback to generic template
            template = self.template_env.get_template("dashboard_generic.json.j2")

        # Generate panels based on discovered metrics
        panels = []
        y_pos = 0

        # Add a header panel with device information
        header_panel = {
            "type": "text",
            "title": f"{device_name} Overview",
            "gridPos": {"x": 0, "y": y_pos, "w": 24, "h": 3},
            "id": self._generate_id(),
            "options": {
                "mode": "markdown",
                "content": f"""# {device_name} ({device_type})
                
**Description**: {self.device_config.get('description', 'No description')}
                
**Status**: Data from {len(self.api_structure.get('endpoints', []))} endpoints""",
            },
        }
        panels.append(header_panel)
        y_pos += 3

        # Add status panel
        status_panel = {
            "type": "stat",
            "title": "Device Status",
            "gridPos": {"x": 0, "y": y_pos, "w": 24, "h": 4},
            "id": self._generate_id(),
            "options": {
                "colorMode": "value",
                "graphMode": "area",
                "justifyMode": "auto",
                "textMode": "auto",
            },
            "fieldConfig": {
                "defaults": {
                    "mappings": [
                        {
                            "type": "value",
                            "options": {
                                "1": {"text": "Online", "color": "green"},
                                "0": {"text": "Offline", "color": "red"},
                            },
                        }
                    ],
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"value": None, "color": "red"},
                            {"value": 1, "color": "green"},
                        ],
                    },
                    "color": {"mode": "thresholds"},
                }
            },
            "targets": [
                {
                    "expr": f'device_health_response_status_code{{device_name="{device_name}", url=~".*"}} / 100',
                    "refId": "A",
                    "legendFormat": "Status",
                }
            ],
        }
        panels.append(status_panel)
        y_pos += 4

        # Group metrics into logical sections
        metric_groups = self._group_metrics()

        # Create a panel for each group
        for group_name, metrics in metric_groups.items():
            # Create a row for the group
            panels.append(
                {
                    "type": "row",
                    "title": group_name,
                    "gridPos": {"x": 0, "y": y_pos, "w": 24, "h": 1},
                    "id": self._generate_id(),
                    "collapsed": False,
                }
            )
            y_pos += 1

            # Create panels for the metrics in this group
            for i, metric in enumerate(metrics):
                panel = self._create_panel_for_metric(
                    metric, i % 2 * 12, y_pos, group_name
                )
                panels.append(panel)

                # Move to next row every 2 panels
                if i % 2 == 1:
                    y_pos += 8

        # Prepare template variables
        template_vars = {
            "device": self.device_config,
            "api": self.api_structure,
            "panels": panels,
            "uid": str(uuid.uuid4()),
            "title": f"{device_name} Dashboard",
            "device_name": device_name,  # Explicitly pass device name for filtering
        }

        # Render the template
        dashboard_json = template.render(**template_vars)
        return json.loads(dashboard_json)

    def _group_metrics(self):
        """Group metrics into logical sections based on paths"""
        metric_groups = {}

        # Process all endpoints
        for endpoint in self.api_structure.get("endpoints", []):
            metrics = endpoint.get("metrics", [])

            for metric in metrics:
                # Try to extract a group name from the path
                parts = metric["path"].split(".")

                if len(parts) > 1:
                    group_name = parts[0].title()
                else:
                    group_name = "General"

                if group_name not in metric_groups:
                    metric_groups[group_name] = []

                metric_groups[group_name].append(metric)

        return metric_groups

    def _create_panel_for_metric(self, metric, x_pos, y_pos, group_name):
        """Create a Grafana panel for a metric"""
        metric_name = metric["name"]
        metric_path = metric["path"]
        metric_type = metric["type"]
        device_name = self.device_config.get("name", "device")

        # Determine the best visualization based on the metric type
        if metric_type in ["int", "float"]:
            panel_type = "gauge"  # or "stat" or "graph"
        else:
            panel_type = "stat"

        # Create the panel configuration
        panel = {
            "id": self._generate_id(),
            "title": metric_name.replace("_", " ").title(),
            "type": panel_type,
            "gridPos": {"x": x_pos, "y": y_pos, "w": 12, "h": 8},
            "targets": [
                {
                    # For our simplified metrics approach, search for any metrics with the device name
                    "expr": f'{{device_name="{device_name}"}}',
                    "refId": "A",
                    "legendFormat": "{{__name__}}",
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "mappings": [],
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"value": None, "color": "green"},
                            {"value": 80, "color": "yellow"},
                            {"value": 90, "color": "red"},
                        ],
                    },
                }
            },
        }

        return panel

    def _generate_id(self):
        """Generate a unique ID for a panel"""
        return int(uuid.uuid4().hex[:8], 16) & 0x7FFFFFFF

    def save_dashboard(self, filename):
        """Save the generated dashboard to a file"""
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        with open(filename, "w") as f:
            json.dump(self.generate(), f, indent=2)

        logger.info(f"Saved Grafana dashboard to {filename}")
