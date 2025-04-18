#!/usr/bin/env python3
import json
import logging
import os
import time
from datetime import datetime

import requests
from openapi_spec_validator import validate

logger = logging.getLogger("api-monitor.discovery")


class ApiDiscovery:
    def __init__(self, device_config):
        self.device_config = device_config
        self.base_url = device_config["api"]["base_url"]
        self.auth_type = device_config["api"].get("auth_type", "none")
        self.verify_ssl = device_config["api"].get("verify_ssl", True)
        self.session = requests.Session()
        self.session.verify = self.verify_ssl
        self.auth_token = None
        self.token_store = {}  # For storing refresh tokens and expiry times
        self.auth_failed = False
        self.auth_error = None

        # Ensure global configuration exists
        if "global" not in self.device_config:
            self.device_config["global"] = {}

        # Setup auth but catch and log failures
        try:
            self._setup_auth()
        except Exception as e:
            self.auth_failed = True
            self.auth_error = str(e)
            logger.error(
                f"Authentication setup failed for {device_config.get('name', 'unknown')}: {str(e)}"
            )

    def _setup_auth(self):
        """Set up authentication for API requests"""
        if self.auth_type == "basic":
            try:
                username = self.device_config["api"]["username"]
                password = self.device_config["api"]["password"]
                # Handle environment variable references
                if password.startswith("${") and password.endswith("}"):
                    env_var = password[2:-1]
                    password = os.environ.get(env_var, "")
                    if not password:
                        raise ValueError(
                            f"Environment variable {env_var} not set or empty"
                        )
                self.session.auth = (username, password)
                logger.info(
                    f"Basic auth setup for {self.device_config.get('name', 'unknown')}"
                )
            except Exception as e:
                self.auth_failed = True
                self.auth_error = f"Basic auth setup failed: {str(e)}"
                raise

        elif self.auth_type == "bearer":
            try:
                token = self.device_config["api"]["token"]
                # Handle environment variable references
                if token.startswith("${") and token.endswith("}"):
                    env_var = token[2:-1]
                    token = os.environ.get(env_var, "")
                    if not token:
                        raise ValueError(
                            f"Environment variable {env_var} not set or empty"
                        )
                self.session.headers.update({"Authorization": f"Bearer {token}"})
                logger.info(
                    f"Bearer token auth setup for {self.device_config.get('name', 'unknown')}"
                )
            except Exception as e:
                self.auth_failed = True
                self.auth_error = f"Bearer token setup failed: {str(e)}"
                raise

        elif self.auth_type == "token_from_auth":
            # This auth type requires a login endpoint that returns a token
            try:
                if "auth_endpoint" not in self.device_config["api"]:
                    raise ValueError("Missing auth_endpoint configuration")

                # Check if we're using OpenID Connect extension
                if (
                    self.device_config["api"].get("auth_type_extension")
                    == "openid_connect"
                ):
                    self._get_openid_token()
                else:
                    self._get_auth_token()
                logger.info(
                    f"Token auth setup for {self.device_config.get('name', 'unknown')}"
                )
            except Exception as e:
                self.auth_failed = True
                self.auth_error = f"Token auth setup failed: {str(e)}"
                raise

    def _get_openid_token(self):
        """Get token using OpenID Connect authentication flow"""
        try:
            api_config = self.device_config["api"]
            device_name = self.device_config["name"]

            # Load existing tokens from disk if available
            self._load_token_store()

            # Check if we have valid tokens already
            if device_name in self.token_store:
                token_data = self.token_store[device_name]
                # If access token is still valid, use it
                if (
                    token_data.get("expires_at", 0) > time.time() + 60
                ):  # 60-second buffer
                    self.auth_token = token_data["access_token"]
                    self.session.headers.update(
                        {"Authorization": f"Bearer {self.auth_token}"}
                    )
                    logger.info(
                        f"Using existing valid OpenID Connect access token for {device_name}"
                    )
                    return
                # If we have a refresh token, try to refresh the access token
                elif "refresh_token" in token_data:
                    self._refresh_openid_token(token_data)
                    return

            # Otherwise, get a new token
            username = api_config["username"]
            password = api_config["password"]

            # Handle environment variable references for password
            if password.startswith("${") and password.endswith("}"):
                env_var = password[2:-1]
                password = os.environ.get(env_var, "")

            # Get OpenID Connect specific configuration
            client_id = api_config.get(
                "openid_client_id", "webui"
            )  # Default for Prismon
            scope = api_config.get(
                "openid_scope", "offline_access"
            )  # Get refresh token by default

            # Prepare the token request
            auth_endpoint = api_config["auth_endpoint"]
            token_url = f"{self.base_url.rstrip('/')}/{auth_endpoint.lstrip('/')}"
            logger.info(
                f"Getting OpenID Connect token for {device_name} from {token_url}"
            )

            payload = {
                "client_id": client_id,
                "username": username,
                "password": password,
                "grant_type": "password",
                "scope": scope,
            }

            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            response = requests.post(
                token_url,
                data=payload,
                headers=headers,
                timeout=10,
                verify=self.verify_ssl,
            )
            response.raise_for_status()

            token_data = response.json()

            # Extract tokens
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 300)  # Default 5 minutes

            if not access_token:
                logger.error(
                    f"No access token found in OpenID Connect response for {device_name}"
                )
                return

            # Store the token in memory for this session
            self.auth_token = access_token
            self.session.headers.update({"Authorization": f"Bearer {access_token}"})

            # Store token information for future use
            self.token_store[device_name] = {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": time.time() + expires_in,
                "token_url": token_url,
                "client_id": client_id,
            }

            # Save token store to disk
            self._save_token_store()

            logger.info(
                f"Successfully obtained OpenID Connect tokens for {device_name}"
            )

        except Exception as e:
            logger.error(f"Error getting OpenID Connect token: {str(e)}")

    def _refresh_openid_token(self, token_data):
        """Refresh an OpenID Connect access token using the refresh token"""
        try:
            device_name = self.device_config["name"]
            token_url = token_data["token_url"]
            client_id = token_data["client_id"]
            refresh_token = token_data["refresh_token"]

            logger.info(f"Refreshing access token for {device_name}")

            payload = {
                "client_id": client_id,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }

            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            response = requests.post(
                token_url,
                data=payload,
                headers=headers,
                timeout=10,
                verify=self.verify_ssl,
            )
            response.raise_for_status()

            new_token_data = response.json()

            # Extract tokens
            access_token = new_token_data.get("access_token")
            new_refresh_token = new_token_data.get(
                "refresh_token", refresh_token
            )  # Use old one if not provided
            expires_in = new_token_data.get("expires_in", 300)  # Default 5 minutes

            if not access_token:
                logger.error(
                    f"No access token found in refresh response for {device_name}"
                )
                return

            # Update token in memory for this session
            self.auth_token = access_token
            self.session.headers.update({"Authorization": f"Bearer {access_token}"})

            # Update token information for future use
            self.token_store[device_name] = {
                "access_token": access_token,
                "refresh_token": new_refresh_token,
                "expires_at": time.time() + expires_in,
                "token_url": token_url,
                "client_id": client_id,
            }

            # Save token store to disk
            self._save_token_store()

            logger.info(f"Successfully refreshed access token for {device_name}")

        except Exception as e:
            logger.error(f"Error refreshing token: {str(e)}")
            # If refresh fails, try a full re-authentication
            logger.info(f"Token refresh failed, reverting to full authentication")
            self._get_openid_token()

    def _load_token_store(self):
        """Load token store from disk"""
        token_store_path = f"/config/telegraf/token_store.json"
        if os.path.exists(token_store_path):
            try:
                with open(token_store_path, "r") as f:
                    self.token_store = json.load(f)
                logger.info("Loaded token store from disk")
            except Exception as e:
                logger.error(f"Error loading token store: {str(e)}")

    def _save_token_store(self):
        """Save token store to disk"""
        token_store_path = f"/config/telegraf/token_store.json"
        try:
            os.makedirs(os.path.dirname(token_store_path), exist_ok=True)
            with open(token_store_path, "w") as f:
                json.dump(self.token_store, f)
            logger.info("Saved token store to disk")
        except Exception as e:
            logger.error(f"Error saving token store: {str(e)}")

    def _get_auth_token(self):
        """Get authentication token using username and password"""
        try:
            auth_endpoint = self.device_config["api"]["auth_endpoint"]
            auth_method = self.device_config["api"].get("auth_method", "POST")
            username = self.device_config["api"]["username"]
            password = self.device_config["api"]["password"]

            # Handle environment variable references for password
            if password.startswith("${") and password.endswith("}"):
                env_var = password[2:-1]
                password = os.environ.get(env_var, "")

            # Prepare auth payload based on config
            auth_payload = self.device_config["api"].get("auth_payload", {})

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
            url = f"{self.base_url.rstrip('/')}/{auth_endpoint.lstrip('/')}"
            logger.info(f"Getting auth token from {url}")

            if auth_method.upper() == "POST":
                response = self.session.post(url, json=auth_payload, timeout=10)
            else:
                response = self.session.get(url, params=auth_payload, timeout=10)

            response.raise_for_status()

            # Parse response for token
            data = response.json()

            # Extract token based on the path specified in config
            token_path = self.device_config["api"].get("token_path", "token")
            token = self._extract_nested_value(data, token_path)

            if token:
                logger.info(
                    f"Successfully obtained auth token for {self.device_config['name']}"
                )
                self.auth_token = token

                # Save the token to be used in telegraf config
                token_env_var = f"DEVICE_{self.device_config['name'].upper()}_TOKEN"
                os.environ[token_env_var] = token

                # Add the token to the current session
                self.session.headers.update({"Authorization": f"Bearer {token}"})
            else:
                logger.error(
                    f"Could not extract token from response using path '{token_path}'"
                )

        except Exception as e:
            logger.error(f"Error getting auth token: {str(e)}")

    def _extract_nested_value(self, data, path):
        """Extract a value from nested JSON using a dot-separated path"""
        parts = path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

        return current

    async def discover(self):
        """Discover API structure from swagger or sample requests"""
        # If auth failed, return a minimal working structure
        if self.auth_failed:
            logger.warning(
                f"Skipping API discovery for {self.device_config.get('name', 'unknown')} due to auth failure"
            )
            return {"endpoints": [], "auth_failed": True, "error": self.auth_error}

        # Check if Swagger/OpenAPI is available
        if "swagger_url" in self.device_config["api"]:
            try:
                return await self._discover_from_swagger()
            except Exception as e:
                logger.error(
                    f"Swagger discovery failed for {self.device_config.get('name', 'unknown')}: {str(e)}"
                )
                # Fall back to sample discovery
                return await self._discover_from_samples()
        else:
            return await self._discover_from_samples()

    async def _discover_from_swagger(self):
        """Discover API structure from Swagger/OpenAPI specification"""
        try:
            swagger_url = self.device_config["api"]["swagger_url"]
            response = self.session.get(swagger_url, timeout=10)
            response.raise_for_status()

            swagger_spec = response.json()

            # Validate OpenAPI specification
            try:
                validate(swagger_spec)
                logger.info(
                    f"Valid OpenAPI specification found for {self.device_config['name']}"
                )
            except Exception as e:
                logger.warning(f"Invalid OpenAPI specification: {str(e)}")

            # Extract paths and data types
            api_structure = {"endpoints": [], "data_models": {}}

            # Process paths
            for path, path_item in swagger_spec.get("paths", {}).items():
                for method, operation in path_item.items():
                    if method.lower() in ["get", "post"]:
                        endpoint = {
                            "path": path,
                            "method": method.upper(),
                            "description": operation.get("summary", ""),
                            "tags": operation.get("tags", []),
                            "parameters": operation.get("parameters", []),
                            "responses": {},
                        }

                        # Extract response models
                        for status, response_spec in operation.get(
                            "responses", {}
                        ).items():
                            if status.startswith("2"):  # Success responses
                                if "schema" in response_spec:
                                    endpoint["responses"]["schema"] = response_spec[
                                        "schema"
                                    ]

                        api_structure["endpoints"].append(endpoint)

            # Process definitions/components
            definitions = swagger_spec.get("definitions", {})
            if not definitions:
                definitions = swagger_spec.get("components", {}).get("schemas", {})

            api_structure["data_models"] = definitions

            return api_structure

        except Exception as e:
            logger.error(f"Error discovering API from Swagger: {str(e)}")
            raise

    async def _discover_from_samples(self):
        """Discover API structure from sample requests"""
        api_structure = {"endpoints": [], "samples": {}}

        # Use provided endpoints or default ones
        endpoints = self.device_config["api"].get(
            "endpoints", [{"path": "", "method": "GET"}]  # Root endpoint
        )

        successful_endpoints = 0
        failed_endpoints = 0

        for endpoint in endpoints:
            path = endpoint["path"]
            method = endpoint["method"]

            # Skip auth endpoint to avoid duplication
            if (
                self.auth_type == "token_from_auth"
                and self.device_config["api"].get("auth_endpoint") == path
            ):
                continue

            url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

            try:
                logger.info(f"Sampling endpoint: {method} {url}")
                try:
                    if method == "GET":
                        response = self.session.get(url, timeout=10)
                    elif method == "POST":
                        # For POST, we would need sample data which we don't have
                        # This is a simplification
                        response = self.session.post(url, json={}, timeout=10)

                    response.raise_for_status()

                    # Try to parse as JSON
                    try:
                        data = response.json()

                        successful_endpoints += 1

                        # Check if this is deeply nested JSON that needs special handling
                        is_deeply_nested = self._is_deeply_nested(data)

                        # Analyze the structure
                        metrics, tags = self._analyze_json_structure(data)

                        endpoint_config = {
                            "path": path,
                            "method": method,
                            "metrics": metrics,
                            "tags": tags,
                            "status": "ok",
                        }

                        # Mark as nested JSON if appropriate
                        if is_deeply_nested:
                            endpoint_config["nested_json"] = True

                            # If we have deeply nested JSON, create a jsonv2 config for Telegraf
                            if len(metrics) > 0 or len(tags) > 0:
                                endpoint_config["jsonv2_config"] = {
                                    "fields": metrics,
                                    "tags": tags,
                                }

                        api_structure["endpoints"].append(endpoint_config)

                        # Store a sample of the response
                        api_structure["samples"][path] = data

                    except json.JSONDecodeError:
                        logger.warning(f"Response from {url} is not valid JSON")
                        # Still add the endpoint but mark it as non-JSON
                        api_structure["endpoints"].append(
                            {
                                "path": path,
                                "method": method,
                                "status": "non-json",
                                "content_type": response.headers.get(
                                    "content-type", "unknown"
                                ),
                            }
                        )

                except requests.RequestException as req_e:
                    failed_endpoints += 1
                    logger.error(f"Request failed for endpoint {url}: {str(req_e)}")
                    # Add the failed endpoint with error info
                    api_structure["endpoints"].append(
                        {
                            "path": path,
                            "method": method,
                            "status": "error",
                            "error": str(req_e),
                        }
                    )

            except Exception as e:
                failed_endpoints += 1
                logger.error(f"Error sampling endpoint {url}: {str(e)}")
                # Add the failed endpoint with error info
                api_structure["endpoints"].append(
                    {"path": path, "method": method, "status": "error", "error": str(e)}
                )

        # Add summary information
        api_structure["summary"] = {
            "total_endpoints": len(endpoints),
            "successful_endpoints": successful_endpoints,
            "failed_endpoints": failed_endpoints,
        }

        return api_structure

    def _is_deeply_nested(self, data, max_depth=5):
        """Check if JSON is deeply nested and would benefit from special handling"""
        if not isinstance(data, (dict, list)):
            return False

        if isinstance(data, dict) and len(data) == 0:
            return False

        if isinstance(data, list) and len(data) == 0:
            return False

        # Check nesting level
        def check_depth(obj, current_depth=0):
            if current_depth >= max_depth:
                return True

            if isinstance(obj, dict):
                return any(
                    check_depth(value, current_depth + 1) for value in obj.values()
                )
            elif isinstance(obj, list) and len(obj) > 0:
                return check_depth(obj[0], current_depth + 1)

            return False

        return check_depth(data)

    def _analyze_json_structure(self, data, prefix=""):
        """Recursively analyze JSON structure to identify metrics and tags"""
        metrics = []
        tags = []

        if isinstance(data, dict):
            for key, value in data.items():
                path = f"{prefix}.{key}" if prefix else key

                if isinstance(value, (int, float)):
                    metrics.append(
                        {
                            "path": path,
                            "name": path.replace(".", "_"),
                            "type": "float" if isinstance(value, float) else "int",
                        }
                    )
                elif isinstance(value, str) and len(value) < 80:
                    tags.append({"path": path, "name": path.replace(".", "_")})
                elif isinstance(value, (dict, list)):
                    child_metrics, child_tags = self._analyze_json_structure(
                        value, path
                    )
                    metrics.extend(child_metrics)
                    tags.extend(child_tags)

        elif isinstance(data, list) and len(data) > 0:
            # Sample the first item for arrays
            sample = data[0]
            array_metrics, array_tags = self._analyze_json_structure(
                sample, f"{prefix}[*]"
            )
            metrics.extend(array_metrics)
            tags.extend(array_tags)

        return metrics, tags
