from django.apps import AppConfig
import logging
import os
import threading
import time
import urllib.request

from django.conf import settings


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"

    def ready(self):
        if os.environ.get("RUN_MAIN") != "true":
            return
        if getattr(self, "_ping_started", False):
            return
        self._ping_started = True

        def ping_loop():
            url = getattr(settings, "SELF_PING_URL", "http://127.0.0.1:8000/healthz/")
            while True:
                try:
                    urllib.request.urlopen(url, timeout=5)
                except Exception:
                    pass
                # Setup nudges run here (in-process), not from the public health endpoint.
                # Production without this dev loop: schedule `manage.py send_setup_nudges`.
                try:
                    from api.user_profile import process_setup_nudges

                    process_setup_nudges()
                except Exception:
                    logging.getLogger(__name__).warning("Setup nudges failed", exc_info=True)
                time.sleep(100)

        threading.Thread(target=ping_loop, daemon=True).start()
