# 🔍 API Monitor

API Monitor is a service that automatically discovers API endpoints and creates monitoring configurations for Telegraf and Grafana dashboards. It provides a comprehensive solution for monitoring the health and performance of various APIs.

## 🏗️ Architecture

The application follows a clean architecture with clear separation of concerns:

```
app/
├── api/                  # API layer
│   ├── routes/           # API route definitions
│   │   ├── __init__.py   # Router registry
│   │   ├── device.py     # Device management routes
│   │   └── health.py     # Health check routes
├── core/                 # Core application components
│   ├── config.py         # Configuration management
│   ├── device_config.py  # Device configuration handling
│   ├── errors.py         # Error handling and exceptions
│   └── tasks.py          # Background tasks
├── models/               # Data models
├── schemas/              # Pydantic schemas
├── services/             # Business logic services
│   └── device_service.py # Device processing service
├── utils/                # Utility functions
├── templates/            # Template files
└── main.py               # Application entry point
```

## 🧩 Key Components

- **📊 ApiDiscovery**: Discovers API endpoints from OpenAPI/Swagger specifications
- **⚙️ TelegrafConfigGenerator**: Generates Telegraf configurations for monitoring
- **📈 GrafanaDashboardGenerator**: Creates Grafana dashboards for visualization
- **🔑 TokenExporter**: Securely exports authentication tokens for devices

## ✨ Features

- 🔎 Automatic API endpoint discovery from OpenAPI/Swagger specifications
- ⚙️ Generation of Telegraf configurations for monitoring
- 📊 Creation of Grafana dashboards for visualization
- 🔐 Support for various authentication methods: None, Basic, Bearer, OAuth, OpenID Connect
- 🔄 Periodic refresh of configurations
- 🧹 Cleanup of removed device configurations
- 📡 Real-time health monitoring of critical endpoints

## 🌐 API Endpoints

- `GET /`: Root endpoint, returns service status
- `GET /api/health`: Health check endpoint
- `POST /api/devices/process`: Trigger device processing

## 🔧 Environment Variables

- `CONFIG_PATH`: Path to the devices configuration file (default: `/config/devices.yml`)
- `TELEGRAF_DIR`: Directory for Telegraf configurations (default: `/config/telegraf`)
- `GRAFANA_DIR`: Directory for Grafana dashboards (default: `/config/grafana/provisioning/dashboards`)
- `TOKEN_ENV_PATH`: Path for token environment file (default: `/config/telegraf/auth_tokens.env`)
- `REFRESH_INTERVAL`: Interval in seconds for refreshing configurations (default: `3600`)
- `DEBUG`: Enable debug mode (default: `false`)

## 🚀 Building and Running

### 🐳 Docker

```bash
docker build -t api-monitor -f app/Dockerfile.new .
docker run -v /path/to/config:/config -p 8000:8000 api-monitor
```

### 🛠️ Docker Compose (Recommended)

```bash
# Create .env file with your credentials
cp .env.example .env
# Edit the .env file with your credentials
nano .env

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down
```

### 💻 Local Development

```bash
cd app
python -m uvicorn main:app --reload
```

## ⚙️ Configuration

The application uses a YAML configuration file for device definitions. The system is configured using a YAML file located at `config/devices.yml`. Each device entry specifies how to connect to and monitor the API.

### 🔐 Authentication Methods

The system supports multiple authentication methods:

1. **No Authentication** - Set `auth_type: none`
2. **Basic Authentication** - Set `auth_type: basic` and provide `username` and `password`
3. **Bearer Token** - Set `auth_type: bearer` and provide `token`
4. **Token from Authentication** - Set `auth_type: token_from_auth` and provide details for obtaining a token
5. **OpenID Connect** - Set `auth_type: token_from_auth` with `auth_type_extension: openid_connect`

### 📋 Example Configuration

```yaml
devices:
  # Web application with Prometheus metrics
  - name: webapp
    type: web_application
    description: "Web Application"
    api:
      base_url: "http://host.docker.internal:8000"
      auth_type: none
      swagger_url: "http://host.docker.internal:8000/openapi.json"
      metrics_type: prometheus
      metrics_path: "/metrics"
      endpoints:
        - path: "/health"
          method: GET
          critical: true

  # Network router with basic auth
  - name: router-01
    type: network_router
    description: "Main office router"
    api:
      base_url: "http://host.docker.internal:8002/mock/router"
      auth_type: basic
      username: admin
      password: ${ROUTER_PASSWORD}
      swagger_url: "http://host.docker.internal:8002/mock/router/swagger.json"

  # Device API with token authentication
  - name: prismon-monitor
    type: media_monitor
    description: "Prismon media monitor"
    api:
      base_url: "http://host.docker.internal:8002/mock/prismon"
      auth_type: token_from_auth
      username: admin
      password: ${PRISMON_PASSWORD}
      # Auth endpoint to get the token
      auth_endpoint: "/api/v1/auth/login"
      auth_method: POST
      auth_payload:
        user: "{{username}}"
        pass: "{{password}}"
      token_path: "data.token"
      # Define monitoring endpoints
      endpoints:
        - path: "/api/v1/status"
          method: GET
          nested_json: true
        - path: "/api/v1/metrics"
          method: GET
          nested_json: true
        - path: "/api/v1/health"
          method: GET
          critical: true

# Global configuration
global:
  polling_interval: 60s
  timeout: 10s
```

### 🔑 Authentication Options

For `token_from_auth` authentication, the following options are available:

- `auth_endpoint`: The endpoint to request the token from
- `auth_method`: HTTP method to use (GET or POST)
- `auth_payload`: The payload to send with the request
  - Use `{{username}}` and `{{password}}` as placeholders
- `token_path`: The JSON path to extract the token from the response
  - Use dot notation, e.g., `data.token` for nested objects

For OpenID Connect authentication, additional options:

- `auth_type_extension: openid_connect`: Enables OpenID Connect flow
- `openid_client_id`: Client ID for OpenID Connect
- `openid_scope`: Scope for OpenID Connect (e.g., `offline_access`)

## 🔒 Environment Variables

For security, passwords and tokens should be stored as environment variables rather than in your configuration files:

```yaml
password: ${DEVICE_PASSWORD_VAR}
token: ${DEVICE_TOKEN_VAR}
```

Define these in a `.env` file at the root of your project:

```
# .env file example
ROUTER_PASSWORD=your_secure_router_password
PRISMON_PASSWORD=your_secure_prismon_password
ANOTHER_DEVICE_PASSWORD=another_password

# Grafana credentials
GF_ADMIN_USER=admin
GF_ADMIN_PASSWORD=admin_password
```

The `.env` file is automatically loaded by the containers, and environment variables are securely passed to the services that need them. This approach keeps sensitive credentials out of your configuration files and version control.

### 🔄 Tokens Generated via Authentication

For devices using `token_from_auth`, the system will:

1. Authenticate with the provided credentials
2. Extract the token from the response
3. Store it in a separate environment file for Telegraf to use
4. Automatically refresh tokens when they expire

## ⚙️ How It Works

1. The API Monitor reads the `devices.yml` configuration
2. For each device, it:
   - Performs authentication if needed
   - Discovers API endpoints and structure
   - Generates Telegraf configuration for monitoring
   - Creates Grafana dashboards
3. Telegraf polls the API endpoints and collects metrics
4. Prometheus stores the metrics
5. Grafana displays the metrics in dashboards

## 📊 Dashboards

Grafana dashboards are automatically generated for each device. The dashboards include:

- Device status and health metrics
- API endpoint response times
- Detailed metrics extracted from API responses
- Critical endpoint status

## 🆕 Adding a New Device

1. Add the device configuration to `config/devices.yml`
2. Add any required credentials to your `.env` file
3. Refresh the configuration:

   ```bash
   curl -X POST http://localhost:8002/api/devices/process
   ```

4. Access Grafana at <http://localhost:3000> to view the new dashboard

## 🛠️ Project Structure

```
api-monitor/
├── app/                  # Main application code
│   ├── api/              # API endpoints
│   ├── core/             # Core functionality
│   ├── models/           # Data models
│   ├── schemas/          # Request/response schemas
│   ├── services/         # Business logic
│   ├── utils/            # Utility functions
│   ├── templates/        # Template files
│   └── main.py           # Application entry point
├── config/               # Configuration files
│   ├── grafana/          # Grafana dashboards
│   ├── prometheus/       # Prometheus configuration
│   ├── telegraf/         # Telegraf configurations
│   └── devices.yml       # Device definitions
└── docker-compose.yml    # Docker Compose configuration
```
