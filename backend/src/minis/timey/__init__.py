"""Search videos, preview timer styles and render a countdown with optional YouTube upload

Expose shared media search, overlay design, preview and rendering operations
through lazy imports. Browser and CLI workflows use these same settings
and do not load image or upload dependencies until they are needed
"""

lazy from .preview import frame, overlay, picture, thumbnail
lazy from .style import catalogue, design, designer, font, fonts, specimen
lazy from .style import read as read_style
lazy from .video import (
    FONTS,
    POSITIONS,
    STYLES,
    Timer,
    clock,
    download,
    duration,
    frames,
    placement,
    probe,
    reference,
    render,
    require_ffmpeg,
    search,
    suggest,
    suggest_style,
    surface,
    typeface,
    youtube_url,
)

__all__ = [
    "FONTS",
    "POSITIONS",
    "STYLES",
    "Timer",
    "catalogue",
    "clock",
    "design",
    "designer",
    "download",
    "duration",
    "font",
    "fonts",
    "frame",
    "frames",
    "overlay",
    "picture",
    "placement",
    "probe",
    "read_style",
    "reference",
    "render",
    "require_ffmpeg",
    "search",
    "specimen",
    "suggest",
    "suggest_style",
    "surface",
    "thumbnail",
    "typeface",
    "youtube_url",
]
