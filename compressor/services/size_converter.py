"""Binary size conversion helpers and target-size presets."""
import os
import re

BYTES_PER_KB = 1024
BYTES_PER_MB = 1024 * 1024
BYTES_PER_GB = 1024 * 1024 * 1024

_UNIT_FACTORS = {
    "b": 1,
    "byte": 1,
    "bytes": 1,
    "kb": BYTES_PER_KB,
    "mb": BYTES_PER_MB,
    "gb": BYTES_PER_GB,
    "tb": BYTES_PER_GB * 1024,
}

KB_PRESETS = [10, 20, 30, 50, 100, 200, 500]
MB_PRESETS = [1, 2, 5, 10, 20, 50, 100]
GB_PRESETS = [0.5, 1, 2]

LEVEL_PRESETS = {
    "low": {"quality": 90, "scale": 1.0, "label": "Low"},
    "medium": {"quality": 75, "scale": 1.0, "label": "Medium"},
    "high": {"quality": 55, "scale": 0.85, "label": "High"},
}


def bytes_to_human(num_bytes, decimals=2):
    """Format a byte count using binary (1024-based) units."""
    num_bytes = float(num_bytes or 0)
    if num_bytes < BYTES_PER_KB:
        return f"{int(num_bytes)} B"
    for unit, factor in (
        ("KB", BYTES_PER_KB),
        ("MB", BYTES_PER_MB),
        ("GB", BYTES_PER_GB),
        ("TB", BYTES_PER_GB * 1024),
    ):
        if num_bytes < factor * 1024 or unit == "TB":
            value = num_bytes / factor
            return f"{value:.{decimals}f} {unit}"
    return f"{num_bytes:.{decimals}f} B"


def parse_size_string(value):
    """Parse ``"10 MB"`` / ``"1.5gb"`` / ``"500"`` into a byte count."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    match = re.match(r"^\s*([0-9]*\.?[0-9]+)\s*([a-zA-Z]*)\s*$", str(value))
    if not match:
        return None
    number, unit = match.groups()
    factor = _UNIT_FACTORS.get(unit.lower() or "b")
    if factor is None:
        return None
    return int(float(number) * factor)


def parse_target_size(value, unit="KB"):
    """Convert a numeric value + unit (KB/MB/GB) into bytes."""
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    factor = _UNIT_FACTORS.get(str(unit).lower(), BYTES_PER_KB)
    return int(number * factor)


def build_presets():
    """Return the preset catalogue consumed by the frontend."""
    return {
        "KB": [{"label": f"{v} KB", "value": v, "unit": "KB", "bytes": v * BYTES_PER_KB} for v in KB_PRESETS],
        "MB": [{"label": f"{v} MB", "value": v, "unit": "MB", "bytes": v * BYTES_PER_MB} for v in MB_PRESETS],
        "GB": [{"label": f"{v} GB", "value": v, "unit": "GB", "bytes": int(v * BYTES_PER_GB)} for v in GB_PRESETS],
    }


def filename_for(original_name, suffix="compressed", extension=None):
    """Build an output filename, optionally forcing a new extension."""
    root, ext = os.path.splitext(original_name or "file")
    if extension:
        ext = extension if extension.startswith(".") else f".{extension}"
    return f"{root}_{suffix}{ext}"
