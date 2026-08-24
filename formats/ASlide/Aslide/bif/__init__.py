"""
BIF (Ventana BigTIFF) file format reader.
"""

from .bif_slide import BifSlide
from .bif_deepzoom import DeepZoomGenerator as BifDeepZoomGenerator

__all__ = ['BifSlide', 'BifDeepZoomGenerator']

