"""Admin configuration for the compressor app."""
from django.contrib import admin
from django.utils.html import format_html

from .models import CompressedFile, CompressionJob, UploadedFile


@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ("filename", "category", "file_type", "original_size_display", "user", "uploaded_at")
    list_filter = ("category", "file_type", "uploaded_at")
    search_fields = ("filename", "checksum")
    date_hierarchy = "uploaded_at"
    readonly_fields = ("original_size", "checksum", "uploaded_at")


@admin.register(CompressionJob)
class CompressionJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "uploaded_file",
        "compression_level",
        "target_size_display",
        "status",
        "processing_time",
        "created_at",
    )
    list_filter = ("status", "compression_level", "created_at")
    search_fields = ("uploaded_file__filename",)
    date_hierarchy = "created_at"
    readonly_fields = ("created_at", "completed_at", "processing_time", "celery_task_id")


@admin.register(CompressedFile)
class CompressedFileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "compression_job",
        "compressed_size_display",
        "compression_percentage",
        "created_at",
    )
    list_filter = ("created_at",)
    readonly_fields = ("created_at", "width", "height")

    @admin.display(description="Savings")
    def savings(self, obj):
        return format_html("<b>{}%</b>", obj.compression_percentage)
