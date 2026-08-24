"""
DeepZoom generator for QPTiff files
Provides tiled access to QPTiff slides for web-based viewing
"""

import math
from typing import Tuple, Optional
from PIL import Image
import numpy as np

from .qptiff_slide import QptiffSlide


class QptiffDeepZoomGenerator:
    """DeepZoom generator for QPTiff slides"""

    def __init__(
        self,
        osr,
        tile_size: int = 254,
        overlap: int = 1,
        limit_bounds: bool = False,
        biomarker: Optional[str] = None,
    ):
        self._osr = osr
        self._tile_size = tile_size
        self._overlap = overlap
        self._limit_bounds = limit_bounds

        # Get the actual QptiffSlide object
        if hasattr(osr, "_osr") and hasattr(osr._osr, "get_biomarkers"):
            # This is a Slide object wrapping a QptiffSlide
            self._qptiff_slide = osr._osr
        elif hasattr(osr, "get_biomarkers"):
            # This is a QptiffSlide object directly
            self._qptiff_slide = osr
        else:
            raise ValueError("Object does not appear to be a QPTiff slide")

        # Select biomarker
        biomarkers = self._qptiff_slide.get_biomarkers()
        if biomarker is not None:
            if biomarker not in biomarkers:
                raise ValueError(
                    f"Biomarker '{biomarker}' not found. Available: {biomarkers}"
                )
            self._biomarker = biomarker
        else:
            self._biomarker = self._qptiff_slide.get_default_display_biomarker()

        # Calculate DeepZoom levels
        self._calculate_dz_levels()

    def _calculate_dz_levels(self):
        """Calculate DeepZoom levels based on slide dimensions"""
        if not self._osr.level_dimensions:
            self._dz_levels = []
            return

        # Get the largest dimension from level 0
        max_dimension = max(self._osr.level_dimensions[0])

        # Calculate number of DeepZoom levels needed
        # Each level halves the dimensions until we reach tile_size
        self._dz_level_count = math.ceil(math.log2(max_dimension / self._tile_size)) + 1

        # Calculate dimensions for each DeepZoom level
        self._dz_levels = []
        base_width, base_height = self._osr.level_dimensions[0]

        for level in range(self._dz_level_count):
            # Calculate dimensions for this DeepZoom level
            scale = 2 ** (self._dz_level_count - 1 - level)
            width = max(1, math.ceil(base_width / scale))
            height = max(1, math.ceil(base_height / scale))

            # Calculate number of tiles needed
            tiles_x = math.ceil(width / self._tile_size)
            tiles_y = math.ceil(height / self._tile_size)

            self._dz_levels.append(
                {
                    "width": width,
                    "height": height,
                    "tiles_x": tiles_x,
                    "tiles_y": tiles_y,
                    "scale": scale,
                }
            )

    @property
    def level_count(self) -> int:
        """Number of DeepZoom levels"""
        return self._dz_level_count

    @property
    def level_tiles(self) -> Tuple[Tuple[int, int], ...]:
        """Number of tiles (columns, rows) for each level"""
        return tuple((level["tiles_x"], level["tiles_y"]) for level in self._dz_levels)

    @property
    def level_dimensions(self) -> Tuple[Tuple[int, int], ...]:
        """Dimensions (width, height) for each DeepZoom level"""
        return tuple((level["width"], level["height"]) for level in self._dz_levels)

    @property
    def tile_count(self) -> int:
        """Total number of tiles across all levels"""
        return sum(level["tiles_x"] * level["tiles_y"] for level in self._dz_levels)

    def get_dzi(self, format: str = "png") -> str:
        """Get DZI (DeepZoom Image) XML metadata

        Args:
            format: Image format ('png' or 'jpeg')

        Returns:
            XML string for DZI file
        """
        if not self._dz_levels:
            return ""

        width, height = self._osr.level_dimensions[0]

        dzi_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Image xmlns="http://schemas.microsoft.com/deepzoom/2008"
       Format="{format}"
       Overlap="{self._overlap}"
       TileSize="{self._tile_size}">
    <Size Width="{width}" Height="{height}"/>
</Image>'''

        return dzi_xml

    def get_tile(self, level: int, address: Tuple[int, int]) -> Image.Image:
        """Get a tile at the specified level and address

        Args:
            level: DeepZoom level
            address: (column, row) tuple for tile address

        Returns:
            PIL Image object
        """
        if level >= self._dz_level_count or level < 0:
            raise ValueError(
                f"Level {level} not available (0-{self._dz_level_count - 1})"
            )

        col, row = address
        level_info = self._dz_levels[level]

        if (
            col >= level_info["tiles_x"]
            or row >= level_info["tiles_y"]
            or col < 0
            or row < 0
        ):
            raise ValueError(
                f"Tile address ({col}, {row}) not available for level {level}"
            )

        # Calculate tile boundaries
        tile_left = col * self._tile_size
        tile_top = row * self._tile_size
        tile_right = min(tile_left + self._tile_size, level_info["width"])
        tile_bottom = min(tile_top + self._tile_size, level_info["height"])

        tile_width = tile_right - tile_left
        tile_height = tile_bottom - tile_top

        # Add overlap
        if self._overlap > 0:
            # Expand tile boundaries by overlap amount
            overlap_left = self._overlap if col > 0 else 0
            overlap_top = self._overlap if row > 0 else 0
            overlap_right = self._overlap if col < level_info["tiles_x"] - 1 else 0
            overlap_bottom = self._overlap if row < level_info["tiles_y"] - 1 else 0

            tile_left = max(0, tile_left - overlap_left)
            tile_top = max(0, tile_top - overlap_top)
            tile_right = min(level_info["width"], tile_right + overlap_right)
            tile_bottom = min(level_info["height"], tile_bottom + overlap_bottom)

            tile_width = tile_right - tile_left
            tile_height = tile_bottom - tile_top

        # Map DeepZoom coordinates to slide coordinates
        scale = level_info["scale"]
        slide_left = int(tile_left * scale)
        slide_top = int(tile_top * scale)
        slide_width = int(tile_width * scale)
        slide_height = int(tile_height * scale)

        # Find the best slide level for this scale
        slide_level = self._osr.get_best_level_for_downsample(scale)

        try:
            # Always use biomarker-specific method for QPTiff files
            if hasattr(self._qptiff_slide, "read_region_biomarker"):
                # Use biomarker-specific method
                tile_image = self._qptiff_slide.read_region_biomarker(
                    (slide_left, slide_top),
                    slide_level,
                    (slide_width, slide_height),
                    self._biomarker,
                )
            else:
                # This shouldn't happen for QPTiff files, but provide fallback
                raise ValueError(
                    "QPTiff slide does not support biomarker-specific reading"
                )

            # Resize to exact tile dimensions if needed
            if tile_image.size != (tile_width, tile_height):
                tile_image = tile_image.resize(
                    (tile_width, tile_height), Image.Resampling.LANCZOS
                )

            # Pad to full tile size if necessary
            if (
                tile_width < self._tile_size + 2 * self._overlap
                or tile_height < self._tile_size + 2 * self._overlap
            ):
                # Create a new image with the full tile size
                full_tile_width = self._tile_size + 2 * self._overlap
                full_tile_height = self._tile_size + 2 * self._overlap

                # Use white background for padding
                padded_image = Image.new(
                    "RGB", (full_tile_width, full_tile_height), (255, 255, 255)
                )

                # Paste the actual tile data
                paste_x = (full_tile_width - tile_width) // 2
                paste_y = (full_tile_height - tile_height) // 2
                padded_image.paste(tile_image, (paste_x, paste_y))

                tile_image = padded_image

            return tile_image

        except Exception as e:
            # Return a blank tile if reading fails
            tile_size_with_overlap = self._tile_size + 2 * self._overlap
            blank_tile = Image.new(
                "RGB", (tile_size_with_overlap, tile_size_with_overlap), (255, 255, 255)
            )
            return blank_tile

    def get_tile_coordinates(
        self, level: int, address: Tuple[int, int]
    ) -> Tuple[int, int, int, int]:
        """Get the slide coordinates for a tile

        Args:
            level: DeepZoom level
            address: (column, row) tuple for tile address

        Returns:
            (left, top, width, height) tuple in slide coordinates
        """
        if level >= self._dz_level_count or level < 0:
            raise ValueError(
                f"Level {level} not available (0-{self._dz_level_count - 1})"
            )

        col, row = address
        level_info = self._dz_levels[level]

        # Calculate tile boundaries in DeepZoom coordinates
        tile_left = col * self._tile_size
        tile_top = row * self._tile_size
        tile_right = min(tile_left + self._tile_size, level_info["width"])
        tile_bottom = min(tile_top + self._tile_size, level_info["height"])

        tile_width = tile_right - tile_left
        tile_height = tile_bottom - tile_top

        # Map to slide coordinates
        scale = level_info["scale"]
        slide_left = int(tile_left * scale)
        slide_top = int(tile_top * scale)
        slide_width = int(tile_width * scale)
        slide_height = int(tile_height * scale)

        return slide_left, slide_top, slide_width, slide_height

    def set_biomarker(self, biomarker: str):
        """Change the biomarker used for tile generation

        Args:
            biomarker: Name of the biomarker to use
        """
        biomarkers = self._qptiff_slide.get_biomarkers()
        if biomarker not in biomarkers:
            raise ValueError(
                f"Biomarker '{biomarker}' not found. Available: {biomarkers}"
            )

        self._biomarker = biomarker

    def get_current_biomarker(self) -> str:
        """Get the currently selected biomarker"""
        return self._biomarker
