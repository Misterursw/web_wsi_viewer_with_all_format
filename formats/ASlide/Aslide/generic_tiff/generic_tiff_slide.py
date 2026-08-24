from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from openslide import AbstractSlide
import tifffile

from ..errors import (
    MissingDefaultBiomarkerError,
    UnknownBiomarkerError,
    UnsupportedOperationError,
)


class GenericTiffSlide(AbstractSlide):
    @classmethod
    def detect_format(cls, filename: Any) -> str | None:
        with tifffile.TiffFile(filename) as tiff:
            if tiff.is_ome:
                return None
        return "generic_tiff"

    def __init__(self, filename: str):
        AbstractSlide.__init__(self)
        self._filename = filename
        self._path = Path(filename)
        self._biomarkers: list[str] | None = None
        with tifffile.TiffFile(filename) as tiff:
            self._series = tiff.series[0]
            self._shape = tuple(int(value) for value in self._series.shape)
            self._axes = self._series.axes
            self._dtype = tiff.pages[0].dtype
            self._description = str(getattr(tiff.pages[0], "description", "") or "")
            self._mpp = _extract_tiff_mpp(tiff.pages[0])
            self._page_count = len(tiff.pages)
            self._samples_per_pixel = int(
                getattr(tiff.pages[0].tags.get("SamplesPerPixel"), "value", 1) or 1
            )

    @property
    def level_count(self) -> int:
        return 1

    @property
    def dimensions(self) -> tuple[int, int]:
        return _dimensions_from_axes(self._shape, self._axes)

    @property
    def level_dimensions(self) -> tuple[tuple[int, int], ...]:
        return (self.dimensions,)

    @property
    def level_downsamples(self) -> tuple[float, ...]:
        return (1.0,)

    @property
    def properties(self) -> dict[str, str]:
        props = {
            "openslide.vendor": "tifffile",
            "tiff.axes": self._axes,
            "tiff.description": self._description,
        }
        if self._mpp is not None:
            mpp_x, mpp_y = self._mpp
            props["openslide.mpp-x"] = str(mpp_x)
            props["openslide.mpp-y"] = str(mpp_y)
        return props

    @property
    def mpp(self) -> float | None:
        if self._mpp is None:
            return None
        mpp_x, mpp_y = self._mpp
        return (mpp_x + mpp_y) / 2

    @property
    def associated_images(self) -> dict[str, Image.Image]:
        return {}

    def close(self) -> None:
        return None

    def get_best_level_for_downsample(self, downsample: float) -> int:
        return 0

    def read_region(
        self, location: tuple[int, int], level: int, size: tuple[int, int]
    ) -> Image.Image:
        if self.classify_slide_family() == "multiplex":
            raise UnsupportedOperationError(
                "Multiplex TIFF slides require an explicit biomarker; use read_biomarker_region()"
            )
        if level != 0:
            raise ValueError("Generic TIFF backend currently supports only level 0")
        x, y = location
        width, height = size
        with tifffile.TiffFile(str(self._path)) as tiff:
            data = np.asarray(tiff.asarray())
        image = _as_displayable_image(data, self._axes)
        region = image[y : y + height, x : x + width]
        if region.size == 0:
            return Image.new("RGBA", (width, height))
        if region.ndim == 2:
            if region.dtype != np.uint8:
                region = _normalize_to_uint8(region)
            rgba = np.stack(
                [region, region, region, np.full_like(region, 255)], axis=-1
            )
            return Image.fromarray(rgba, mode="RGBA")
        if region.dtype != np.uint8:
            region = _normalize_to_uint8(region)
        if region.shape[-1] == 3:
            alpha = np.full(region.shape[:2] + (1,), 255, dtype=np.uint8)
            region = np.concatenate([region, alpha], axis=-1)
        return Image.fromarray(region, mode="RGBA")

    def get_thumbnail(self, size: tuple[int, int]) -> Image.Image:
        if self.classify_slide_family() == "multiplex":
            raise UnsupportedOperationError(
                "Multiplex TIFF thumbnails require an explicit display biomarker-aware path"
            )
        image = self.read_region((0, 0), 0, self.dimensions)
        image.thumbnail(size)
        return image

    def classify_slide_family(self) -> str:
        """Classify whether this TIFF is brightfield or multiplex."""
        # Check 1: explicit channel axis with more than one channel
        if "C" in self._axes:
            c_index = self._axes.index("C")
            if self._shape[c_index] > 1:
                return "multiplex"

        # Check 2: ImageJ hyperstack description with multiple channels
        if "channels=" in self._description.lower():
            match = re.search(r"channels\s*=\s*(\d+)", self._description, re.IGNORECASE)
            if match and int(match.group(1)) > 1:
                return "multiplex"

        # Check 3: multiple pages each with a single sample (potential multi-page stack)
        if self._page_count > 1 and self._samples_per_pixel == 1:
            # Avoid false positives for multi-resolution (pyramid) images by
            # checking that pages have the same size as the series.
            expected_y = self._shape[self._axes.index("Y")] if "Y" in self._axes else self._shape[-2]
            expected_x = self._shape[self._axes.index("X")] if "X" in self._axes else self._shape[-1]
            if self.dimensions == (expected_x, expected_y):
                return "multiplex"

        return "brightfield"

    def _discover_biomarkers(self) -> list[str]:
        if self._biomarkers is not None:
            return self._biomarkers

        biomarkers: list[str] = []

        # Try to extract channel names from ImageJ description
        desc = self._description
        if "labels=" in desc.lower():
            match = re.search(r"labels\s*=\s*\[(.*?)\]", desc, re.IGNORECASE | re.DOTALL)
            if match:
                labels_str = match.group(1)
                # Split by comma or newline
                biomarkers = [label.strip().strip('"\'') for label in re.split(r"[\n,]", labels_str) if label.strip()]

        if not biomarkers and "C" in self._axes:
            c_count = self._shape[self._axes.index("C")]
            biomarkers = [f"Channel {i}" for i in range(c_count)]
        elif not biomarkers and self._page_count > 1:
            biomarkers = [f"Channel {i}" for i in range(self._page_count)]

        self._biomarkers = biomarkers
        return self._biomarkers

    def list_biomarkers(self) -> list[str]:
        return self._discover_biomarkers()

    def get_biomarkers(self) -> list[str]:
        return self.list_biomarkers()

    def has_biomarker(self, name: str) -> bool:
        return name in self._discover_biomarkers()

    def get_default_display_biomarker(self) -> str:
        biomarkers = self._discover_biomarkers()
        if not biomarkers:
            raise MissingDefaultBiomarkerError("No biomarkers available in this TIFF")
        return biomarkers[0]

    def read_biomarker_region(
        self,
        location: tuple[int, int],
        level: int,
        size: tuple[int, int],
        biomarker: str,
    ) -> Image.Image:
        if level != 0:
            raise ValueError("Generic TIFF backend currently supports only level 0")

        biomarkers = self._discover_biomarkers()
        if biomarker not in biomarkers:
            raise UnknownBiomarkerError(
                f"Biomarker '{biomarker}' not found. Available: {biomarkers}"
            )

        x, y = location
        width, height = size
        channel_index = biomarkers.index(biomarker)

        with tifffile.TiffFile(str(self._path)) as tiff:
            data = np.asarray(tiff.asarray())

        # Extract the requested channel plane
        if "C" in self._axes:
            axis = self._axes.index("C")
            plane = np.take(data, channel_index, axis=axis)
        else:
            # Multi-page fallback: read the specific page
            page_data = np.asarray(tiff.pages[channel_index].asarray())
            plane = page_data

        region = np.asarray(plane[y : y + height, x : x + width])
        if region.size == 0:
            region = np.zeros((height, width), dtype=np.uint8)
        if region.dtype != np.uint8:
            region = _normalize_to_uint8(region)
        rgba = np.stack([region, region, region, np.full_like(region, 255)], axis=-1)
        return Image.fromarray(rgba, mode="RGBA")


def _dimensions_from_axes(shape: tuple[int, ...], axes: str) -> tuple[int, int]:
    if "X" in axes and "Y" in axes:
        return (shape[axes.index("X")], shape[axes.index("Y")])
    return (shape[-1], shape[-2])


def _as_displayable_image(data: NDArray[Any], axes: str) -> NDArray[Any]:
    array = np.asarray(data)
    if array.ndim == 2:
        return array
    if axes.endswith("YXS") and array.ndim == 3:
        return array
    while array.ndim > 3:
        array = array[0]
    if array.ndim == 3 and array.shape[0] in {3, 4} and "Y" in axes and "X" in axes:
        array = np.moveaxis(array, 0, -1)
    elif array.ndim == 3 and array.shape[-1] not in {3, 4}:
        array = array[..., 0]
    return array


def _normalize_to_uint8(data: NDArray[Any]) -> NDArray[np.uint8]:
    data = np.asarray(data)
    minimum = float(data.min())
    maximum = float(data.max())
    if maximum <= minimum:
        return np.zeros(data.shape, dtype=np.uint8)
    scaled = (data - minimum) / (maximum - minimum)
    return (scaled * 255).astype(np.uint8)


def _extract_tiff_mpp(page: Any) -> tuple[float, float] | None:
    x_resolution = _resolution_value(page.tags.get("XResolution"))
    y_resolution = _resolution_value(page.tags.get("YResolution"))
    if not x_resolution or not y_resolution:
        return None

    unit_tag = page.tags.get("ResolutionUnit")
    unit = int(unit_tag.value) if unit_tag is not None else 2
    if unit == 2:  # inch
        microns_per_unit = 25400.0
    elif unit == 3:  # centimeter
        microns_per_unit = 10000.0
    else:
        return None

    return (microns_per_unit / x_resolution, microns_per_unit / y_resolution)


def _resolution_value(tag: Any) -> float | None:
    if tag is None:
        return None
    value = tag.value
    if isinstance(value, tuple) and len(value) == 2:
        numerator, denominator = value
        if denominator == 0:
            return None
        return float(numerator) / float(denominator)
    return float(value)
