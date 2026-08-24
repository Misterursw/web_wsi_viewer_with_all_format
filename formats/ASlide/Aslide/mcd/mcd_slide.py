from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from ..errors import (
    MissingDefaultBiomarkerError,
    UnknownBiomarkerError,
    UnsupportedOperationError,
)

try:
    from readimc import MCDFile as _MCDFile
except ImportError:
    _MCDFile = None


class McdSlide:
    @classmethod
    def detect_format(cls, filename: Any) -> str | None:
        if _MCDFile is None:
            return None
        try:
            with _MCDFile(filename):
                return "mcd"
        except Exception:
            return None

    def __init__(self, filename: str, acquisition_id: int | None = None):
        if _MCDFile is None:
            raise ImportError(
                "readimc is required for MCD support. Install with: pip install readimc"
            )

        self._filename = filename
        self._requested_acquisition_id = acquisition_id
        self._mcd = _MCDFile(filename)
        self._mcd.open()
        self._slides = self._mcd.slides
        if not self._slides:
            self._mcd.close()
            raise ValueError(f"No slides found in MCD file: {filename}")

        self._slide = self._slides[0]
        self._acquisitions = list(self._slide.acquisitions)
        if not self._acquisitions:
            self._mcd.close()
            raise ValueError(f"No acquisitions found in MCD file: {filename}")

        self._acquisition = self._select_acquisition(acquisition_id)
        self._acquisition_data = np.asarray(
            self._mcd.read_acquisition(self._acquisition)
        )
        width_px = self._acquisition.width_px
        height_px = self._acquisition.height_px
        pixel_size_x = self._acquisition.pixel_size_x_um
        pixel_size_y = self._acquisition.pixel_size_y_um
        self._width = int(
            width_px if width_px is not None else self._acquisition_data.shape[-1]
        )
        self._height = int(
            height_px if height_px is not None else self._acquisition_data.shape[-2]
        )
        self._pixel_size_x = float(pixel_size_x if pixel_size_x is not None else 1.0)
        self._pixel_size_y = float(pixel_size_y if pixel_size_y is not None else 1.0)
        self._biomarkers = self._build_biomarkers()
        self._channels = {entry["name"]: entry for entry in self._biomarkers}

    def _build_biomarkers(self) -> list[dict[str, Any]]:
        biomarkers: list[dict[str, Any]] = []
        for index, name in enumerate(self._acquisition.channel_names):
            label = self._acquisition.channel_labels[index]
            display_name = str(label or name)
            biomarkers.append(
                {
                    "name": display_name,
                    "index": index,
                    "source_name": str(name),
                    "metal": str(self._acquisition.channel_metals[index]),
                    "mass": str(self._acquisition.channel_masses[index]),
                }
            )
        return biomarkers

    def _select_acquisition(self, acquisition_id: int | None):
        if acquisition_id is not None:
            for acquisition in self._acquisitions:
                if int(acquisition.id or 0) == acquisition_id:
                    return acquisition
            self._mcd.close()
            raise ValueError(
                f"Acquisition id {acquisition_id} not found in MCD file: {self._filename}"
            )

        return max(
            self._acquisitions,
            key=lambda acquisition: (
                int(acquisition.width_px or 0) * int(acquisition.height_px or 0),
                int(acquisition.id or 0),
            ),
        )

    @property
    def level_count(self) -> int:
        return 1

    @property
    def dimensions(self) -> tuple[int, int]:
        return (self._width, self._height)

    @property
    def level_dimensions(self) -> tuple[tuple[int, int], ...]:
        return (self.dimensions,)

    @property
    def level_downsamples(self) -> tuple[float, ...]:
        return (1.0,)

    @property
    def properties(self) -> dict[str, str]:
        return {
            "openslide.vendor": "mcd",
            "mcd.slide-count": str(len(self._slides)),
            "mcd.acquisition-count": str(len(self._acquisitions)),
            "mcd.channel-count": str(len(self._biomarkers)),
            "mcd.selected-acquisition-id": str(self._acquisition.id),
            "mcd.selected-acquisition-description": str(
                self._acquisition.description or ""
            ),
            "openslide.mpp-x": str(self._pixel_size_x),
            "openslide.mpp-y": str(self._pixel_size_y),
        }

    @property
    def associated_images(self) -> dict[str, Image.Image]:
        return {}

    def close(self) -> None:
        self._mcd.close()

    def get_best_level_for_downsample(self, downsample: float) -> int:
        return 0

    def list_biomarkers(self) -> list[str]:
        return [entry["name"] for entry in self._biomarkers]

    def has_biomarker(self, name: str) -> bool:
        return name in self._channels

    def get_default_display_biomarker(self) -> str:
        for candidate in self.list_biomarkers():
            upper = candidate.upper()
            if "DNA" in upper or "IRIDIUM" in upper or "HISTONE" in upper:
                return candidate
        if self._biomarkers:
            return self._biomarkers[0]["name"]
        raise MissingDefaultBiomarkerError("No biomarkers available in MCD acquisition")

    def read_region(
        self, location: tuple[int, int], level: int, size: tuple[int, int]
    ) -> Image.Image:
        raise UnsupportedOperationError(
            "MCD slides require an explicit biomarker; use read_biomarker_region()"
        )

    def read_biomarker_region(
        self,
        location: tuple[int, int],
        level: int,
        size: tuple[int, int],
        biomarker: str,
    ) -> Image.Image:
        if level != 0:
            raise ValueError("MCD backend currently supports only level 0")
        if biomarker not in self._channels:
            raise UnknownBiomarkerError(f"Biomarker '{biomarker}' not found")

        channel_index = int(self._channels[biomarker]["index"])
        x, y = location
        width, height = size
        plane = self._acquisition_data[channel_index]
        region = np.asarray(plane[y : y + height, x : x + width])
        if region.size == 0:
            region = np.zeros((height, width), dtype=np.uint8)
        if region.dtype != np.uint8:
            region = _normalize_to_uint8(region)
        rgba = np.stack([region, region, region, np.full_like(region, 255)], axis=-1)
        return Image.fromarray(rgba, mode="RGBA")


def _normalize_to_uint8(data: NDArray[Any]) -> NDArray[np.uint8]:
    data = np.asarray(data)
    minimum = float(data.min())
    maximum = float(data.max())
    if maximum <= minimum:
        return np.zeros(data.shape, dtype=np.uint8)
    scaled = (data - minimum) / (maximum - minimum)
    return (scaled * 255).astype(np.uint8)
