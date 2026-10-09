"""Format conversion helpers for images and documents.

Image format conversion is handled natively by Pillow (see the image
compressor).  Document format conversion (e.g. DOCX -> PDF) requires
LibreOffice in headless mode; when it is not installed the converter raises a
clear, user-facing error instead of silently pretending to convert.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from django.conf import settings

# Friendly name -> canonical extension
IMAGE_OUTPUT_FORMATS = {"jpg", "jpeg", "png", "webp", "bmp", "tiff"}
DOCUMENT_OUTPUT_FORMATS = {"pdf", "docx", "xlsx", "pptx"}


class ConversionError(Exception):
    """Raised when a requested conversion cannot be produced."""


class ConversionUnavailable(ConversionError):
    """Raised when the converter engine (LibreOffice) is not installed."""


def normalize_image_format(value):
    """Return a canonical image extension (``jpg``/``png``/...) or ``None``."""
    if not value or str(value).lower() in {"auto", "original", "keep", "none"}:
        return None
    fmt = str(value).lower().lstrip(".")
    if fmt == "jpeg":
        fmt = "jpg"
    return fmt if fmt in IMAGE_OUTPUT_FORMATS else None


def normalize_document_format(value):
    """Return a canonical document extension or ``None``."""
    if not value or str(value).lower() in {"auto", "original", "keep", "none"}:
        return None
    fmt = str(value).lower().lstrip(".")
    return fmt if fmt in DOCUMENT_OUTPUT_FORMATS else None


def find_soffice():
    """Locate the LibreOffice ``soffice`` binary, if present."""
    candidates = [
        getattr(settings, "LIBREOFFICE_BINARY", ""),
        "soffice",
        "soffice.exe",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/usr/bin/soffice",
        "/usr/local/bin/soffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        resolved = shutil.which(candidate) if os.path.sep not in candidate else (
            candidate if os.path.exists(candidate) else None
        )
        if resolved:
            return resolved
    return None


def conversion_available():
    return find_soffice() is not None


# LibreOffice's filter names for office targets.
_SOFFICE_TARGETS = {
    "pdf": "pdf",
    "docx": 'docx:"MS Word 2007 XML"',
    "xlsx": 'xlsx:"Calc MS Excel 2007 XML"',
    "pptx": 'pptx:"Impress MS PowerPoint 2007 XML"',
}


def convert_document(input_path, target_format, workdir=None):
    """Convert an Office/PDF document to ``target_format`` using LibreOffice.

    Returns the path to the converted file.  Raises ``ConversionUnavailable``
    when LibreOffice is missing and ``ConversionError`` when it fails.
    """
    target = normalize_document_format(target_format)
    if not target:
        raise ConversionError(f"Unsupported target format: {target_format}")

    soffice = find_soffice()
    if not soffice:
        raise ConversionUnavailable(
            "Document format conversion requires LibreOffice. Install it and set "
            "LIBREOFFICE_BINARY (or add soffice to your PATH) to enable PDF/DOCX/"
            "XLSX/PPTX conversion."
        )

    workdir = workdir or tempfile.mkdtemp(prefix="sc-convert-")
    target_arg = _SOFFICE_TARGETS.get(target, target)
    output_ext = "." + target
    command = [
        soffice,
        "--headless",
        "--norestore",
        "--nologo",
        "--convert-to",
        target_arg,
        "--outdir",
        workdir,
        input_path,
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=600)
    except (subprocess.SubprocessError, OSError) as exc:
        raise ConversionError(f"LibreOffice conversion failed: {exc}") from exc

    base = os.path.splitext(os.path.basename(input_path))[0]
    result = os.path.join(workdir, base + output_ext)
    if not os.path.exists(result):
        for name in os.listdir(workdir):
            if name.lower().endswith(output_ext):
                result = os.path.join(workdir, name)
                break
    if not os.path.exists(result):
        raise ConversionError(f"LibreOffice did not produce a {target.upper()} file.")
    return result
