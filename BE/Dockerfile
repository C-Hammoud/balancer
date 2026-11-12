# Django API image (also used by the scheduler). Works on x86 and ARM (Oracle Ampere).
# Build: docker compose -f deploy/docker-compose.yml build

# ---- Build wheels (compilers stay out of the final image) ----
FROM python:3.13-slim-trixie AS build
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /wheels
COPY requirements.txt .
RUN pip wheel --no-cache-dir -r requirements.txt -w /wheels

# ---- Runtime ----
FROM python:3.13-slim-trixie
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STATIC_ROOT=/app/staticfiles
# postgresql-client: pg_dump for the nightly backup (same major version as the postgres:17 database).
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /wheels /wheels
RUN pip install --no-index --find-links=/wheels /wheels/*.whl && rm -rf /wheels

WORKDIR /app
COPY . .
# uid 1000 = the default "ubuntu" user on the server, so backups written to deploy/backups are yours.
RUN useradd --uid 1000 --create-home app \
    && mkdir -p /app/staticfiles /backups \
    && chown -R app:app /app/staticfiles /backups \
    && chmod +x /app/docker-entrypoint.sh
USER app

EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
# Bind address, workers and timeout: gunicorn.conf.py
CMD ["gunicorn", "finance_tracker.wsgi:application"]
