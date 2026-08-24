"""
iSyntax slide reader for ASlide
Supports reading .isyntax files using the pyisyntax library
"""

import os
import io
import numpy as np
from PIL import Image
from typing import Optional, Tuple, List, Dict, Any
from isyntax import ISyntax

from openslide import AbstractSlide


class IsyntaxSlide(AbstractSlide):
    """iSyntax slide reader using pyisyntax library"""

    def __init__(self, filename: str):
        """Initialize iSyntax slide

        Args:
            filename: Path to .isyntax file
        """

        AbstractSlide.__init__(self)
        self.__filename = filename
        self._isyntax = ISyntax.open(filename)

        # Cache properties
        self._level_count = self._isyntax.level_count
        self._level_dimensions = tuple(self._isyntax.level_dimensions)
        self._level_downsamples = tuple(
            float(ds) for ds in self._isyntax.level_downsamples
        )

        # Set format for compatibility
        self.format = os.path.splitext(os.path.basename(filename))[-1]

        # Cache mpp
        self._mpp = (self._isyntax.mpp_x + self._isyntax.mpp_y) / 2.0

    def __repr__(self):
        return f"{self.__class__.__name__}({self.__filename!r})"

    @classmethod
    def detect_format(cls, filename) -> Optional[str]:
        """Detect if file is iSyntax format"""
        try:
            # Check file extension first
            normalized_filename = str(filename)
            ext = os.path.splitext(normalized_filename)[1].lower()
            if ext not in [".isyntax"]:
                return None

            # Try to open the file
            with ISyntax.open(normalized_filename) as f:
                # If we can open it and get basic info, it's valid
                _ = f.level_count
                return "isyntax"
        except Exception:
            return None

    def close(self):
        """Close the iSyntax file"""
        if hasattr(self, "_isyntax") and self._isyntax:
            self._isyntax.close()
            self._isyntax = None

    @property
    def level_count(self) -> int:
        """The number of levels in the image"""
        return self._level_count

    @property
    def level_dimensions(self) -> Tuple[Tuple[int, int], ...]:
        """A list of (width, height) tuples, one for each level"""
        return self._level_dimensions

    @property
    def level_downsamples(self) -> Tuple[float, ...]:
        """A list of downsample factors for each level"""
        return self._level_downsamples

    @property
    def dimensions(self) -> Tuple[int, int]:
        """The dimensions of level 0 (width, height)"""
        return self._level_dimensions[0] if self._level_dimensions else (0, 0)

    @property
    def mpp(self) -> float:
        """Microns per pixel"""
        return self._mpp

    @property
    def properties(self) -> Dict[str, str]:
        """Slide properties"""
        props = {
            "openslide.vendor": "Philips",
            "openslide.mpp-x": str(self._mpp),
            "openslide.mpp-y": str(self._mpp),
            "openslide.objective-power": str(int(10.0 / self._mpp))
            if self._mpp > 0
            else "40",
            "isyntax.barcode": str(getattr(self._isyntax, "barcode", "")),
            "isyntax.offset-x": str(getattr(self._isyntax, "offset_x", 0)),
            "isyntax.offset-y": str(getattr(self._isyntax, "offset_y", 0)),
        }

        # Add level information
        for i, (w, h) in enumerate(self._level_dimensions):
            props[f"openslide.level[{i}].width"] = str(w)
            props[f"openslide.level[{i}].height"] = str(h)
            props[f"openslide.level[{i}].downsample"] = str(self._level_downsamples[i])

        return props

    @property
    def associated_images(self) -> Dict[str, Image.Image]:
        """Get associated images (label, macro, etc.)"""
        # Check if we have cached associated images
        if hasattr(self, "_cached_associated_images"):
            return self._cached_associated_images

        result = {}

        try:
            # Read label image
            if self._isyntax is None:
                raise RuntimeError("iSyntax reader is closed")
            label_jpeg = self._isyntax.read_label_image_jpeg()
            if label_jpeg is not None:
                result["label"] = Image.open(io.BytesIO(label_jpeg), formats=["JPEG"])
        except Exception:
            pass

        try:
            # Read macro image
            if self._isyntax is None:
                raise RuntimeError("iSyntax reader is closed")
            macro_jpeg = self._isyntax.read_macro_image_jpeg()
            if macro_jpeg is not None:
                result["macro"] = Image.open(io.BytesIO(macro_jpeg), formats=["JPEG"])
        except Exception:
            pass

        # Cache the result
        self._cached_associated_images = result
        return result

    def get_best_level_for_downsample(self, downsample: float) -> int:
        """Get the best level for a given downsample factor"""
        if not self._level_downsamples:
            return 0

        # Find the level with downsample closest to but not exceeding the requested value
        best_level = 0
        for i, level_downsample in enumerate(self._level_downsamples):
            if level_downsample <= downsample:
                best_level = i
            else:
                break

        return best_level

    def read_region(
        self, location: Tuple[int, int], level: int, size: Tuple[int, int]
    ) -> Image.Image:
        """Read a region from the slide

        Args:
            location: (x, y) tuple giving the top left pixel in the level 0 reference frame
            level: the level number
            size: (width, height) tuple giving the region size

        Returns:
            PIL Image object in RGBA mode
        """
        x, y = location
        width, height = size

        if level >= self._level_count:
            raise ValueError(
                f"Level {level} not available (max level: {self._level_count - 1})"
            )

        # Calculate position at the requested level
        downsample = self._level_downsamples[level]
        level_x = int(x / downsample)
        level_y = int(y / downsample)

        try:
            # Read the region - pyisyntax returns RGBA numpy array [height, width, 4]
            if self._isyntax is None:
                raise RuntimeError("iSyntax reader is closed")

            region_data = self._isyntax.read_region(
                level_x, level_y, width, height, level=level
            )

            # Convert numpy array to PIL Image (keep RGBA format for compatibility)
            return Image.fromarray(region_data, mode="RGBA")

        except Exception as e:
            # Return a blank RGBA image if reading fails
            blank = np.zeros((height, width, 4), dtype=np.uint8)
            blank[:, :, 3] = 255  # Set alpha channel to opaque
            return Image.fromarray(blank, mode="RGBA")

    def get_thumbnail(self, size: Tuple[int, int]) -> Image.Image:
        """Get a thumbnail of the slide

        Args:
            size: (width, height) tuple giving the maximum size of the thumbnail

        Returns:
            PIL Image object
        """
        # Read from the lowest resolution level
        last_level = self._level_count - 1
        thumb = self.read_region((0, 0), last_level, self._level_dimensions[last_level])

        # Resize to requested size while maintaining aspect ratio
        thumb.thumbnail(size, Image.Resampling.LANCZOS)
        return thumb


def open_isyntax_slide(filename: str) -> Optional[IsyntaxSlide]:
    """Open an iSyntax slide file

    Args:
        filename: Path to .isyntax file

    Returns:
        IsyntaxSlide object or None if failed
    """
    try:
        return IsyntaxSlide(filename)
    except Exception:
        return None
