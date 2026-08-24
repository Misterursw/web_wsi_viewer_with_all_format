from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import h5py
import numpy as np
import numpy.typing as npt
from PIL import Image

from .errors import (
    MissingDefaultBiomarkerError,
    UnknownBiomarkerError,
    UnsupportedOperationError,
)


_HDF5_EXTENSIONS = {".h5", ".hdf5", ".h5ad"}
_MARKER_ATTRIBUTE_NAMES = ("markers", "marker_names", "channel_names", "channels")


def is_hdf5_multiplex_candidate(path: str) -> bool:
    file_path = Path(path)
    if file_path.suffix.lower() not in _HDF5_EXTENSIONS:
        return False

    try:
        with h5py.File(path, "r") as handle:
            for dataset in _iter_datasets(handle):
                if _is_multiplex_dataset(dataset):
                    return True
    except Exception:
        return False

    return False


def _iter_datasets(handle: h5py.File) -> list[h5py.Dataset]:
    datasets: list[h5py.Dataset] = []

    def visitor(name: str, obj: Any) -> None:
        if isinstance(obj, h5py.Dataset):
            datasets.append(obj)

    handle.visititems(visitor)
    return datasets


def _is_multiplex_dataset(dataset: h5py.Dataset) -> bool:
    if len(dataset.shape) != 3:
        return False

    channel_count = int(dataset.shape[0])
    if channel_count <= 1:
        return False

    markers = _extract_markers(dataset)
    return markers is not None and len(markers) == channel_count


def _extract_markers(dataset: h5py.Dataset) -> list[str] | None:
    for attribute_name in _MARKER_ATTRIBUTE_NAMES:
        if attribute_name not in dataset.attrs:
            continue
        markers = _normalize_marker_values(dataset.attrs[attribute_name])
        if markers:
            return markers
    return None


def _normalize_marker_values(raw_value: object) -> list[str]:
    values: list[object]
    if raw_value is None:
        return []
    if isinstance(raw_value, (bytes, str)):
        values = [raw_value]
    elif isinstance(raw_value, np.ndarray):
        values = list(cast(Sequence[object], raw_value.tolist()))
    elif isinstance(raw_value, Sequence):
        values = list(raw_value)
    else:
        values = [raw_value]

    normalized: list[str] = []
    for value in values:
        decoded = _decode_scalar(value)
        text = str(decoded).strip()
        if text:
            normalized.append(text)
    return normalized


def _decode_scalar(value: object) -> object:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    decoder = getattr(value, "decode", None)
    if callable(decoder) and not isinstance(value, str):
        try:
            return decoder("utf-8")
        except Exception:
            return value
    return value


class Hdf5Slide:
    _filename: str
    _handle: h5py.File
    _dataset: h5py.Dataset
    _biomarkers: list[str]
    _channels: dict[str, int]

    def __init__(self, filename: str):
        self._filename = filename
        self._handle = h5py.File(filename, "r")
        self._dataset = self._find_dataset()
        markers = _extract_markers(self._dataset)
        self._biomarkers = list(markers or [])
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
        candidates = [
            dataset
            for dataset in _iter_datasets(self._handle)
            if _is_multiplex_dataset(dataset)
        ]
        if not candidates:
            self.close()
            raise ValueError(f"No multiplex HDF5 dataset found in {self._filename}")
        candidates.sort(key=lambda dataset: _dataset_sort_key(dataset))
        return candidates[0]

    @property
    def level_count(self) -> int:
        return 1

    @property
    def dimensions(self) -> tuple[int, int]:
        _channels, height, width = self._dataset.shape
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
            "hdf5.dataset": _dataset_name(self._dataset),
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


def _dataset_name(dataset: h5py.Dataset) -> str:
    name = dataset.name
    if isinstance(name, str) and name:
        return name
    return "/"


def _dataset_sort_key(dataset: h5py.Dataset) -> tuple[int, str]:
    name = _dataset_name(dataset)
    return (name.count("/"), name)


def _normalize_to_uint8(data: npt.NDArray[np.generic]) -> npt.NDArray[np.uint8]:
    array = np.asarray(data, dtype=np.float32)
    if array.size == 0:
        return np.zeros((0, 0), dtype=np.uint8)
    minimum = float(array.min())
    maximum = float(array.max())
    if maximum <= minimum:
        return np.zeros(array.shape, dtype=np.uint8)
    scaled = (array - minimum) / (maximum - minimum)
    return (scaled * 255).astype(np.uint8)


__all__ = ["Hdf5Slide", "is_hdf5_multiplex_candidate"]
