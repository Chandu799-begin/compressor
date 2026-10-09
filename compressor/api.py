"""Django REST Framework API for SmartCompress Pro."""
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import CompressionJob, UploadedFile
from .serializers import (
    CompressionJobSerializer,
    CompressionRequestSerializer,
    UploadedFileSerializer,
)
from .services.size_converter import parse_target_size
from .tasks import run_compression_job
from .validators import validate_content, validate_extension, validate_size


class UploadedFileViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = UploadedFileSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        return UploadedFile.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        upload = request.FILES.get("file")
        if not upload:
            return Response({"error": "No file provided."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            extension = validate_extension(upload.name)
            validate_size(upload.size)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        record = UploadedFile.objects.create(
            user=request.user,
            original_file=upload,
            filename=upload.name,
            original_size=upload.size,
        )
        try:
            validate_content(record.original_file.path, extension)
        except Exception as exc:
            record.original_file.delete(save=False)
            record.delete()
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(record)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CompressionJobViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = CompressionJobSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            CompressionJob.objects.filter(uploaded_file__user=self.request.user)
            .select_related("uploaded_file", "result")
        )

    @action(detail=False, methods=["post"], url_path="compress")
    def compress(self, request):
        serializer = CompressionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        target_bytes = parse_target_size(data.get("target_value"), data.get("target_unit"))
        options = {
            "max_width": data.get("max_width"),
            "max_height": data.get("max_height"),
            "keep_aspect": data.get("keep_aspect", True),
            "strip_metadata": data.get("strip_metadata", False),
            "convert_to_webp": data.get("convert_to_webp", False),
            "output_format": data.get("output_format") or "auto",
            "downsample": data.get("downsample", True),
            "use_ghostscript": data.get("use_ghostscript", False),
        }

        uploads = UploadedFile.objects.filter(user=request.user, pk__in=data["upload_ids"])
        jobs = []
        for upload in uploads:
            job = CompressionJob.objects.create(
                uploaded_file=upload,
                target_size_bytes=target_bytes,
                compression_level=data["level"],
                options=options,
            )
            run_compression_job.delay(job.pk)
            jobs.append(job)

        jobs = CompressionJob.objects.filter(pk__in=[j.pk for j in jobs]).select_related("uploaded_file", "result")
        return Response({"jobs": CompressionJobSerializer(jobs, many=True).data})

    @action(detail=True, methods=["get"])
    def status(self, request, pk=None):
        job = self.get_object()
        return Response(CompressionJobSerializer(job).data)

    def perform_destroy(self, instance):
        if hasattr(instance, "result"):
            instance.result.compressed_file.delete(save=False)
        instance.uploaded_file.original_file.delete(save=False)
        instance.delete()
