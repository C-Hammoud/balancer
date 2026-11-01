from django.apps import AppConfig
import os
import threading
import time
import urllib.request
from django.conf import settings


class ExpensesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'expenses'

    def ready(self):
        from . import signals 
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
                time.sleep(100)

        t = threading.Thread(target=ping_loop, daemon=True)
        t.start()