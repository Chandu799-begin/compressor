"""Celery application for SmartCompress Pro."""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "smartcompress_pro.settings")

app = Celery("smartcompress_pro")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):  # pragma: no cover - simple diagnostics helper
    print(f"Request: {self.request!r}")
