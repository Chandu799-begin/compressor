"""PDF compression using PyMuPDF with optional Ghostscript acceleration.

Strategy:
  * Rebuild the document with ``garbage=4`` to drop unused objects.
  * Deflate content/font/image streams.
  * Optionally downsample embedded raster images (scanned pages) by
    re-encoding them as JPEG at a reduced quality/dimension.
  * Optionally hand off to Ghostscript when it is installed for the
    strongest "ebook"/"screen" style downsampling.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess

import pymupdf as fitz
from PIL import Image

from .size_converter import LEVEL_PRESETS

try:  # Pillow's decompression-bomb guard for tidy behaviour
    Image.MAX_IMAGE_PIXELS = 80_000_000
except Exception:  # pragma: no cover
    pass


class PDFCompressionError(Exception):
    pass


# (quality, max_dimension) attempts ordered from gentle to aggressive.
_IMAGE_ATTEMPTS = [
    (80, 2200),
    (65, 1800),
    (50, 1400),
    (35, 1100),
    (25, 900),
]


def _find_ghostscript(configured=""):
    for candidate in (configured, "gswin64c", "gswin32c", "gs"):
        if not candidate:
            continue
        resolved = shutil.which(candidate) if os.path.sep not in candidate else (
            candidate if os.path.exists(candidate) else None
        )
        if resolved:
            return resolved
    return None


def _save(doc, output_path, deflate_images=True):
    doc.save(
        output_path,
        garbage=4,
        deflate=True,
        deflate_images=deflate_images,
        deflate_fonts=True,
        clean=True,
        pretty=False,
    )


def _downsample_images(doc, quality, max_dimension):
    """Downsample/re-encode embedded raster images in place."""
    processed = 0
    for page in doc:
        for image_info in page.get_images(full=True):
            xref = image_info[0]
            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.width < 96 or pix.height < 96:
                    continue
                if pix.n - pix.alpha >= 4:  # CMYK / DeviceN
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                png_bytes = pix.tobytes("png")
                with Image.open(io.BytesIO(png_bytes)) as img:
                    img = img.convert("RGB")
                    if max(img.size) > max_dimension:
                        ratio = max_dimension / float(max(img.size))
                        new_size = (max(1, int(img.width * ratio)), max(1, int(img.height * ratio)))
                        img = img.resize(new_size, Image.LANCZOS)
                    if img.width < pix.width or quality < 90:
                        buffer = io.BytesIO()
                        img.save(buffer, format="JPEG", quality=quality, optimize=True)
                        if buffer.tell() < len(png_bytes):
                            page.replace_image(xref, stream=buffer.getvalue())
                            processed += 1
            except Exception:
                # Never let one odd image abort the whole compression.
                continue
    return processed


def _compress_once(input_path, output_path, downsample, quality, max_dimension, deflate_images=True):
    doc = fitz.open(input_path)
    try:
        if downsample:
            _downsample_images(doc, quality, max_dimension)
        if hasattr(doc, "subset_fonts"):
            try:
                doc.subset_fonts()
            except Exception:
                pass
        _save(doc, output_path, deflate_images=deflate_images)
    finally:
        doc.close()


def compress_with_ghostscript(input_path, output_path, level="medium", gs_binary=""):
    binary = _find_ghostscript(gs_binary)
    if not binary:
        return None
    preset = {
        "low": "/printer",
        "medium": "/ebook",
        "high": "/screen",
        "custom": "/screen",
    }.get(level, "/ebook")
    command = [
        binary,
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        f"-dPDFSETTINGS={preset}",
        "-dNOPAUSE",
        "-dQUIET",
        "-dBATCH",
        "-dDetectDuplicateImages=true",
        f"-sOutputFile={output_path}",
        input_path,
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=600)
    except (subprocess.SubprocessError, OSError):
        return None
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        return output_path
    return None


def compress_pdf(
    input_path,
    output_path,
    target_bytes=None,
    level="medium",
    downsample=True,
    use_ghostscript=False,
    gs_binary="",
):
    """Compress a PDF and return a result dict."""
    if not os.path.exists(input_path):
        raise PDFCompressionError("Input PDF does not exist.")

    original_size = os.path.getsize(input_path)
    warning = ""
    achieved = True

    if target_bytes and original_size <= target_bytes:
        shutil.copyfile(input_path, output_path)
        return _result(original_size, original_size, target_bytes, True, "")

    # Ghostscript pass (optional) - only keep it if it actually helps.
    if use_ghostscript or gs_binary:
        gs_path = output_path + ".gs.pdf"
        if compress_with_ghostscript(input_path, gs_path, level, gs_binary):
            if os.path.getsize(gs_path) < original_size:
                shutil.move(gs_path, output_path)
                size = os.path.getsize(output_path)
                if target_bytes and size > target_bytes:
                    _py_attempts(input_path, output_path, target_bytes, level, downsample)
                    size = os.path.getsize(output_path)
                    if size > target_bytes:
                        return _result(original_size, size, target_bytes, False, _warning())
                return _result(original_size, size, target_bytes, True, "")
            os.remove(gs_path)

    size = _py_attempts(input_path, output_path, target_bytes, level, downsample)
    if target_bytes and size > target_bytes:
        achieved = False
        warning = _warning()
    elif size >= original_size:
        # Compression produced no gain - keep original bytes.
        shutil.copyfile(input_path, output_path)
        size = original_size
    return _result(original_size, size, target_bytes, achieved, warning)


def _py_attempts(input_path, output_path, target_bytes, level, downsample):
    params = LEVEL_PRESETS.get(level, LEVEL_PRESETS["medium"])
    if not downsample:
        _compress_once(input_path, output_path, False, params["quality"], 100000)
        return os.path.getsize(output_path)

    best_path = output_path + ".best.pdf"
    best_size = None
    for quality, max_dim in _IMAGE_ATTEMPTS:
        _compress_once(input_path, output_path, True, quality, max_dim)
        size = os.path.getsize(output_path)
        if best_size is None or size < best_size:
            shutil.copyfile(output_path, best_path)
            best_size = size
        if not target_bytes or size <= target_bytes:
            if os.path.exists(best_path) and size != best_size:
                os.remove(best_path)
            return size
    if os.path.exists(best_path):
        shutil.move(best_path, output_path)
        return os.path.getsize(output_path)
    return os.path.getsize(output_path)


def _warning():
    return (
        "This PDF could not reach the requested target size without unacceptable "
        "quality loss (scanned/image-heavy PDFs often cannot shrink further). "
        "The smallest safe version was generated."
    )


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
