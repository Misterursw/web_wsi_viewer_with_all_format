from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BaseSlideBackend(Protocol):
    level_count: int
    dimensions: tuple[int, int]
    level_dimensions: Any
    level_downsamples: Any
    properties: Any

    def close(self) -> None: ...


@runtime_checkable
class BrightfieldSlideBackend(BaseSlideBackend, Protocol):
    def read_region(
        self, location: tuple[int, int], level: int, size: tuple[int, int]
    ) -> Any: ...


@runtime_checkable
class MultiplexSlideBackend(BaseSlideBackend, Protocol):
    def list_biomarkers(self) -> list[str]: ...

    def has_biomarker(self, name: str) -> bool: ...

    def read_biomarker_region(
        self,
        location: tuple[int, int],
        level: int,
        size: tuple[int, int],
        biomarker: str,
    ) -> Any: ...

    def get_default_display_biomarker(self) -> str: ...


@runtime_checkable
class SlideBackend(BaseSlideBackend, Protocol):
    pass


@runtime_checkable
class DeepZoomBackend(Protocol):
    level_count: int
    level_tiles: Any
    level_dimensions: Any
    tile_count: int

    def get_dzi(self, image_format: str) -> str: ...

    def get_tile(self, level: int, address: tuple[int, int]) -> Any: ...
