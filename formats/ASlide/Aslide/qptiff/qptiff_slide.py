"""
QPTiff slide reader for ASlide
Supports reading .qptiff files using the qptifffile library
"""

import os
import numpy as np
from numpy.typing import NDArray
from PIL import Image
from typing import Optional, Tuple, List, Dict, Any

try:
    from qptifffile import QPTiffFile as _QPTiffFile
except ImportError:
    _QPTiffFile = None

from openslide import AbstractSlide
import openslide

from ..errors import (
    MissingDefaultBiomarkerError,
    UnknownBiomarkerError,
    UnsupportedOperationError,
)


class QptiffSlide(AbstractSlide):
    """QPTiff slide reader using qptifffile library"""

    DEFAULT_DISPLAY_BIOMARKER = "DAPI"
    BRIGHTFIELD_MARKERS = {"h&e", "he"}

    def __init__(self, filename: str):
        """Initialize QPTiff slide

        Args:
            filename: Path to .qptiff file
        """
        if _QPTiffFile is None:
            raise ImportError(
                "qptifffile library is not available. Please install it with: pip install qptifffile"
            )

        AbstractSlide.__init__(self)
        self.__filename = filename
        self._qptiff = _QPTiffFile(filename)
        self._openslide = None

        # Get basic information
        self._biomarkers = self._qptiff.get_biomarkers()
        self._series = self._qptiff.series[0] if self._qptiff.series else None

        if not self._series:
            raise ValueError(f"No series found in QPTiff file: {filename}")

        # Cache properties
        self._level_count = len(self._series.levels)
        self._level_dimensions = tuple(
            (level.shape[2], level.shape[1]) for level in self._series.levels
        )
        self._level_downsamples = self._calculate_downsamples()
        self._mpp = _extract_tiff_mpp(self._series.pages[0])

        # Set format for compatibility
        self.format = os.path.splitext(os.path.basename(filename))[-1]

        if self.classify_slide_family() == "brightfield":
            self._openslide = openslide.OpenSlide(filename)

    def __repr__(self):
        return f"{self.__class__.__name__}({self.__filename!r})"

    @classmethod
    def detect_format(cls, filename) -> Optional[str]:
        """Detect if file is QPTiff format"""
        if _QPTiffFile is None:
            return None

        try:
            # Check file extension first
            ext = os.path.splitext(filename)[1].lower()
            if ext not in [".qptiff"]:
                return None

            # Try to open the file
            with _QPTiffFile(filename) as f:
                biomarkers = f.get_biomarkers()
                if biomarkers:
                    return "qptiff"
            return None
        except Exception:
            return None

    def close(self):
        """Close the QPTiff file"""
        if hasattr(self, "_qptiff") and self._qptiff:
            self._qptiff.close()
            self._qptiff = None
        if getattr(self, "_openslide", None) is not None:
            openslide_reader = self._openslide
            if openslide_reader is not None:
                openslide_reader.close()
            self._openslide = None

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
    def mpp(self) -> Optional[float]:
        """Microns per pixel"""
        if self._mpp is None:
            return None
        mpp_x, mpp_y = self._mpp
        return (mpp_x + mpp_y) / 2

    @property
    def magnification(self) -> Optional[float]:
        """Get slide magnification"""
        # Fallback to MPP calculation if mpp becomes available
        mpp = self.mpp
        if mpp and mpp > 0:
            return 10.0 / mpp
        return None

    @property
    def properties(self) -> Dict[str, str]:
        """Slide properties"""
        props = {
            "openslide.vendor": "QPTiff",
            "qptiff.biomarkers": ",".join(self._biomarkers),
            "qptiff.biomarker-count": str(len(self._biomarkers)),
        }

        # Add level information
        for i, (w, h) in enumerate(self._level_dimensions):
            props[f"openslide.level[{i}].width"] = str(w)
            props[f"openslide.level[{i}].height"] = str(h)
            props[f"openslide.level[{i}].downsample"] = str(self._level_downsamples[i])

        if self._mpp is not None:
            mpp_x, mpp_y = self._mpp
            props["openslide.mpp-x"] = str(mpp_x)
            props["openslide.mpp-y"] = str(mpp_y)

        return props

    @property
    def associated_images(self) -> Dict[str, Image.Image]:
        return {}

    def get_best_level_for_downsample(self, downsample: float) -> int:
        """Get the best level for a given downsample factor.

        This mirrors OpenSlide's behavior:
        - Return the largest level whose downsample is <= target
        - This ensures we don't over-downsample (lose resolution)
        """
        if not self._level_downsamples:
            return 0

        downsamples = self._level_downsamples

        # If target is smaller than level 0, return level 0
        if downsample < downsamples[0]:
            return 0

        # Find the largest level with downsample <= target
        for i in range(1, len(downsamples)):
            if downsamples[i] > downsample:
                return i - 1

        # Target is >= all levels, return the last level
        return len(downsamples) - 1

    def read_region(
        self, location: Tuple[int, int], level: int, size: Tuple[int, int]
    ) -> Image.Image:
        if self.classify_slide_family() == "brightfield":
            if self._openslide is None:
                raise RuntimeError("Brightfield QPTIFF OpenSlide reader is closed")
            return self._openslide.read_region(location, level, size)
        raise UnsupportedOperationError(
            "QPTIFF is a multiplex slide; use read_biomarker_region() with an explicit biomarker"
        )

    def read_biomarker_region(
        self,
        location: Tuple[int, int],
        level: int,
        size: Tuple[int, int],
        biomarker: str,
    ) -> Image.Image:
        """Read a region for a specific biomarker

        Args:
            location: (x, y) tuple giving the top left pixel in the level 0 reference frame
            level: the level number
            size: (width, height) tuple giving the region size
            biomarker: name of the biomarker to read

        Returns:
            PIL Image object
        """
        if biomarker not in self._biomarkers:
            raise UnknownBiomarkerError(
                f"Biomarker '{biomarker}' not found. Available: {self._biomarkers}"
            )

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

        if self._qptiff is None:
            raise RuntimeError("QPTiff reader is closed")

        region_data = self._qptiff.read_region(
            layers=[biomarker],
            pos=(level_x, level_y),
            shape=(height, width),
            level=level,
        )

        return self._region_to_image(region_data)

    def read_region_biomarker(
        self,
        location: Tuple[int, int],
        level: int,
        size: Tuple[int, int],
        biomarker: str,
    ) -> Image.Image:
        return self.read_biomarker_region(location, level, size, biomarker)

    def list_biomarkers(self) -> List[str]:
        return self._biomarkers.copy()

    def classify_slide_family(self) -> str:
        normalized = [
            marker.strip().lower() for marker in self._biomarkers if marker.strip()
        ]
        if len(normalized) == 1 and normalized[0] in self.BRIGHTFIELD_MARKERS:
            return "brightfield"
        return "multiplex"

    @property
    def qptiff_semantics(self) -> str:
        return self.classify_slide_family()

    def has_biomarker(self, name: str) -> bool:
        return name in self._biomarkers

    def get_biomarkers(self) -> List[str]:
        """Get list of available biomarkers"""
        return self.list_biomarkers()

    def get_default_display_biomarker(self) -> str:
        if self.classify_slide_family() != "multiplex":
            raise MissingDefaultBiomarkerError(
                "Brightfield QPTIFF does not define a default multiplex display biomarker"
            )
        if self.DEFAULT_DISPLAY_BIOMARKER in self._biomarkers:
            return self.DEFAULT_DISPLAY_BIOMARKER
        raise MissingDefaultBiomarkerError(
            f"Default display biomarker '{self.DEFAULT_DISPLAY_BIOMARKER}' is not available"
        )

    def get_thumbnail(self, size: Tuple[int, int]) -> Image.Image:
        if self.classify_slide_family() == "brightfield":
            if self._openslide is None:
                raise RuntimeError("Brightfield QPTIFF OpenSlide reader is closed")
            return self._openslide.get_thumbnail(size)
        raise UnsupportedOperationError(
            "QPTIFF thumbnails require an explicit display biomarker-aware path"
        )

    def _region_to_image(self, region_data: NDArray[Any]) -> Image.Image:
        if region_data.dtype == np.uint8 and region_data.max() <= 1:
            normalized = (region_data * 255).astype(np.uint8)
        elif region_data.max() > region_data.min():
            normalized = (
                (region_data - region_data.min())
                / (region_data.max() - region_data.min())
                * 255
            ).astype(np.uint8)
        else:
            normalized = np.zeros_like(region_data, dtype=np.uint8)

        if len(normalized.shape) == 2:
            rgb_data = np.stack([normalized] * 3, axis=-1)
        else:
            rgb_data = normalized

        return Image.fromarray(rgb_data)

    def _calculate_downsamples(self) -> Tuple[float, ...]:
        """Calculate downsample factors for each level"""
        if not self._level_dimensions:
            return tuple()

        base_width, base_height = self._level_dimensions[0]
        downsamples = []

        for width, height in self._level_dimensions:
            # Calculate downsample based on width (assuming square pixels)
            downsample = base_width / width
            downsamples.append(downsample)

        return tuple(downsamples)


def _extract_tiff_mpp(page: Any) -> Optional[Tuple[float, float]]:
    x_resolution = _resolution_value(page.tags.get("XResolution"))
    y_resolution = _resolution_value(page.tags.get("YResolution"))
    if not x_resolution or not y_resolution:
        return None

    unit_tag = page.tags.get("ResolutionUnit")
    unit = int(unit_tag.value) if unit_tag is not None else 2
    if unit == 2:
        microns_per_unit = 25400.0
    elif unit == 3:
        microns_per_unit = 10000.0
    else:
        return None

    return (microns_per_unit / x_resolution, microns_per_unit / y_resolution)


def _resolution_value(tag: Any) -> Optional[float]:
    if tag is None:
        return None
    value = tag.value
    if isinstance(value, tuple) and len(value) == 2:
        numerator, denominator = value
        if denominator == 0:
            return None
        return float(numerator) / float(denominator)
    return float(value)
