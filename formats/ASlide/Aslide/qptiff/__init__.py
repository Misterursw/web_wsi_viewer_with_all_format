# QPTiff format support for ASlide
# This module provides support for reading .qptiff files using the qptifffile library

from .qptiff_slide import QptiffSlide
from .qptiff_deepzoom import QptiffDeepZoomGenerator

__all__ = ['QptiffSlide', 'QptiffDeepZoomGenerator']
