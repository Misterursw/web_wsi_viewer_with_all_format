from __future__ import annotations

from typing import Any

import h5py
import numpy as np
from PIL import Image

from ..errors import (
    MissingDefaultBiomarkerError,
    UnknownBiomarkerError,
    UnsupportedOperationError,
)
from .probe import _normalize_marker_values


class Hdf5Slide:
    def __init__(self, filename: str):
        self._filename = filename
        self._handle = h5py.File(filename, "r")
        self._dataset = self._find_dataset()
        self._biomarkers = _normalize_marker_values(self._dataset.attrs["markers"])
        if len(self._dataset.shape) != 3:
            self.close()
            raise ValueError(f"HDF5 multiplex dataset must be 3D: {self._dataset.name}")
        if len(self._biomarkers) != int(self._dataset.shape[0]):
            self.close()
            raise ValueError(
                f"Marker count does not match channel count for dataset {self._dataset.name}"
            )
        self._channels = {name: index for index, name in enumerate(self._biomarkers)}

    def _find_dataset(self) -> h5py.Dataset:
        candidates: list[h5py.Dataset] = []

        def visitor(name: str, obj: Any) -> None:
            if not isinstance(obj, h5py.Dataset):
                return
            markers = obj.attrs.get("markers")
            normalized = _normalize_marker_values(markers)
            if len(obj.shape) == 3 and len(normalized) == int(obj.shape[0]):
                candidates.append(obj)

        self._handle.visititems(visitor)
        if not candidates:
            self.close()
            raise ValueError(f"No multiplex HDF5 dataset found in {self._filename}")
        return candidates[0]

    @property
    def level_count(self) -> int:
        return 1

    @property
    def dimensions(self) -> tuple[int, int]:
        channels, height, width = self._dataset.shape
        return (int(width), int(height))

    @property
    def level_dimensions(self) -> tuple[tuple[int, int], ...]:
        return (self.dimensions,)

    @property
    def level_downsamples(self) -> tuple[float, ...]:
        return (1.0,)

    @property
    def properties(self) -> dict[str, str]:
        return {
            "openslide.vendor": "hdf5-imc",
            "hdf5.dataset": self._dataset.name,
            "hdf5.channel-count": str(len(self._biomarkers)),
        }

    @property
    def associated_images(self) -> dict[str, Image.Image]:
        return {}

    def close(self) -> None:
        if getattr(self, "_handle", None) is not None:
            self._handle.close()

    def get_best_level_for_downsample(self, downsample: float) -> int:
        return 0

    def list_biomarkers(self) -> list[str]:
        return list(self._biomarkers)

    def has_biomarker(self, name: str) -> bool:
        return name in self._channels

    def get_default_display_biomarker(self) -> str:
        for biomarker in self._biomarkers:
            upper = biomarker.upper()
            if "DNA" in upper or "DAPI" in upper or "HISTONE" in upper:
                return biomarker
        if self._biomarkers:
            return self._biomarkers[0]
        raise MissingDefaultBiomarkerError("No biomarkers available in HDF5 dataset")

    def read_region(
        self, location: tuple[int, int], level: int, size: tuple[int, int]
    ) -> Image.Image:
        raise UnsupportedOperationError(
            "HDF5 multiplex slides require an explicit biomarker; use read_biomarker_region()"
        )

    def read_biomarker_region(
        self,
        location: tuple[int, int],
        level: int,
        size: tuple[int, int],
        biomarker: str,
    ) -> Image.Image:
        if level != 0:
            raise ValueError("HDF5 multiplex backend currently supports only level 0")
        if biomarker not in self._channels:
            raise UnknownBiomarkerError(f"Biomarker '{biomarker}' not found")

        channel_index = self._channels[biomarker]
        x, y = location
        width, height = size
        plane = np.asarray(self._dataset[channel_index])
        region = np.asarray(plane[y : y + height, x : x + width])
        if region.size == 0:
            region = np.zeros((height, width), dtype=np.uint8)
        if region.dtype != np.uint8:
            region = _normalize_to_uint8(region)
        rgba = np.stack([region, region, region, np.full_like(region, 255)], axis=-1)
        return Image.fromarray(rgba, mode="RGBA")


def _normalize_to_uint8(data: np.ndarray) -> np.ndarray:
    array = np.asarray(data)
    if array.size == 0:
        return np.zeros((0, 0), dtype=np.uint8)
    minimum = float(array.min())
    maximum = float(array.max())
    if maximum <= minimum:
        return np.zeros(array.shape, dtype=np.uint8)
    scaled = (array - minimum) / (maximum - minimum)
    return (scaled * 255).astype(np.uint8)
