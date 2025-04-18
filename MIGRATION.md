# Migration Guide

This document guides you through migrating from the old monolithic structure to the new refactored architecture.

## Key Changes

1. **Directory Structure**: The application has been reorganized into a modular structure with clear separation of concerns.
2. **Dependency Injection**: Services and components are properly separated and follow dependency injection patterns.
3. **Error Handling**: Improved error handling with custom exceptions.
4. **Configuration Management**: Environment variables are managed through a central configuration module.
5. **API Organization**: API endpoints are organized into routers with clear responsibilities.

## Migration Steps

### 1. Configuration Changes

The old configuration was hardcoded in the main.py file. It's now managed through environment variables:

```bash
# Old approach
CONFIG_PATH=/config/devices.yml

# New approach
export CONFIG_PATH=/config/devices.yml
export TELEGRAF_DIR=/config/telegraf
export GRAFANA_DIR=/config/grafana/provisioning/dashboards
export TOKEN_ENV_PATH=/config/telegraf/auth_tokens.env
export REFRESH_INTERVAL=3600
export DEBUG=false
```

### 2. Running the Application

#### Old Approach

```bash
python app/main.py
```

#### New Approach

```bash
# Using the main_refactored.py directly
python -m uvicorn app.main_refactored:app --host 0.0.0.0 --port 8000

# Using Docker
docker build -t api-monitor -f app/Dockerfile.new .
docker run -v /path/to/config:/config -p 8000:8000 api-monitor
```

### 3. API Endpoint Changes

| Old Endpoint           | New Endpoint               | Notes                          |
|------------------------|----------------------------|--------------------------------|
| `GET /`                | `GET /`                    | Still returns service status   |
| `POST /refresh`        | `POST /api/devices/process`| Renamed for clarity            |
| `POST /process-devices`| `POST /api/devices/process`| Consolidated with /refresh     |
| N/A                    | `GET /api/health`          | New health check endpoint      |

### 4. Code Migration

If you have custom code that extends the original application:

1. Identify which component your code interacts with (ApiDiscovery, TelegrafConfigGenerator, etc.)
2. Adapt your code to use the new service-based architecture
3. Consider implementing your extensions as services that follow the new patterns

### 5. Testing Changes

The new structure facilitates better testing with separation of concerns:

- **Unit Tests**: Test individual services and components
- **Integration Tests**: Test API endpoints and service interactions
- **End-to-End Tests**: Test complete workflows

### 6. Deployment Considerations

1. Update any CI/CD pipelines to use the new Dockerfile
2. Update environment variable configurations in your deployment
3. Consider a gradual rollout to monitor for any issues

## Direct Replacement Steps

To directly replace the old application with the new one:

1. Rename `main_refactored.py` to `main.py`
2. Update the Dockerfile to use the renamed file
3. Ensure all environment variables are properly set
4. Deploy the application

## Rollback Plan

If issues arise during migration:

1. Keep the old `main.py` as a backup
2. If the new structure causes issues, restore the old file
3. Update the Dockerfile to use the original entrypoint
