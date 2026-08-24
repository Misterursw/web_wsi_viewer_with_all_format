from __future__ import annotations

from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
from openslide import AbstractSlide
import tifffile

from ..errors import (
    MissingDefaultBiomarkerError,
    UnknownBiomarkerError,
    UnsupportedOperationError,
)
from .probe import is_ome_tiff_candidate


class OmeTiffSlide(AbstractSlide):
    @classmethod
    def detect_format(cls, filename: Any) -> str | None:
        if is_ome_tiff_candidate(filename):
            return "ome_tiff"
        return None

    def __init__(self, filename: str):
        AbstractSlide.__init__(self)
        self._filename = filename
        self._channels: dict[str, Path] = {}
        self._channel_order: list[str] = []
        self._channel_indices: dict[str, int] = {}
        self._shape: tuple[int, int] = (0, 0)
        self._dtype = None
        self._mpp = None
        self._single_file_path: Path | None = None
        self._single_file_axes: str | None = None
        self._discover_channels(Path(filename))

    def _discover_channels(self, anchor_path: Path) -> None:
        if not is_ome_tiff_candidate(str(anchor_path)):
            raise ValueError(
                f"Not an OME-compatible TIFF multiplex anchor: {anchor_path}"
            )

        anchor_signature = self._read_signature(anchor_path)
        self._shape = anchor_signature["shape"]
        self._dtype = anchor_signature["dtype"]
        self._mpp = anchor_signature["mpp"]

        if anchor_signature["ome_channels"]:
            self._single_file_path = anchor_path
            self._single_file_axes = anchor_signature["axes"]
            for index, label in enumerate(anchor_signature["ome_channels"]):
                self._channels[label] = anchor_path
                self._channel_order.append(label)
                self._channel_indices[label] = index
            return

        if anchor_signature["page_channels"]:
            self._single_file_path = anchor_path
            self._single_file_axes = anchor_signature["axes"]
            for index, label in enumerate(anchor_signature["page_channels"]):
                self._channels[label] = anchor_path
                self._channel_order.append(label)
                self._channel_indices[label] = index
            return

        for candidate in sorted(anchor_path.parent.iterdir()):
            if not candidate.is_file():
                continue
            if candidate.suffix.lower() not in {".tif", ".tiff"}:
                continue
            if not is_ome_tiff_candidate(str(candidate)):
                continue
            try:
                signature = self._read_signature(candidate)
            except Exception:
                continue
            if signature["shape"] != self._shape or signature["dtype"] != self._dtype:
                continue
            label = signature["label"]
            if label in self._channels:
                continue
            self._channels[label] = candidate
            self._channel_order.append(label)

        if not self._channel_order:
            raise ValueError(f"No readable channels discovered for {anchor_path}")

    def _read_signature(self, path: Path) -> dict[str, Any]:
        with tifffile.TiffFile(path) as tiff:
            series = tiff.series[0]
            page: Any = tiff.pages[0]
            page_name = page.tags.get("PageName")
            ome_channels = _extract_ome_channel_names(tiff.ome_metadata)
            page_channels = _extract_page_channel_names_from_tiff(tiff)
            mpp = _extract_ome_mpp(tiff.ome_metadata)
            if mpp is None:
                mpp = _extract_tiff_resolution_mpp(page)
            return {
                "shape": tuple(int(value) for value in series.shape[-2:]),
                "axes": series.axes,
                "dtype": page.dtype,
                "label": str(page_name.value) if page_name else path.stem,
                "mpp": mpp,
                "ome_channels": ome_channels,
                "page_channels": page_channels,
            }

    @property
    def level_count(self) -> int:
        return 1

    @property
    def dimensions(self) -> tuple[int, int]:
        return (self._shape[1], self._shape[0])

    @property
    def level_dimensions(self) -> tuple[tuple[int, int], ...]:
        return (self.dimensions,)

    @property
    def level_downsamples(self) -> tuple[float, ...]:
        return (1.0,)

    @property
    def properties(self) -> dict[str, str]:
        properties = {
            "openslide.vendor": "ome-tiff",
            "ome.channel-count": str(len(self._channel_order)),
            "ome.channels": ",".join(self._channel_order),
        }
        if self._mpp is not None:
            properties["openslide.mpp-x"] = str(self._mpp)
            properties["openslide.mpp-y"] = str(self._mpp)
        return properties

    @property
    def associated_images(self) -> dict[str, Image.Image]:
        return {}

    def close(self) -> None:
        return None

    def get_best_level_for_downsample(self, downsample: float) -> int:
        return 0

    def list_biomarkers(self) -> list[str]:
        return list(self._channel_order)

    def read_region(
        self, location: tuple[int, int], level: int, size: tuple[int, int]
    ) -> Image.Image:
        raise UnsupportedOperationError(
            "OME-TIFF multiplex slides require an explicit biomarker; use read_biomarker_region()"
        )

    def has_biomarker(self, name: str) -> bool:
        return name in self._channels

    def get_default_display_biomarker(self) -> str:
        for biomarker in self._channel_order:
            upper = biomarker.upper()
            if "DAPI" in upper or "HISTONE" in upper:
                return biomarker
        if self._channel_order:
            return self._channel_order[0]
        raise MissingDefaultBiomarkerError("No biomarker available for display")

    def read_biomarker_region(
        self,
        location: tuple[int, int],
        level: int,
        size: tuple[int, int],
        biomarker: str,
    ) -> Image.Image:
        if level != 0:
            raise ValueError(
                "OME-TIFF multiplex backend currently supports only level 0"
            )
        if biomarker not in self._channels:
            raise UnknownBiomarkerError(f"Biomarker '{biomarker}' not found")

        x, y = location
        width, height = size
        with tifffile.TiffFile(self._channels[biomarker]) as tiff:
            data = tiff.asarray()
        if self._single_file_path is not None and self._single_file_axes is not None:
            channel_index = self._channel_indices[biomarker]
            plane = _extract_channel_plane(
                np.asarray(data), self._single_file_axes, channel_index
            )
        else:
            plane = _coerce_channel_plane(data)
        region = np.asarray(plane[y : y + height, x : x + width])
        if region.size == 0:
            region = np.zeros((height, width), dtype=np.uint8)
        if region.dtype != np.uint8:
            region = _normalize_to_uint8(region)
        rgba = np.stack([region, region, region, np.full_like(region, 255)], axis=-1)
        return Image.fromarray(rgba, mode="RGBA")


def _normalize_to_uint8(data: np.ndarray) -> np.ndarray:
    data = np.asarray(data)
    if data.size == 0:
        return np.zeros((0, 0), dtype=np.uint8)
    minimum = float(data.min())
    maximum = float(data.max())
    if maximum <= minimum:
        return np.zeros(data.shape, dtype=np.uint8)
    scaled = (data - minimum) / (maximum - minimum)
    return (scaled * 255).astype(np.uint8)


def _coerce_channel_plane(data: Any) -> np.ndarray:
    array = np.asarray(data)
    if array.ndim <= 2:
        return array

    squeezed = np.squeeze(array)
    if squeezed.ndim == 2:
        return squeezed

    if squeezed.ndim > 2:
        return np.asarray(squeezed[0])
    return np.asarray(squeezed)


def _extract_page_channel_names(path: Path) -> list[str]:
    with tifffile.TiffFile(path) as tiff:
        return _extract_page_channel_names_from_tiff(tiff)


def _extract_page_channel_names_from_tiff(tiff: tifffile.TiffFile) -> list[str]:
    names: list[str] = []
    for page in tiff.pages:
        tags = getattr(page, "tags", None)
        if tags is None:
            return []
        page_name = tags.get("PageName")
        if page_name is None:
            return []
        names.append(str(page_name.value))
    return names if len(names) > 1 else []


def _extract_ome_channel_names(ome_metadata: str | None) -> list[str]:
    if not ome_metadata:
        return []
    root = ET.fromstring(ome_metadata)
    pixels = _find_ome_pixels(root)
    channels = []
    if pixels is not None:
        channels = [child for child in pixels if _local_name(child.tag) == "Channel"]
    if not channels:
        channels = [element for element in root.iter() if _local_name(element.tag) == "Channel"]
    names: list[str] = []
    for index, channel in enumerate(channels):
        names.append(channel.attrib.get("Name") or f"Channel {index}")
    return names


def _extract_ome_mpp(ome_metadata: str | None) -> float | None:
    if not ome_metadata:
        return None
    root = ET.fromstring(ome_metadata)
    pixels = _find_ome_pixels(root)
    if pixels is None:
        return None

    x_mpp = _physical_size_to_micrometers(
        pixels.attrib.get("PhysicalSizeX"), pixels.attrib.get("PhysicalSizeXUnit")
    )
    y_mpp = _physical_size_to_micrometers(
        pixels.attrib.get("PhysicalSizeY"), pixels.attrib.get("PhysicalSizeYUnit")
    )
    values = [value for value in (x_mpp, y_mpp) if value is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _find_ome_pixels(root: ET.Element) -> ET.Element | None:
    for element in root.iter():
        if _local_name(element.tag) == "Pixels":
            return element
    return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


def _physical_size_to_micrometers(value: str | None, unit: str | None) -> float | None:
    if value is None:
        return None
    try:
        size = float(value)
    except ValueError:
        return None

    normalized_unit = (unit or "um").strip().lower().replace("\u00b5", "u").replace("\u03bc", "u")
    factors = {
        "um": 1.0,
        "micrometer": 1.0,
        "micrometre": 1.0,
        "nm": 0.001,
        "nanometer": 0.001,
        "nanometre": 0.001,
        "mm": 1000.0,
        "millimeter": 1000.0,
        "millimetre": 1000.0,
        "cm": 10000.0,
        "m": 1000000.0,
    }
    factor = factors.get(normalized_unit)
    if factor is None:
        return None
    return size * factor


def _extract_tiff_resolution_mpp(page: Any) -> float | None:
    x_resolution = page.tags.get("XResolution")
    y_resolution = page.tags.get("YResolution")
    resolution_unit = page.tags.get("ResolutionUnit")
    unit_value = resolution_unit.value if resolution_unit is not None else None
    if unit_value == 2:
        unit_micrometers = 25400.0
    elif unit_value == 3:
        unit_micrometers = 10000.0
    else:
        return None

    values = []
    for resolution in (x_resolution, y_resolution):
        if resolution is None:
            continue
        num, den = resolution.value
        if num:
            values.append(unit_micrometers * den / num)
    if not values:
        return None
    return sum(values) / len(values)


def _extract_channel_plane(
    data: np.ndarray, axes: str, channel_index: int
) -> np.ndarray:
    array = np.asarray(data)
    if axes == "CYX":
        return array[channel_index]
    if axes == "IYX":
        return array[channel_index]
    if axes == "QYX":
        return array[channel_index]
    if axes == "YX":
        return array
    if "C" in axes:
        axis = axes.index("C")
        return np.take(array, channel_index, axis=axis)
    return array
