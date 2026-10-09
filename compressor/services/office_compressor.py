"""Office document (DOCX / XLSX / PPTX) compression.

These formats are Open Packaging Convention (OPC) ZIP archives.  We rebuild
the archive while re-encoding the embedded media images inside each package.
Paragraphs, tables, formulas, slides, layouts and all XML parts are copied
byte-for-byte, so formatting is preserved.
"""
from __future__ import annotations

import io
import os
import shutil
import zipfile

from PIL import Image

from .size_converter import LEVEL_PRESETS

try:
    Image.MAX_IMAGE_PIXELS = 80_000_000
except Exception:  # pragma: no cover
    pass

MEDIA_PREFIXES = ("word/media/", "xl/media/", "ppt/media/")
RASTER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}
SKIP_EXTENSIONS = {".emf", ".wmf", ".svg", ".gif"}

_QUALITY_ATTEMPTS = [85, 75, 65, 55, 45, 35]


class OfficeCompressionError(Exception):
    pass


def _is_media(name):
    lowered = name.lower()
    return any(lowered.startswith(prefix) for prefix in MEDIA_PREFIXES)


def _recompress_image(raw, extension, quality, max_dimension=None):
    with Image.open(io.BytesIO(raw)) as img:
        img.load()
        fmt = (img.format or "").upper()
        if extension in (".png",) or fmt == "PNG":
            if max_dimension and max(img.size) > max_dimension:
                ratio = max_dimension / float(max(img.size))
                img = img.resize(
                    (max(1, int(img.width * ratio)), max(1, int(img.height * ratio))),
                    Image.LANCZOS,
                )
            buffer = io.BytesIO()
            if img.mode in ("RGBA", "LA", "P"):
                img.convert("RGBA").save(buffer, format="PNG", optimize=True, compress_level=9)
            else:
                img.convert("RGB").save(buffer, format="PNG", optimize=True, compress_level=9)
            return buffer.getvalue()
        # JPEG / WEBP / BMP / TIFF -> encode as JPEG to maximise savings
        buffer = io.BytesIO()
        if max_dimension and max(img.size) > max_dimension:
            ratio = max_dimension / float(max(img.size))
            img = img.resize(
                (max(1, int(img.width * ratio)), max(1, int(img.height * ratio))),
                Image.LANCZOS,
            )
        rgb = img.convert("RGB")
        rgb.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
        return buffer.getvalue()


def _rebuild_package(input_path, output_path, quality, max_dimension=None):
    with zipfile.ZipFile(input_path, "r") as source:
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as target:
            for item in source.infolist():
                raw = source.read(item.filename)
                extension = os.path.splitext(item.filename)[1].lower()
                if _is_media(item.filename) and extension in RASTER_EXTENSIONS and extension not in SKIP_EXTENSIONS:
                    try:
                        recompressed = _recompress_image(raw, extension, quality, max_dimension)
                        if len(recompressed) < len(raw):
                            raw = recompressed
                    except Exception:
                        pass  # keep the original bytes on any decode issue
                target.writestr(item, raw)


def compress_office(input_path, output_path, target_bytes=None, level="medium"):
    """Compress a DOCX/XLSX/PPTX package and return a result dict."""
    if not os.path.exists(input_path):
        raise OfficeCompressionError("Input file does not exist.")
    if not zipfile.is_zipfile(input_path):
        raise OfficeCompressionError("Not a valid Office (Open XML) file.")

    original_size = os.path.getsize(input_path)
    params = LEVEL_PRESETS.get(level, LEVEL_PRESETS["medium"])
    warning = ""

    if target_bytes and original_size <= target_bytes:
        shutil.copyfile(input_path, output_path)
        return _result(original_size, original_size, target_bytes, True, "")

    start_quality = params["quality"]
    attempts = [start_quality] + [q for q in _QUALITY_ATTEMPTS if q < start_quality]
    best_path = output_path + ".best"
    best_size = None
    achieved = True

    for quality in attempts:
        _rebuild_package(input_path, output_path, quality)
        size = os.path.getsize(output_path)
        if best_size is None or size < best_size:
            shutil.copyfile(output_path, best_path)
            best_size = size
        if not target_bytes or size <= target_bytes:
            if os.path.exists(best_path):
                os.remove(best_path)
            if size >= original_size:
                shutil.copyfile(input_path, output_path)
                size = original_size
            return _result(original_size, size, target_bytes, True, warning)

    # Strength exhausted - keep the smallest result.
    shutil.move(best_path, output_path)
    size = os.path.getsize(output_path)
    if size >= original_size:
        shutil.copyfile(input_path, output_path)
        size = original_size
        achieved = True
    else:
        achieved = False
        warning = (
            "This document could not reach the requested target size without "
            "unacceptable quality loss. The smallest safe version was generated."
        )
    return _result(original_size, size, target_bytes, achieved, warning)


def _result(original_size, compressed_size, target_bytes, achieved, warning):
    saved = max(original_size - compressed_size, 0)
    percentage = (saved / original_size * 100) if original_size else 0.0
    return {
        "original_size": original_size,
        "compressed_size": compressed_size,
        "saved_bytes": saved,
        "savings_percent": round(percentage, 2),
        "target_bytes": target_bytes,
        "achieved_target": achieved,
        "warning": warning,
    }
