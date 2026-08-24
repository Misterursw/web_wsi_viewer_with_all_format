from __future__ import annotations

from typing import Any

from openslide import AbstractSlide
from openslide.deepzoom import DeepZoomGenerator as OpenSlideDeepZoomGenerator

from .ome_tiff_slide import OmeTiffSlide


class _BiomarkerAwareDeepZoomSource(AbstractSlide):
    def __init__(self, slide: OmeTiffSlide, biomarker: str) -> None:
        AbstractSlide.__init__(self)
        self._slide = slide
        self._biomarker = biomarker

    @classmethod
    def detect_format(cls, filename: Any) -> str | None:
        del filename
        return None

    @property
    def level_count(self) -> int:
        return self._slide.level_count

    @property
    def dimensions(self) -> tuple[int, int]:
        return self._slide.dimensions

    @property
    def level_dimensions(self) -> Any:
        return self._slide.level_dimensions

    @property
    def level_downsamples(self) -> Any:
        return self._slide.level_downsamples

    @property
    def properties(self) -> Any:
        return self._slide.properties

    @property
    def associated_images(self) -> Any:
        return self._slide.associated_images

    def close(self) -> None:
        self._slide.close()

    def get_best_level_for_downsample(self, downsample: float) -> int:
        return self._slide.get_best_level_for_downsample(downsample)

    def read_region(
        self, location: tuple[int, int], level: int, size: tuple[int, int]
    ) -> Any:
        return self._slide.read_biomarker_region(location, level, size, self._biomarker)


class OmeTiffDeepZoomGenerator:
    def __init__(
        self,
        slide: OmeTiffSlide,
        tile_size: int = 254,
        overlap: int = 1,
        limit_bounds: bool = False,
        biomarker: str | None = None,
    ) -> None:
        if biomarker is None:
            biomarker = slide.get_default_display_biomarker()
        if not slide.has_biomarker(biomarker):
            raise ValueError(f"Biomarker '{biomarker}' not found")

        self._slide = slide
        self._biomarker: str = biomarker
        self._tile_size = tile_size
        self._source = _BiomarkerAwareDeepZoomSource(slide, biomarker)
        self._deepzoom = OpenSlideDeepZoomGenerator(
            self._source, tile_size, overlap, limit_bounds
        )

    @property
    def biomarker(self) -> str:
        return self._biomarker

    @property
    def tile_size(self) -> int:
        return self._tile_size

    @property
    def level_count(self) -> int:
        return self._deepzoom.level_count

    @property
    def level_tiles(self) -> Any:
        return self._deepzoom.level_tiles

    @property
    def level_dimensions(self) -> Any:
        return self._deepzoom.level_dimensions

    @property
    def tile_count(self) -> int:
        return self._deepzoom.tile_count

    def get_dzi(self, image_format: str) -> str:
        return self._deepzoom.get_dzi(image_format)

    def get_tile(self, level: int, address: tuple[int, int]) -> Any:
        return self._deepzoom.get_tile(level, address)
