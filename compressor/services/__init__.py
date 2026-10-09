"""Compression services for SmartCompress Pro.

Only lightweight size helpers are re-exported here to keep model imports fast.
Import the concrete compressors directly, e.g.::

    from compressor.services.image_compressor import compress_image
"""
from .size_converter import (  # noqa: F401
    BYTES_PER_GB,
    BYTES_PER_KB,
    BYTES_PER_MB,
    LEVEL_PRESETS,
    build_presets,
    bytes_to_human,
    filename_for,
    parse_size_string,
    parse_target_size,
)
