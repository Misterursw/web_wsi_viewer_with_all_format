from __future__ import annotations

import inspect
from typing import Any

import openslide
from openslide.deepzoom import DeepZoomGenerator as OpenSlideDeepZoomGenerator

from .aslide import Slide


class DeepZoom:
    def __init__(
        self,
        slide: Slide,
        tile_size: int = 254,
        overlap: int = 1,
        limit_bounds: bool = False,
        max_level_size: int = 10000,
        biomarker: str | None = None,
    ) -> None:
        del max_level_size
        self.slide = slide
        backend_class: Any = slide.registry_entry.load_deepzoom_backend()
        if backend_class is None:
            backend_class = OpenSlideDeepZoomGenerator
        if slide.slide_family == "multiplex":
            resolved_biomarker = biomarker or slide.get_default_display_biomarker()
            backend_signature = inspect.signature(backend_class)
            if "biomarker" in backend_signature.parameters:
                self._backend = backend_class(
                    slide.backend,
                    tile_size,
                    overlap,
                    limit_bounds,
                    biomarker=resolved_biomarker,
                )
            else:
                self._backend = backend_class(
                    slide.backend, tile_size, overlap, limit_bounds
                )
        elif slide.format.lower() == ".qptiff" and hasattr(slide.backend, "_openslide"):
            brightfield_backend = slide.backend._openslide
            if brightfield_backend is None:
                raise RuntimeError("Brightfield QPTIFF OpenSlide reader is closed")
            self._backend = OpenSlideDeepZoomGenerator(
                brightfield_backend, tile_size, overlap, limit_bounds
            )
        else:
            self._backend = backend_class(
                slide.backend, tile_size, overlap, limit_bounds
            )

    @property
    def backend(self) -> Any:
        return self._backend

    @property
    def biomarker(self) -> str | None:
        if hasattr(self.backend, "biomarker"):
            return getattr(self.backend, "biomarker")
        if hasattr(self.backend, "_biomarker"):
            return getattr(self.backend, "_biomarker")
        return None

    @property
    def tile_size(self) -> int:
        return getattr(self.backend, "tile_size", 254)

    @property
    def level_count(self) -> int:
        return self.backend.level_count

    @property
    def level_tiles(self) -> Any:
        return self.backend.level_tiles

    @property
    def level_dimensions(self) -> Any:
        return self.backend.level_dimensions

    @property
    def tile_count(self) -> int:
        return self.backend.tile_count

    def get_dzi(self, image_format: str) -> str:
        return self.backend.get_dzi(image_format)

    def get_tile(self, level: int, address: tuple[int, int]) -> Any:
        return self.backend.get_tile(level, address)


ADeepZoomGenerator = DeepZoom
