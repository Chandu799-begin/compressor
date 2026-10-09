"""Views for the compressor application (pages + AJAX API)."""
from __future__ import annotations

import hashlib
import io
import json
import mimetypes
import os
import zipfile

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import CompressedFile, CompressionJob, UploadedFile, detect_category
from .services.size_converter import bytes_to_human, filename_for, parse_target_size
from .services.dispatcher import SUPPORTED_EXTENSIONS, is_supported
from .tasks import run_compression_job
from .validators import validate_content, validate_extension, validate_size

try:
    from django_ratelimit.decorators import ratelimit
except Exception:  # pragma: no cover - optional dependency
    def ratelimit(*args, **kwargs):
        def decorator(func):
            return func
        return decorator


# ---------------------------------------------------------------------------
# Ownership helpers
# ---------------------------------------------------------------------------
def remember_upload(request, upload):
    ids = request.session.get("upload_ids", [])
    if upload.pk not in ids:
        ids.append(upload.pk)
        request.session["upload_ids"] = ids[-200:]


def owned_uploads(request):
    session_ids = request.session.get("upload_ids", [])
    if request.user.is_authenticated:
        return UploadedFile.objects.filter(Q(user=request.user) | Q(pk__in=session_ids))
    return UploadedFile.objects.filter(pk__in=session_ids)


def owned_jobs(request):
    session_ids = request.session.get("upload_ids", [])
    if request.user.is_authenticated:
        return CompressionJob.objects.filter(
            Q(uploaded_file__user=request.user) | Q(uploaded_file_id__in=session_ids)
        )
    return CompressionJob.objects.filter(uploaded_file_id__in=session_ids)


def can_access_job(request, job):
    if request.user.is_authenticated and job.uploaded_file.user_id == request.user.id:
        return True
    return job.uploaded_file_id in request.session.get("upload_ids", [])


def _sha256(path, chunk_size=1024 * 1024):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def serialize_job(job):
    result = getattr(job, "result", None)
    upload = job.uploaded_file
    data = {
        "id": job.pk,
        "status": job.status,
        "status_display": job.get_status_display(),
        "message": job.message,
        "processing_time": job.processing_time,
        "filename": upload.filename,
        "file_type": upload.file_type,
        "category": upload.category,
        "original_size": upload.original_size,
        "original_size_display": bytes_to_human(upload.original_size),
        "target_size": job.target_size_bytes,
        "target_size_display": job.target_size_display,
        "compression_level": job.compression_level,
        "created_at": job.created_at.isoformat(),
        "results_url": reverse("compressor:results", args=[job.pk]),
        "original_url": reverse("compressor:preview_original", args=[upload.pk]),
    }
    if result:
        data.update(
            {
                "compressed_size": result.compressed_size,
                "compressed_size_display": bytes_to_human(result.compressed_size),
                "percentage": round(result.compression_percentage, 2),
                "saved_display": result.saved_display,
                "achieved": job.status != CompressionJob.STATUS_WARNING,
                "download_url": reverse("compressor:download", args=[job.pk]),
                "preview_url": reverse("compressor:preview", args=[job.pk])
                if upload.is_image
                else None,
                "width": result.width,
                "height": result.height,
            }
        )
    return data


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def home(request):
    recent = owned_jobs(request).select_related("uploaded_file", "result")[:6]
    return render(request, "home.html", {"recent_jobs": recent})


def image_compressor_page(request):
    return render(request, "image_compressor.html", {"tab": "image"})


def document_compressor_page(request):
    return render(request, "document_compressor.html", {"tab": "document"})


@login_required
def dashboard(request):
    jobs = owned_jobs(request).select_related("uploaded_file", "result")
    paginator = Paginator(jobs, 10)
    page = paginator.get_page(request.GET.get("page"))
    total_original = jobs.aggregate(total=Sum("uploaded_file__original_size"))["total"] or 0
    stats = {
        "total_jobs": jobs.count(),
        "completed": jobs.filter(status__in=[CompressionJob.STATUS_COMPLETED, CompressionJob.STATUS_WARNING]).count(),
        "failed": jobs.filter(status=CompressionJob.STATUS_FAILED).count(),
        "original_bytes_display": bytes_to_human(total_original),
    }
    return render(request, "dashboard.html", {"page_obj": page, "stats": stats})


def results(request, pk):
    job = get_object_or_404(CompressionJob.objects.select_related("uploaded_file", "result"), pk=pk)
    if not can_access_job(request, job):
        raise Http404("Not found")
    return render(request, "results.html", {"job": job})


# ---------------------------------------------------------------------------
# AJAX upload
# ---------------------------------------------------------------------------
@require_POST
def upload_file(request):
    uploaded = request.FILES.get("file")
    if not uploaded:
        return JsonResponse({"error": "No file was provided."}, status=400)
    try:
        extension = validate_extension(uploaded.name)
        validate_size(uploaded.size)
    except Exception as exc:  # ValidationError
        return JsonResponse({"error": str(exc)}, status=400)

    mime_type = uploaded.content_type or mimetypes.guess_type(uploaded.name)[0] or ""
    category = detect_category(uploaded.name, mime_type)

    record = UploadedFile(
        user=request.user if request.user.is_authenticated else None,
        filename=os.path.basename(uploaded.name),
        original_size=uploaded.size,
        mime_type=mime_type,
        category=category,
        file_type=(mimetypes.guess_type(uploaded.name)[0] or extension.lstrip(".")).split("/")[-1],
    )
    record.original_file.save(uploaded.name, uploaded, save=False)
    record.save()

    try:
        validate_content(record.original_file.path, extension)
    except Exception as exc:
        record.original_file.delete(save=False)
        record.delete()
        return JsonResponse({"error": str(exc)}, status=400)

    record.checksum = _sha256(record.original_file.path)
    record.save(update_fields=["checksum"])
    remember_upload(request, record)

    return JsonResponse(
        {
            "id": record.pk,
            "filename": record.filename,
            "size": record.original_size,
            "size_display": record.original_size_display,
            "category": record.category,
            "file_type": record.file_type,
            "supported": extension in SUPPORTED_EXTENSIONS,
            "preview_url": reverse("compressor:preview_original", args=[record.pk])
            if record.is_image
            else None,
        }
    )


@require_POST
def chunk_upload(request):
    """Receive a single chunk of a chunked (GB-sized) upload."""
    file_id = request.POST.get("upload_id") or request.POST.get("file_id")
    chunk_index = int(request.POST.get("chunk_index", 0))
    total_chunks = int(request.POST.get("total_chunks", 1))
    filename = os.path.basename(request.POST.get("filename", "upload.bin"))
    chunk = request.FILES.get("chunk")

    if not chunk or not file_id:
        return JsonResponse({"error": "Missing chunk or upload id."}, status=400)

    try:
        extension = validate_extension(filename)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    temp_dir = os.path.join(settings.MEDIA_ROOT, "uploads", "chunks", file_id)
    os.makedirs(temp_dir, exist_ok=True)
    part_path = os.path.join(temp_dir, f"{chunk_index:08d}.part")
    with open(part_path, "wb") as handle:
        for piece in chunk.chunks():
            handle.write(piece)

    if chunk_index + 1 >= total_chunks:
        return _finalize_chunked_upload(request, file_id, filename, extension, total_chunks)
    return JsonResponse({"status": "partial", "received": chunk_index + 1, "total": total_chunks})


def _finalize_chunked_upload(request, file_id, filename, extension, total_chunks):
    temp_dir = os.path.join(settings.MEDIA_ROOT, "uploads", "chunks", file_id)
    total_size = 0
    try:
        validate_size(sum(os.path.getsize(os.path.join(temp_dir, f)) for f in os.listdir(temp_dir)))
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    record = UploadedFile(
        user=request.user if request.user.is_authenticated else None,
        filename=filename,
        category=detect_category(filename),
        mime_type=mimetypes.guess_type(filename)[0] or "",
        file_type=(mimetypes.guess_type(filename)[0] or extension.lstrip(".")).split("/")[-1],
    )
    target = record.original_file.field.generate_filename(record, filename)
    absolute_target = os.path.join(settings.MEDIA_ROOT, target)
    os.makedirs(os.path.dirname(absolute_target), exist_ok=True)
    with open(absolute_target, "wb") as out:
        for index in range(total_chunks):
            part = os.path.join(temp_dir, f"{index:08d}.part")
            with open(part, "rb") as handle:
                while True:
                    buffer = handle.read(1024 * 1024)
                    if not buffer:
                        break
                    out.write(buffer)
                    total_size += len(buffer)

    record.original_file.name = target
    record.original_size = total_size
    record.save()

    try:
        validate_content(record.original_file.path, extension)
    except Exception as exc:
        record.original_file.delete(save=False)
        record.delete()
        return JsonResponse({"error": str(exc)}, status=400)

    record.checksum = _sha256(record.original_file.path)
    record.save(update_fields=["checksum"])
    remember_upload(request, record)

    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)

    return JsonResponse(
        {
            "id": record.pk,
            "filename": record.filename,
            "size": record.original_size,
            "size_display": record.original_size_display,
            "category": record.category,
        }
    )


# ---------------------------------------------------------------------------
# Compression
# ---------------------------------------------------------------------------
@require_POST
@ratelimit(key="user_or_ip", rate=settings.RATELIMIT_COMPRESS, method="POST", block=True)
def compress_files(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = request.POST.dict()

    upload_ids = payload.get("upload_ids") or ([payload.get("upload_id")] if payload.get("upload_id") else [])
    if not upload_ids:
        return JsonResponse({"error": "Select at least one file to compress."}, status=400)

    target_value = payload.get("target_value")
    target_unit = payload.get("target_unit", "KB")
    target_bytes = parse_target_size(target_value, target_unit)
    level = payload.get("level", CompressionJob.LEVEL_MEDIUM)
    if level not in dict(CompressionJob.LEVEL_CHOICES):
        level = CompressionJob.LEVEL_MEDIUM

    options = {
        "max_width": _as_int(payload.get("max_width")),
        "max_height": _as_int(payload.get("max_height")),
        "keep_aspect": _as_bool(payload.get("keep_aspect"), True),
        "strip_metadata": _as_bool(payload.get("strip_metadata"), False),
        "convert_to_webp": _as_bool(payload.get("convert_to_webp"), False),
        "output_format": (payload.get("output_format") or "auto"),
        "downsample": _as_bool(payload.get("downsample"), True),
        "use_ghostscript": _as_bool(payload.get("use_ghostscript"), False),
    }

    uploads = owned_uploads(request).filter(pk__in=upload_ids)
    if not uploads.exists():
        return JsonResponse({"error": "No accessible files were found."}, status=404)

    created_jobs = []
    for upload in uploads:
        if not is_supported(upload.filename):
            continue
        job = CompressionJob.objects.create(
            uploaded_file=upload,
            target_size_bytes=target_bytes,
            compression_level=level,
            options=options,
            status=CompressionJob.STATUS_PENDING,
        )
        created_jobs.append(job)

    # Dispatch tasks (runs inline when CELERY_TASK_ALWAYS_EAGER is enabled).
    for job in created_jobs:
        try:
            run_compression_job.delay(job.pk)
        except Exception:
            # Broker unavailable - fall back to synchronous processing.
            from .services.dispatcher import process_job

            process_job(job)

    refreshed = [
        CompressionJob.objects.select_related("uploaded_file", "result").get(pk=job.pk)
        for job in created_jobs
    ]

    response = JsonResponse({"jobs": [serialize_job(job) for job in refreshed]})
    if target_bytes:
        response.set_cookie("pref_target_unit", target_unit, max_age=60 * 60 * 24 * 365)
        response.set_cookie("pref_target_value", str(target_value), max_age=60 * 60 * 24 * 365)
    response.set_cookie("pref_level", level, max_age=60 * 60 * 24 * 365)
    return response


def _as_int(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@require_GET
def job_status(request, pk):
    job = get_object_or_404(CompressionJob.objects.select_related("uploaded_file", "result"), pk=pk)
    if not can_access_job(request, job):
        raise Http404("Not found")
    return JsonResponse(serialize_job(job))


@require_GET
def job_list(request):
    jobs = owned_jobs(request).select_related("uploaded_file", "result")[:50]
    return JsonResponse({"jobs": [serialize_job(job) for job in jobs]})


# ---------------------------------------------------------------------------
# Secure serving / download
# ---------------------------------------------------------------------------
def _file_response(path, filename, as_attachment, content_type=None):
    if not path or not os.path.exists(path):
        raise Http404("File not found.")
    response = FileResponse(open(path, "rb"), as_attachment=as_attachment, filename=filename)
    if content_type:
        response["Content-Type"] = content_type
    return response


def preview_original(request, pk):
    upload = get_object_or_404(UploadedFile, pk=pk)
    session_ids = request.session.get("upload_ids", [])
    if not (request.user.is_authenticated and upload.user_id == request.user.id) and upload.pk not in session_ids:
        raise Http404("Not found")
    return _file_response(upload.original_file.path, upload.filename, as_attachment=False)


def preview(request, pk):
    job = get_object_or_404(CompressionJob.objects.select_related("result", "uploaded_file"), pk=pk)
    if not can_access_job(request, job) or not hasattr(job, "result"):
        raise Http404("Not found")
    result = job.result
    filename = filename_for(job.uploaded_file.filename, "compressed", os.path.splitext(result.compressed_file.name)[1])
    return _file_response(result.compressed_file.path, filename, as_attachment=False)


def download_file(request, pk):
    job = get_object_or_404(CompressionJob.objects.select_related("result", "uploaded_file"), pk=pk)
    if not can_access_job(request, job) or not hasattr(job, "result"):
        raise Http404("Not found")
    result = job.result
    extension = os.path.splitext(result.compressed_file.name)[1]
    filename = filename_for(job.uploaded_file.filename, "compressed", extension)
    return _file_response(result.compressed_file.path, filename, as_attachment=True)


@require_POST
def download_all(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = request.POST.dict()
    job_ids = payload.get("job_ids") or []

    jobs = owned_jobs(request).filter(pk__in=job_ids, result__isnull=False).select_related("uploaded_file", "result")
    if not jobs.exists():
        return JsonResponse({"error": "No compressed files to download."}, status=404)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for job in jobs:
            result = job.result
            extension = os.path.splitext(result.compressed_file.name)[1]
            archive.write(result.compressed_file.path, arcname=filename_for(job.uploaded_file.filename, "compressed", extension))
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="smartcompress_{timezone.now():%Y%m%d_%H%M%S}.zip"'
    return response


# ---------------------------------------------------------------------------
# History management
# ---------------------------------------------------------------------------
@require_POST
def delete_job(request, pk):
    job = get_object_or_404(CompressionJob, pk=pk)
    if not can_access_job(request, job):
        raise Http404("Not found")
    if hasattr(job, "result"):
        job.result.compressed_file.delete(save=False)
    job.uploaded_file.original_file.delete(save=False)
    job.delete()
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"status": "deleted"})
    messages.success(request, "Item deleted.")
    return redirect("compressor:dashboard")


@require_POST
def clear_history(request):
    jobs = owned_jobs(request)
    for job in jobs:
        if hasattr(job, "result"):
            job.result.compressed_file.delete(save=False)
        job.uploaded_file.original_file.delete(save=False)
    jobs.delete()
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"status": "cleared"})
    messages.success(request, "History cleared.")
    return redirect("compressor:dashboard")
