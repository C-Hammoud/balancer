# Loaded automatically by gunicorn from the working directory.
# PORT and WEB_CONCURRENCY come from the host where it sets them (Render); the Docker server uses the defaults.
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "3"))
timeout = 120
accesslog = "-"
