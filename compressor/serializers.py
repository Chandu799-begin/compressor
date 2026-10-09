"""DRF serializers for the compressor REST API."""
from rest_framework import serializers

from .models import CompressedFile, CompressionJob, UploadedFile


class UploadedFileSerializer(serializers.ModelSerializer):
    size_display = serializers.CharField(source="original_size_display", read_only=True)

    class Meta:
        model = UploadedFile
        fields = [
            "id",
            "filename",
            "file_type",
            "mime_type",
            "category",
            "original_size",
            "size_display",
            "uploaded_at",
        ]
        read_only_fields = ["id", "uploaded_at", "original_size"]


class CompressedFileSerializer(serializers.ModelSerializer):
    compressed_size_display = serializers.CharField(read_only=True)
    original_size = serializers.IntegerField(read_only=True)
    saved_display = serializers.CharField(read_only=True)

    class Meta:
        model = CompressedFile
        fields = [
            "id",
            "compressed_size",
            "compressed_size_display",
            "original_size",
            "saved_display",
            "compression_percentage",
            "width",
            "height",
            "created_at",
        ]


class CompressionJobSerializer(serializers.ModelSerializer):
    uploaded_file = UploadedFileSerializer(read_only=True)
    result = CompressedFileSerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    target_size_display = serializers.CharField(read_only=True)

    class Meta:
        model = CompressionJob
        fields = [
            "id",
            "uploaded_file",
            "target_size_bytes",
            "target_size_display",
            "compression_level",
            "status",
            "status_display",
            "message",
            "processing_time",
            "result",
            "created_at",
            "completed_at",
        ]


class CompressionRequestSerializer(serializers.Serializer):
    upload_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    target_value = serializers.FloatField(required=False, allow_null=True)
    target_unit = serializers.ChoiceField(choices=["KB", "MB", "GB"], default="KB")
    level = serializers.ChoiceField(choices=[c[0] for c in CompressionJob.LEVEL_CHOICES], default="medium")
    max_width = serializers.IntegerField(required=False, allow_null=True)
    max_height = serializers.IntegerField(required=False, allow_null=True)
    keep_aspect = serializers.BooleanField(required=False, default=True)
    strip_metadata = serializers.BooleanField(required=False, default=False)
    convert_to_webp = serializers.BooleanField(required=False, default=False)
    output_format = serializers.CharField(required=False, allow_blank=True, default="auto")
    downsample = serializers.BooleanField(required=False, default=True)
    use_ghostscript = serializers.BooleanField(required=False, default=False)
