"""Upload validation helpers: extension, MIME type and magic-number checks."""
import os
import zipfile

from django.conf import settings
from django.core.exceptions import ValidationError

from .services.dispatcher import SUPPORTED_EXTENSIONS

MAGIC_SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
    b"BM": "image/bmp",
    b"II*\x00": "image/tiff",
    b"MM\x00*": "image/tiff",
    b"%PDF": "application/pdf",
    b"PK\x03\x04": "application/zip",
}


def _read_head(path, size=16):
    with open(path, "rb") as handle:
        return handle.read(size)


def detect_magic(path):
    head = _read_head(path, 16)
    for signature, mime in MAGIC_SIGNATURES.items():
        if head.startswith(signature):
            return mime
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return ""


def validate_extension(filename):
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValidationError(
            f"Unsupported file type '{ext or 'unknown'}'. "
            f"Allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))}."
        )
    return ext


def validate_size(size):
    if size and size > settings.MAX_UPLOAD_SIZE:
        limit = settings.MAX_UPLOAD_SIZE // (1024 * 1024)
        raise ValidationError(f"File exceeds the maximum upload size of {limit} MB.")
    if not size:
        raise ValidationError("The uploaded file is empty.")


def validate_content(path, extension):
    """Validate that the file content matches its extension."""
    magic = detect_magic(path)
    if not magic:
        raise ValidationError("The file content could not be recognised.")

    if extension in {".jpg", ".jpeg"} and magic != "image/jpeg":
        raise ValidationError("The file is not a valid JPEG image.")
    if extension == ".png" and magic != "image/png":
        raise ValidationError("The file is not a valid PNG image.")
    if extension == ".webp" and magic != "image/webp":
        raise ValidationError("The file is not a valid WEBP image.")
    if extension == ".gif" and magic != "image/gif":
        raise ValidationError("The file is not a valid GIF image.")
    if extension == ".bmp" and magic != "image/bmp":
        raise ValidationError("The file is not a valid BMP image.")
    if extension == ".tiff" and magic != "image/tiff":
        raise ValidationError("The file is not a valid TIFF image.")
    if extension == ".pdf" and magic != "application/pdf":
        raise ValidationError("The file is not a valid PDF.")
    if extension in {".docx", ".xlsx", ".pptx"}:
        if magic != "application/zip" or not zipfile.is_zipfile(path):
            raise ValidationError("The file is not a valid Office document.")
    return True
