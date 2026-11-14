# RiskFlow: image used for the local deployment (see docs/riskflow-deploiement.md)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    DJANGO_SETTINGS_MODULE=config.settings.local

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

# WeasyPrint (PDF export) needs Pango and a font
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first: this layer is cached until uv.lock changes
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

# Build the CSS (standalone Tailwind binary) and collect the static files.
# The build needs no real secret: these values only exist for this step.
RUN SECRET_KEY=build DB_NAME=x DB_USER=x DB_PASSWORD=x DB_HOST=x \
    DJANGO_SETTINGS_MODULE=config.settings.dev \
    uv run --no-dev python manage.py tailwind build \
 && SECRET_KEY=build DB_NAME=x DB_USER=x DB_PASSWORD=x DB_HOST=x \
    STATIC_ROOT=/app/staticfiles LOG_DIR=/tmp/build-logs \
    uv run --no-dev python manage.py collectstatic --noinput

# Non-root user; /data holds what must survive an update (media, logs)
RUN useradd --create-home riskflow \
 && mkdir -p /data/media /data/logs \
 && chown -R riskflow /data /app/staticfiles
USER riskflow

ENV MEDIA_ROOT=/data/media \
    LOG_DIR=/data/logs \
    STATIC_ROOT=/app/staticfiles \
    PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
