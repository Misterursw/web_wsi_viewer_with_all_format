from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import numpy.typing as npt
from openslide import AbstractSlide
from PIL import Image

from ..errors import (
    MissingDefaultBiomarkerError,
    UnknownBiomarkerError,
    UnsupportedOperationError,
)


def is_ims_candidate(path: str) -> bool:
    file_path = Path(path)
    if file_path.suffix.lower() != ".ims":
        return False

    try:
        with h5py.File(path, "r") as handle:
            return _find_level_group(handle, "ResolutionLevel 0") is not None and bool(
                _discover_channel_metadata(handle)
            )
    except Exception:
        return False


@dataclass(frozen=True)
class _LevelInfo:
    name: str
    dataset_paths: tuple[str, ...]
    dimensions: tuple[int, int]
    downsample: float


class ImsSlide(AbstractSlide):
    @classmethod
    def detect_format(cls, filename: Any) -> str | None:
        if is_ims_candidate(filename):
            return "ims"
        return None

    def __init__(self, filename: str):
        AbstractSlide.__init__(self)
        self._filename = filename
        self._handle = h5py.File(filename, "r")
        try:
            channel_entries = _discover_channel_metadata(self._handle)
            self._channel_labels = [label for label, _ in channel_entries]
            self._channel_lookup = {
                label: offset for offset, (label, _) in enumerate(channel_entries)
            }
            self._channel_dataset_indices = tuple(
                channel_index for _, channel_index in channel_entries
            )
            if not self._channel_labels:
                raise ValueError("No IMS channel metadata found")

            self._levels = self._discover_levels()
            if not self._levels:
                raise ValueError("No IMS resolution levels found")
        except Exception:
            self.close()
            raise

    def _discover_levels(self) -> tuple[_LevelInfo, ...]:
        dataset_root = self._handle.get("DataSet")
        if not isinstance(dataset_root, h5py.Group):
            raise ValueError("IMS file missing DataSet group")

        raw_levels: list[tuple[int, _LevelInfo]] = []
        base_width = 0
        base_height = 0

        for name, obj in dataset_root.items():
            if not isinstance(obj, h5py.Group) or not name.startswith(
                "ResolutionLevel "
            ):
                continue
            level_index = _parse_resolution_level(name)
            level_group = _find_level_group(self._handle, name)
            if level_group is None:
                continue

            dataset_paths: list[str] = []
            level_dimensions: tuple[int, int] | None = None
            for channel_index in self._channel_dataset_indices:
                dataset = _get_channel_dataset(level_group, channel_index)
                if dataset is None:
                    raise ValueError(
                        f"Missing dataset for channel {channel_index} in {name}"
                    )
                dimensions = _dataset_dimensions(dataset)
                if level_dimensions is None:
                    level_dimensions = dimensions
                elif level_dimensions != dimensions:
                    raise ValueError(
                        f"Inconsistent channel dimensions in {name}: {level_dimensions} vs {dimensions}"
                    )
                dataset_name = dataset.name
                if not isinstance(dataset_name, str):
                    raise ValueError(
                        f"Invalid IMS dataset name for channel {channel_index}"
                    )
                dataset_paths.append(dataset_name)

            if level_dimensions is None:
                continue

            width, height = level_dimensions
            if level_index == 0:
                base_width = width
                base_height = height
                downsample = 1.0
            else:
                if base_width == 0 or base_height == 0:
                    raise ValueError("Resolution levels discovered before level 0")
                downsample = max(base_width / width, base_height / height)

            raw_levels.append(
                (
                    level_index,
                    _LevelInfo(
                        name=name,
                        dataset_paths=tuple(dataset_paths),
                        dimensions=level_dimensions,
                        downsample=float(downsample),
                    ),
                )
            )

        raw_levels.sort(key=lambda item: item[0])
        return tuple(level for _, level in raw_levels)

    @property
    def level_count(self) -> int:
        return len(self._levels)

    @property
    def dimensions(self) -> tuple[int, int]:
        return self._levels[0].dimensions

    @property
    def level_dimensions(self) -> tuple[tuple[int, int], ...]:
        return tuple(level.dimensions for level in self._levels)

    @property
    def level_downsamples(self) -> tuple[float, ...]:
        return tuple(level.downsample for level in self._levels)

    @property
    def properties(self) -> dict[str, str]:
        return {
            "openslide.vendor": "ims",
            "ims.channel-count": str(len(self._channel_labels)),
            "ims.level-count": str(self.level_count),
            "ims.channels": ",".join(self._channel_labels),
        }

    @property
    def associated_images(self) -> dict[str, Image.Image]:
        return {}

    def close(self) -> None:
        handle = getattr(self, "_handle", None)
        if handle is not None:
            handle.close()

    def get_best_level_for_downsample(self, downsample: float) -> int:
        if not self._levels:
            return 0
        for index in range(1, len(self._levels)):
            if self._levels[index].downsample > downsample:
                return index - 1
        return len(self._levels) - 1

    def list_biomarkers(self) -> list[str]:
        return list(self._channel_labels)

    def has_biomarker(self, name: str) -> bool:
        return name in self._channel_lookup

    def get_default_display_biomarker(self) -> str:
        for biomarker in self._channel_labels:
            upper = biomarker.upper()
            if (
                "DNA" in upper
                or "DAPI" in upper
                or "HOECHST" in upper
                or "HISTONE" in upper
            ):
                return biomarker
        if self._channel_labels:
            return self._channel_labels[0]
        raise MissingDefaultBiomarkerError("No biomarkers available in IMS file")

    def read_region(
        self, location: tuple[int, int], level: int, size: tuple[int, int]
    ) -> Image.Image:
        raise UnsupportedOperationError(
            "IMS multiplex slides require an explicit biomarker; use read_biomarker_region()"
        )

    def read_biomarker_region(
        self,
        location: tuple[int, int],
        level: int,
        size: tuple[int, int],
        biomarker: str,
    ) -> Image.Image:
        if level < 0 or level >= self.level_count:
            raise ValueError(
                f"IMS level {level} not available (0-{self.level_count - 1})"
            )
        if biomarker not in self._channel_lookup:
            raise UnknownBiomarkerError(f"Biomarker '{biomarker}' not found")

        channel_offset = self._channel_lookup[biomarker]
        level_info = self._levels[level]
        dataset_obj = self._handle[level_info.dataset_paths[channel_offset]]
        if not isinstance(dataset_obj, h5py.Dataset):
            raise ValueError(
                f"IMS dataset path no longer points to a dataset: {level_info.dataset_paths[channel_offset]}"
            )

        x, y = location
        width, height = size
        plane = _dataset_plane(dataset_obj)
        region = np.asarray(plane[y : y + height, x : x + width])
        if region.size == 0:
            region = np.zeros((height, width), dtype=np.uint8)
        if region.dtype != np.uint8:
            region = _normalize_to_uint8(region)
        rgba = np.stack([region, region, region, np.full_like(region, 255)], axis=-1)
        return Image.fromarray(rgba, mode="RGBA")


def _find_level_group(handle: h5py.File, level_name: str) -> h5py.Group | None:
    dataset_root = handle.get("DataSet")
    if not isinstance(dataset_root, h5py.Group):
        return None
    level_group = dataset_root.get(level_name)
    if not isinstance(level_group, h5py.Group):
        return None

    if "TimePoint 0" in level_group and isinstance(
        level_group["TimePoint 0"], h5py.Group
    ):
        preferred_group = level_group["TimePoint 0"]
        if isinstance(preferred_group, h5py.Group):
            return preferred_group

    for key in sorted(level_group.keys()):
        candidate = level_group[key]
        if key.startswith("TimePoint ") and isinstance(candidate, h5py.Group):
            return candidate
    return None


def _discover_channel_metadata(handle: h5py.File) -> list[tuple[str, int]]:
    info_root = handle.get("DataSetInfo")
    if not isinstance(info_root, h5py.Group):
        return []

    channel_groups: list[tuple[int, h5py.Group]] = []
    for key, obj in info_root.items():
        if not isinstance(obj, h5py.Group) or not key.startswith("Channel "):
            continue
        channel_index = _parse_channel_index(key)
        if channel_index is None:
            continue
        channel_groups.append((channel_index, obj))

    channel_groups.sort(key=lambda item: item[0])

    labels: list[tuple[str, int]] = []
    seen_labels: set[str] = set()
    for channel_index, obj in channel_groups:
        label = (
            _decode_text_attribute(obj.attrs.get("Name")) or f"Channel {channel_index}"
        )
        original_label = label
        suffix = 2
        while label in seen_labels:
            label = f"{original_label} ({suffix})"
            suffix += 1
        seen_labels.add(label)
        labels.append((label, channel_index))
    return labels


def _get_channel_dataset(
    level_group: h5py.Group, channel_index: int
) -> h5py.Dataset | None:
    channel_group = level_group.get(f"Channel {channel_index}")
    if not isinstance(channel_group, h5py.Group):
        return None
    dataset = channel_group.get("Data")
    if not isinstance(dataset, h5py.Dataset):
        return None
    return dataset


def _dataset_dimensions(dataset: h5py.Dataset) -> tuple[int, int]:
    shape = tuple(int(value) for value in dataset.shape)
    if len(shape) == 2:
        height, width = shape
        return (width, height)
    if len(shape) == 3 and shape[0] in {1, 4}:
        _, height, width = shape
        return (width, height)
    raise ValueError(f"Unsupported IMS dataset shape: {shape}")


def _dataset_plane(dataset: h5py.Dataset) -> npt.NDArray[np.generic]:
    array = np.asarray(dataset)
    if array.ndim == 2:
        return array
    if array.ndim == 3 and array.shape[0] in {1, 4}:
        return np.asarray(array[0])
    raise ValueError(f"Unsupported IMS dataset shape: {array.shape}")


def _decode_text_attribute(raw_value: object) -> str:
    if raw_value is None:
        return ""
    if isinstance(raw_value, bytes):
        return raw_value.decode("utf-8", errors="ignore").strip("\x00 ")
    if isinstance(raw_value, str):
        return raw_value.strip()
    if isinstance(raw_value, np.ndarray):
        if raw_value.dtype.kind in {"S", "U"}:
            flattened = raw_value.reshape(-1).tolist()
            parts: list[str] = []
            for item in flattened:
                if isinstance(item, bytes):
                    parts.append(item.decode("utf-8", errors="ignore"))
                else:
                    parts.append(str(item))
            return "".join(parts).strip("\x00 ")
        return str(raw_value.tolist()).strip()
    return str(raw_value).strip()


def _parse_resolution_level(name: str) -> int:
    try:
        return int(name.split()[-1])
    except Exception as exc:
        raise ValueError(f"Invalid IMS resolution level name: {name}") from exc


def _parse_channel_index(name: str) -> int | None:
    if not name.startswith("Channel "):
        return None
    try:
        return int(name.split()[-1])
    except Exception:
        return None


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


__all__ = ["ImsSlide", "is_ims_candidate"]
