from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

import numpy as np
from PIL import Image

from .adapter import CziAdapter
from ..errors import UnsupportedOperationError


class _CziSlideAdapter(Protocol):
    @property
    def dimensions(self) -> tuple[int, int]: ...

    @property
    def level_count(self) -> int: ...

    @property
    def level_dimensions(self) -> tuple[tuple[int, int], ...]: ...

    @property
    def level_downsamples(self) -> tuple[float, ...]: ...

    @property
    def properties(self) -> dict[str, str]: ...

    def classify_slide_family(self) -> str: ...

    def read_region(
        self,
        location: tuple[int, int],
        level: int,
        size: tuple[int, int],
    ) -> Any: ...

    def get_thumbnail(self, size: tuple[int, int]) -> Any: ...

    def list_biomarkers(self) -> list[str]: ...

    def get_default_display_biomarker(self) -> str: ...

    def read_biomarker_region(
        self,
        location: tuple[int, int],
        level: int,
        size: tuple[int, int],
        biomarker: str,
    ) -> Any: ...

    def get_best_level_for_downsample(self, downsample: float) -> int: ...

    def close(self) -> None: ...


class CziSlide:
    def __init__(self, filename: str, adapter: _CziSlideAdapter | None = None):
        self.filename = filename
        if adapter is None:
            try:
                adapter = CziAdapter.from_pylibczirw(filename)
            except (RuntimeError, ImportError):
                try:
                    adapter = CziAdapter.from_bioformats(filename)
                except (RuntimeError, ImportError):
                    try:
                        adapter = CziAdapter.from_czifile(filename)
                    except ImportError as exc:
                        raise ImportError(
                            "CZI adapter dependency is not configured; pylibCZIrw, Bio-Formats, and czifile backends are unavailable"
                        ) from exc
        self._adapter = adapter
        self._slide_family = self._adapter.classify_slide_family()

    @property
    def slide_family(self) -> str:
        return self._slide_family

    def classify_slide_family(self) -> str:
        return self._adapter.classify_slide_family()

    @property
    def dimensions(self) -> tuple[int, int]:
        return self._adapter.dimensions

    @property
    def level_count(self) -> int:
        return self._adapter.level_count

    @property
    def level_dimensions(self) -> tuple[tuple[int, int], ...]:
        return self._adapter.level_dimensions

    @property
    def level_downsamples(self) -> tuple[float, ...]:
        return self._adapter.level_downsamples

    @property
    def properties(self) -> Mapping[str, Any]:
        return self._adapter.properties

    def get_best_level_for_downsample(self, downsample: float) -> int:
        return self._adapter.get_best_level_for_downsample(downsample)

    def read_region(
        self, location: tuple[int, int], level: int, size: tuple[int, int]
    ) -> Any:
        if self.slide_family != "brightfield":
            raise UnsupportedOperationError(
                "CZI multiplex slides require an explicit biomarker"
            )
        return self._adapter.read_region(location, level, size)

    def get_thumbnail(self, size: tuple[int, int]) -> Any:
        if self.slide_family != "brightfield":
            raise UnsupportedOperationError(
                "CZI multiplex slides do not support generic thumbnails"
            )
        return self._adapter.get_thumbnail(size)

    def list_biomarkers(self) -> list[str]:
        if self.slide_family != "multiplex":
            raise UnsupportedOperationError(
                "CZI brightfield slides do not expose biomarkers"
            )
        return self._adapter.list_biomarkers()

    def get_default_display_biomarker(self) -> str:
        if self.slide_family != "multiplex":
            raise UnsupportedOperationError(
                "CZI brightfield slides do not expose biomarkers"
            )
        return self._adapter.get_default_display_biomarker()

    def read_biomarker_region(
        self,
        location: tuple[int, int],
        level: int,
        size: tuple[int, int],
        biomarker: str,
    ) -> Any:
        if self.slide_family != "multiplex":
            raise UnsupportedOperationError(
                "CZI brightfield slides do not expose biomarkers"
            )
        image = self._adapter.read_biomarker_region(location, level, size, biomarker)
        return _biomarker_region_to_rgba(image)

    def close(self) -> None:
        self._adapter.close()


def _biomarker_region_to_rgba(image: Any) -> Image.Image:
    if hasattr(image, "mode") and image.mode == "RGBA":
        return image
    data = np.asarray(image)
    if data.ndim == 3 and data.shape[-1] == 1:
        data = data[:, :, 0]
    if data.ndim == 2:
        if data.dtype != np.uint8:
            data = _normalize_to_uint8(data)
        rgba = np.stack([data, data, data, np.full_like(data, 255)], axis=-1)
        return Image.fromarray(rgba, mode="RGBA")
    pil_image = image if hasattr(image, "mode") else Image.fromarray(data)
    if pil_image.mode != "RGBA":
        return pil_image.convert("RGBA")
    return pil_image


def _normalize_to_uint8(data: Any) -> np.ndarray:
    array = np.asarray(data)
    if array.size == 0:
        return np.zeros(array.shape, dtype=np.uint8)
    minimum = float(array.min())
    maximum = float(array.max())
    if maximum <= minimum:
        return np.zeros(array.shape, dtype=np.uint8)
    scaled = (array - minimum) / (maximum - minimum)
    return (scaled * 255).astype(np.uint8)
