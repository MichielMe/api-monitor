FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim


ENV PYTHONUNBUFFERED=1

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

ENV UV_COMPILE_BYTE=1

ENV UV_LINK_MODE=copy

# Change the working directory to the `app` directory
WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"

COPY ./pyproject.toml ./uv.lock ./.python-version /app/

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Copy the project into the image
COPY . /app

CMD ["fastapi", "run", "main.py", "--host", "0.0.0.0", "--port", "8000"] 
# CMD ls -lah /app/.venv/bin/