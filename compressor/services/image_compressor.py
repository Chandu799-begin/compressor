"""Real image compression using Pillow.

Supports JPG/JPEG, PNG, WEBP (plus BMP/GIF/TIFF as inputs).  Implements
target-size compression through an iterative quality search with an optional
resolution reduction fallback.
"""
from __future__ import annotations

import io
import os

from PIL import Image, ImageOps

from .size_converter import LEVEL_PRESETS

# Refuse to hold absurdly large bitmaps in memory.
MAX_PIXELS = 80_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

_QUALITY_FLOOR = 20
_QUALITY_CEILING = 95
_MIN_SCALE = 0.2


class ImageCompressionError(Exception):
    """Raised when an image cannot be decoded or compressed."""


def _output_format(output_path, original_format):
    ext = os.path.splitext(output_path)[1].lower()
    mapping = {
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".png": "PNG",
        ".webp": "WEBP",
        ".bmp": "BMP",
        ".tiff": "TIFF",
    }
    return mapping.get(ext, original_format or "JPEG")


def _prepare(image, fmt):
    """Flatten/convert an image so it can be encoded in ``fmt``."""
    if fmt == "JPEG":
        if image.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", image.size, (255, 255, 255))
            converted = image.convert("RGBA")
            background.paste(converted, mask=converted.split()[-1])
            return background
        if image.mode != "RGB":
            return image.convert("RGB")
    elif fmt == "WEBP" and image.mode == "P":
        return image.convert("RGBA")
    return image


def _encode(image, fmt, quality, colors=None):
    """Encode ``image`` to bytes and return them."""
    buffer = io.BytesIO()
    prepared = image
    if fmt == "PNG" and colors:
        prepared = image.convert("P", palette=Image.ADAPTIVE, colors=max(2, min(256, colors)))
    elif fmt in ("JPEG", "WEBP", "BMP"):
        prepared = _prepare(image, fmt)

    save_kwargs = {"format": fmt}
    if fmt in ("JPEG", "WEBP"):
        save_kwargs["quality"] = int(quality)
        save_kwargs["optimize"] = True
        if fmt == "JPEG":
            save_kwargs["progressive"] = True
        else:
            save_kwargs["method"] = 6
    elif fmt == "PNG":
        save_kwargs["optimize"] = True
        save_kwargs["compress_level"] = 9

    if prepared.mode in ("RGBA", "LA") and fmt in ("PNG", "WEBP"):
        save_kwargs["lossless"] = False if fmt == "WEBP" else save_kwargs.get("lossless", False)

    prepared.save(buffer, **save_kwargs)
    return buffer.getvalue()


def _resize(image, scale):
    if scale >= 1.0:
        return image
    width = max(1, int(image.width * scale))
    height = max(1, int(image.height * scale))
    return image.resize((width, height), Image.LANCZOS)


def _resize_to_box(image, max_width, max_height, keep_aspect=True):
    if not max_width and not max_height:
        return image
    if keep_aspect:
        image.thumbnail((max_width or image.width, max_height or image.height), Image.LANCZOS)
        return image
    return image.resize((max_width or image.width, max_height or image.height), Image.LANCZOS)


def _best_for_target(image, fmt, target_bytes):
    """Search for the highest quality encoding under ``target_bytes``.

    Returns ``(bytes, scale, quality, colors)``.
    """
    best = None
    try:
        original_quality = _QUALITY_CEILING
        low, high = _QUALITY_FLOOR, _QUALITY_CEILING
        candidate = None
        while low <= high:
            mid = (low + high) // 2
            data = _encode(image, fmt, mid)
            if len(data) <= target_bytes:
                candidate = (data, 1.0, mid, None)
                low = mid + 1
            else:
                high = mid - 1
        if candidate:
            return candidate

        # Quality floor still too large: progressively shrink the image.
        scale = 1.0
        while scale > _MIN_SCALE:
            scale *= 0.85
            scaled = _resize(image, scale)
            low, high = _QUALITY_FLOOR, _QUALITY_CEILING
            while low <= high:
                mid = (low + high) // 2
                data = _encode(scaled, fmt, mid)
                if len(data) <= target_bytes:
                    best = (data, scale, mid, None)
                    low = mid + 1
                else:
                    high = mid - 1
            if best:
                return best
    except (OSError, ValueError) as exc:  # pragma: no cover - defensive
        raise ImageCompressionError(str(exc)) from exc

    if best:
        return best
    # Nothing fit: emit the smallest encoding we can produce.
    fallback = _encode(_resize(image, _MIN_SCALE), fmt, _QUALITY_FLOOR)
    return (fallback, _MIN_SCALE, _QUALITY_FLOOR, None)


def compress_image(
    input_path,
    output_path,
    target_bytes=None,
    level="medium",
    max_width=None,
    max_height=None,
    keep_aspect=True,
    strip_metadata=False,
    convert_to_webp=False,
):
    """Compress an image file and write it to ``output_path``.

    Returns a dict describing the outcome.  Never enlarges a file that is
    already smaller than the requested target.
    """
    if not os.path.exists(input_path):
        raise ImageCompressionError("Input file does not exist.")

    original_size = os.path.getsize(input_path)
    try:
        image = Image.open(input_path)
        input_format = (image.format or "").upper()
        image = ImageOps.exif_transpose(image)
        image.load()
    except (OSError, ValueError) as exc:
        raise ImageCompressionError(f"Unsupported or corrupt image: {exc}") from exc

    fmt = "WEBP" if convert_to_webp else _output_format(output_path, input_format)
    # When the output format differs from the input we must always emit freshly
    # encoded bytes (never copy the original, which would mismatch the extension).
    same_format = input_format == fmt

    if input_format in ("GIF",) or getattr(image, "is_animated", False):
        image = image.convert("RGBA") if image.mode in ("RGBA", "P") else image.convert("RGB")

    image = _resize_to_box(image, max_width, max_height, keep_aspect)

    params = LEVEL_PRESETS.get(level, LEVEL_PRESETS["medium"])
    warning = ""
    achieved = True

    if target_bytes and original_size <= target_bytes:
        # Already under target - apply a light, safe optimisation.
        data = _encode(_prepare(image, fmt), fmt, params["quality"])
        if same_format and len(data) >= original_size:
            # Keep the original bytes rather than enlarging an already-small file.
            _copy(input_path, output_path)
            return _result(original_size, original_size, image, fmt, target_bytes, True, warning)
        _write(output_path, data)
        return _result(original_size, len(data), image, fmt, target_bytes, True, warning)

    if target_bytes:
        data, scale, quality, colors = _best_for_target(image, fmt, target_bytes)
        if len(data) > target_bytes:
            achieved = False
            warning = (
                "Requested target could not be reached without unacceptable quality loss. "
                "The smallest safe result was produced instead."
            )
    else:
        data = _encode(_prepare(image, fmt), fmt, params["quality"])
        scale = params.get("scale", 1.0)
        if scale < 1.0:
            data = _encode(_prepare(_resize(image, scale), fmt), fmt, params["quality"])

    # Never enlarge beyond the original - but only meaningful when the format
    # is unchanged (a format conversion may legitimately be larger).
    if same_format and len(data) > original_size:
        _copy(input_path, output_path)
        return _result(original_size, original_size, image, fmt, target_bytes, True, warning)

    _write(output_path, data)
    return _result(original_size, len(data), image, fmt, target_bytes, achieved, warning)


def _result(original_size, compressed_size, image, fmt, target_bytes, achieved, warning):
    saved = max(original_size - compressed_size, 0)
    percentage = (saved / original_size * 100) if original_size else 0.0
    return {
        "original_size": original_size,
        "compressed_size": compressed_size,
        "saved_bytes": saved,
        "savings_percent": round(percentage, 2),
        "width": image.width,
        "height": image.height,
        "format": fmt,
        "target_bytes": target_bytes,
        "achieved_target": achieved,
        "warning": warning,
    }


def _write(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)


def _copy(source, destination):
    import shutil

    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copyfile(source, destination)
