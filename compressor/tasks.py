"""Celery tasks for background compression."""
import logging

from celery import shared_task

from .models import CompressionJob
from .services.dispatcher import process_job

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="compressor.run_compression_job")
def run_compression_job(self, job_id):
    """Compress a job's uploaded file in the background."""
    try:
        job = CompressionJob.objects.select_related("uploaded_file").get(pk=job_id)
    except CompressionJob.DoesNotExist:
        logger.warning("CompressionJob %s disappeared before processing", job_id)
        return {"error": "job-not-found"}

    job.celery_task_id = self.request.id or ""
    job.save(update_fields=["celery_task_id"])
    result = process_job(job)
    return {"job_id": job_id, "status": job.status, "result": result}


@shared_task(name="compressor.cleanup_temp_files")
def cleanup_temp_files(max_age_seconds=86400):
    """Remove uploaded/compressed files older than ``max_age_seconds``.

    Deletes database rows first (so media is removed via signals) then sweeps
    any orphaned files from the temporary upload directory.
    """
    import os
    import time

    from django.conf import settings
    from django.utils import timezone
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(seconds=max_age_seconds)
    deleted = 0
    for job in CompressionJob.objects.filter(created_at__lt=cutoff, status__in=[
        CompressionJob.STATUS_COMPLETED,
        CompressionJob.STATUS_WARNING,
        CompressionJob.STATUS_FAILED,
    ]):
        job.delete()
        deleted += 1

    uploads_dir = os.path.join(settings.BASE_DIR, "media", "uploads")
    now = time.time()
    for root, _dirs, files in os.walk(uploads_dir):
        for name in files:
            path = os.path.join(root, name)
            try:
                if now - os.path.getmtime(path) > max_age_seconds:
                    os.remove(path)
                    deleted += 1
            except OSError:
                continue
    return {"deleted": deleted}
