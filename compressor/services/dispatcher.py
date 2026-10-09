"""Route uploaded files to the correct compression service and persist results."""
from __future__ import annotations

import os
import time
import uuid

from django.conf import settings
from django.utils import timezone

from .converter import (
    ConversionError,
    convert_document,
    normalize_document_format,
    normalize_image_format,
)
from .image_compressor import ImageCompressionError, compress_image
from .office_compressor import OfficeCompressionError, compress_office
from .pdf_compressor import PDFCompressionError, compress_pdf
from .size_converter import bytes_to_human

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff"}
PDF_EXTENSIONS = {".pdf"}
OFFICE_EXTENSIONS = {".docx", ".xlsx", ".pptx"}
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | PDF_EXTENSIONS | OFFICE_EXTENSIONS


def is_supported(filename):
    return os.path.splitext(filename or "")[1].lower() in SUPPORTED_EXTENSIONS


def resolve_image_extension(extension, options):
    """Return the output extension for an image (honours output_format)."""
    fmt = normalize_image_format(options.get("output_format"))
    if fmt is None and options.get("convert_to_webp"):
        fmt = "webp"
    if fmt:
        return "." + fmt
    return extension


def resolve_document_extension(extension, options):
    """Return the target extension for a document (same as input when auto)."""
    fmt = normalize_document_format(options.get("output_format"))
    if fmt and ("." + fmt) != extension:
        return "." + fmt
    return extension


def compress_file(input_path, output_path, extension, target_bytes=None, level="medium", options=None):
    """Dispatch compression by extension. Returns a result dict."""
    options = options or {}
    if extension in IMAGE_EXTENSIONS:
        return compress_image(
            input_path,
            output_path,
            target_bytes=target_bytes,
            level=level,
            max_width=options.get("max_width"),
            max_height=options.get("max_height"),
            keep_aspect=options.get("keep_aspect", True),
            strip_metadata=options.get("strip_metadata", False),
            convert_to_webp=normalize_image_format(options.get("output_format")) == "webp"
            or options.get("convert_to_webp", False),
        )
    if extension in PDF_EXTENSIONS:
        return compress_pdf(
            input_path,
            output_path,
            target_bytes=target_bytes,
            level=level,
            downsample=options.get("downsample", True),
            use_ghostscript=options.get("use_ghostscript", False),
        )
    if extension in OFFICE_EXTENSIONS:
        return compress_office(input_path, output_path, target_bytes=target_bytes, level=level)
    raise ValueError(f"Unsupported file type: {extension}")


def process_job(job):
    """Run a compression job end to end and persist the ``CompressedFile``.

    Handles optional format conversion:
      * Images  -> JPG / PNG / WEBP / BMP / TIFF (Pillow).
      * Documents -> PDF / DOCX / XLSX / PPTX (LibreOffice, when installed).
    """
    from compressor.models import CompressedFile

    upload = job.uploaded_file
    input_path = upload.original_file.path
    extension = upload.extension
    options = job.options or {}

    job.status = job.STATUS_PROCESSING
    job.message = ""
    job.save(update_fields=["status", "message"])

    started = time.perf_counter()
    converted_path = None
    try:
        if upload.is_image:
            out_ext = resolve_image_extension(extension, options)
            working_input = input_path
            compress_ext = extension
        else:
            out_ext = resolve_document_extension(extension, options)
            if out_ext != extension:
                converted_path = convert_document(input_path, out_ext.lstrip("."))
                working_input = converted_path
                compress_ext = out_ext
            else:
                working_input = input_path
                compress_ext = extension

        now = timezone.now()
        relative_dir = f"compressed/{now:%Y/%m}"
        absolute_dir = os.path.join(settings.MEDIA_ROOT, relative_dir)
        os.makedirs(absolute_dir, exist_ok=True)
        filename = f"{uuid.uuid4().hex}{out_ext}"
        output_path = os.path.join(absolute_dir, filename)

        result = compress_file(
            working_input,
            output_path,
            compress_ext,
            target_bytes=job.target_size_bytes,
            level=job.compression_level,
            options=options,
        )

        elapsed = time.perf_counter() - started
        compressed_size = result.get("compressed_size") or os.path.getsize(output_path)
        percentage = result.get("savings_percent", 0.0)

        relative_path = f"{relative_dir}/{filename}".replace("\\", "/")

        CompressedFile.objects.update_or_create(
            compression_job=job,
            defaults={
                "compressed_file": relative_path,
                "compressed_size": compressed_size,
                "compression_percentage": percentage,
                "width": result.get("width"),
                "height": result.get("height"),
            },
        )

        job.processing_time = round(elapsed, 3)
        job.completed_at = timezone.now()
        warning = result.get("warning") or ""
        if warning and not result.get("achieved_target", True):
            job.status = job.STATUS_WARNING
        else:
            job.status = job.STATUS_COMPLETED

        converted_note = ""
        if normalized := normalize_document_format(options.get("output_format")):
            if ("." + normalized) != extension:
                converted_note = f"Converted {extension.lstrip('.').upper()} → {normalized.upper()}. "
        elif upload.is_image:
            image_fmt = normalize_image_format(options.get("output_format"))
            if image_fmt and ("." + image_fmt) != extension:
                converted_note = f"Converted {extension.lstrip('.').upper()} → {image_fmt.upper()}. "

        job.message = warning or (
            f"{converted_note}Compressed to {bytes_to_human(compressed_size)} "
            f"({percentage:.1f}% smaller)."
        )
        job.save()
        return result

    except (
        ImageCompressionError,
        PDFCompressionError,
        OfficeCompressionError,
        ConversionError,
        ValueError,
        OSError,
    ) as exc:
        job.status = job.STATUS_FAILED
        job.processing_time = round(time.perf_counter() - started, 3)
        job.message = str(exc)
        job.completed_at = timezone.now()
        job.save()
        return {"error": str(exc)}
    finally:
        if converted_path and os.path.exists(converted_path):
            try:
                os.remove(converted_path)
            except OSError:
                pass
