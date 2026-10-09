"""Template context processors."""
from django.conf import settings

from .services.dispatcher import SUPPORTED_EXTENSIONS
from .services.size_converter import build_presets

SITE_NAME = "SmartCompress Pro"
SITE_TAGLINE = "Compress Smarter. Share Faster."


def site_context(request):
    return {
        "site_name": SITE_NAME,
        "site_tagline": SITE_TAGLINE,
        "size_presets": build_presets(),
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "max_upload_mb": settings.MAX_UPLOAD_SIZE // (1024 * 1024),
        "compression_levels": [
            {"value": "low", "label": "Low"},
            {"value": "medium", "label": "Medium"},
            {"value": "high", "label": "High"},
            {"value": "custom", "label": "Custom"},
        ],
    }
