"""Data models for the compressor application."""
import os
import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from .services.size_converter import bytes_to_human

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx"}


def upload_to(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"uploads/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{ext}"


def compressed_upload_to(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"compressed/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{ext}"


class UploadedFile(models.Model):
    CATEGORY_IMAGE = "image"
    CATEGORY_DOCUMENT = "document"
    CATEGORY_OTHER = "other"
    CATEGORY_CHOICES = [
        (CATEGORY_IMAGE, "Image"),
        (CATEGORY_DOCUMENT, "Document"),
        (CATEGORY_OTHER, "Other"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="uploaded_files",
        null=True,
        blank=True,
    )
    original_file = models.FileField(upload_to=upload_to)
    filename = models.CharField(max_length=512)
    file_type = models.CharField(max_length=128, blank=True)
    mime_type = models.CharField(max_length=128, blank=True)
    category = models.CharField(max_length=16, choices=CATEGORY_CHOICES, default=CATEGORY_OTHER)
    original_size = models.BigIntegerField(default=0)
    checksum = models.CharField(max_length=64, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [models.Index(fields=["-uploaded_at"])]

    def __str__(self):
        return self.filename

    @property
    def extension(self):
        return os.path.splitext(self.filename)[1].lower()

    @property
    def is_image(self):
        return self.category == self.CATEGORY_IMAGE

    @property
    def is_document(self):
        return self.category == self.CATEGORY_DOCUMENT

    @property
    def original_size_display(self):
        return bytes_to_human(self.original_size)

    @property
    def earliest_job(self):
        return self.jobs.order_by("created_at").first()


class CompressionJob(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_WARNING = "warning"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_WARNING, "Completed with warning"),
    ]

    LEVEL_LOW = "low"
    LEVEL_MEDIUM = "medium"
    LEVEL_HIGH = "high"
    LEVEL_CUSTOM = "custom"
    LEVEL_CHOICES = [
        (LEVEL_LOW, "Low compression"),
        (LEVEL_MEDIUM, "Medium compression"),
        (LEVEL_HIGH, "High compression"),
        (LEVEL_CUSTOM, "Custom"),
    ]

    uploaded_file = models.ForeignKey(
        UploadedFile, on_delete=models.CASCADE, related_name="jobs"
    )
    target_size_bytes = models.BigIntegerField(null=True, blank=True)
    compression_level = models.CharField(
        max_length=16, choices=LEVEL_CHOICES, default=LEVEL_MEDIUM
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    options = models.JSONField(default=dict, blank=True)
    message = models.TextField(blank=True)
    processing_time = models.FloatField(default=0.0)
    celery_task_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"]), models.Index(fields=["status"])]

    def __str__(self):
        return f"Job #{self.pk} - {self.uploaded_file.filename}"

    @property
    def target_size_display(self):
        if not self.target_size_bytes:
            return "Best effort"
        return bytes_to_human(self.target_size_bytes)

    @property
    def is_finished(self):
        return self.status in {self.STATUS_COMPLETED, self.STATUS_FAILED, self.STATUS_WARNING}

    def get_absolute_url(self):
        return reverse("compressor:results", args=[self.pk])


class CompressedFile(models.Model):
    compression_job = models.OneToOneField(
        CompressionJob, on_delete=models.CASCADE, related_name="result"
    )
    compressed_file = models.FileField(upload_to=compressed_upload_to)
    compressed_size = models.BigIntegerField(default=0)
    compression_percentage = models.FloatField(default=0.0)
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Result for job #{self.compression_job_id}"

    @property
    def compressed_size_display(self):
        return bytes_to_human(self.compressed_size)

    @property
    def original_size(self):
        return self.compression_job.uploaded_file.original_size

    @property
    def saved_bytes(self):
        return max(self.original_size - self.compressed_size, 0)

    @property
    def saved_display(self):
        return bytes_to_human(self.saved_bytes)


def detect_category(filename, mime_type=""):
    """Return the storage category for a filename/mime pair."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext in IMAGE_EXTENSIONS or (mime_type or "").startswith("image/"):
        return UploadedFile.CATEGORY_IMAGE
    if ext in DOCUMENT_EXTENSIONS:
        return UploadedFile.CATEGORY_DOCUMENT
    return UploadedFile.CATEGORY_OTHER
