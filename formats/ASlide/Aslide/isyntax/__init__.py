"""
iSyntax format support for ASlide
"""

try:
    from .isyntax_slide import IsyntaxSlide, open_isyntax_slide
except ImportError:
    IsyntaxSlide = None
    open_isyntax_slide = None

ISYNTAX_AVAILABLE = IsyntaxSlide is not None

__all__ = ["IsyntaxSlide", "open_isyntax_slide", "ISYNTAX_AVAILABLE"]
