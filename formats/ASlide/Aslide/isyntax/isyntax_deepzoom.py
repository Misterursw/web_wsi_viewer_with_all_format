"""
DeepZoom generator for iSyntax slides
"""

import math
from typing import Tuple
from PIL import Image
from .isyntax_slide import IsyntaxSlide





class IsyntaxDeepZoomGenerator:
    """DeepZoom generator for iSyntax slides"""
    
    def __init__(self, osr: 'IsyntaxSlide', tile_size: int = 254, overlap: int = 1, limit_bounds: bool = False):
        """Initialize DeepZoom generator
        
        Args:
            osr: IsyntaxSlide object
            tile_size: Tile size (default: 254)
            overlap: Tile overlap (default: 1)
            limit_bounds: Whether to limit bounds (default: False)
        """
        self._osr = osr
        self._tile_size = tile_size
        self._overlap = overlap
        self._limit_bounds = limit_bounds
        
        # Calculate DeepZoom levels
        self._dz_levels = self._calculate_dz_levels()
    
    def _calculate_dz_levels(self) -> int:
        """Calculate the number of DeepZoom levels"""
        # Get the dimensions of the highest resolution level
        width, height = self._osr.dimensions
        
        # Calculate the number of levels needed
        max_dimension = max(width, height)
        levels = math.ceil(math.log2(max_dimension)) + 1
        
        return levels
    
    @property
    def level_count(self) -> int:
        """Number of DeepZoom levels"""
        return self._dz_levels
    
    @property
    def tile_count(self) -> int:
        """Total number of tiles in the image"""
        total = 0
        for level in range(self._dz_levels):
            cols, rows = self.level_tiles[level]
            total += cols * rows
        return total
    
    @property
    def level_tiles(self) -> Tuple[Tuple[int, int], ...]:
        """Number of tiles in each level as (columns, rows)"""
        tiles = []
        for level in range(self._dz_levels):
            level_width, level_height = self.level_dimensions[level]
            cols = math.ceil(level_width / self._tile_size)
            rows = math.ceil(level_height / self._tile_size)
            tiles.append((cols, rows))
        return tuple(tiles)
    
    @property
    def level_dimensions(self) -> Tuple[Tuple[int, int], ...]:
        """Dimensions of each DeepZoom level as (width, height)"""
        dimensions = []
        base_width, base_height = self._osr.dimensions
        
        for level in range(self._dz_levels):
            # Calculate dimensions for this DeepZoom level
            scale = 2 ** (self._dz_levels - level - 1)
            width = max(1, base_width // scale)
            height = max(1, base_height // scale)
            dimensions.append((width, height))
        
        return tuple(dimensions)
    
    def get_tile(self, level: int, address: Tuple[int, int]) -> Image.Image:
        """Get a DeepZoom tile
        
        Args:
            level: DeepZoom level
            address: Tile address as (column, row)
            
        Returns:
            PIL Image object
        """
        col, row = address
        
        # Calculate tile position and size
        tile_width = self._tile_size
        tile_height = self._tile_size
        
        # Get level dimensions
        level_width, level_height = self.level_dimensions[level]
        
        # Calculate position in the DeepZoom level
        x = col * self._tile_size
        y = row * self._tile_size
        
        # Adjust for overlap
        if col > 0:
            x -= self._overlap
            tile_width += self._overlap
        if row > 0:
            y -= self._overlap
            tile_height += self._overlap
        
        # Clip to level bounds
        if x + tile_width > level_width:
            tile_width = level_width - x
        if y + tile_height > level_height:
            tile_height = level_height - y
        
        # Calculate the downsample factor for this DeepZoom level
        dz_downsample = 2 ** (self._dz_levels - level - 1)
        
        # Find the best slide level for this downsample
        slide_level = self._osr.get_best_level_for_downsample(dz_downsample)
        slide_downsample = self._osr.level_downsamples[slide_level]
        
        # Calculate position in level 0 coordinates
        level0_x = int(x * dz_downsample)
        level0_y = int(y * dz_downsample)
        
        # Calculate the size to read from the slide
        read_width = int(tile_width * dz_downsample / slide_downsample)
        read_height = int(tile_height * dz_downsample / slide_downsample)
        
        # Read the region from the slide
        tile = self._osr.read_region((level0_x, level0_y), slide_level, (read_width, read_height))
        
        # Resize to the target tile size if necessary
        if tile.size != (tile_width, tile_height):
            tile = tile.resize((tile_width, tile_height), Image.Resampling.LANCZOS)
        
        return tile
    
    def get_dzi(self, format: str = 'jpeg') -> str:
        """Get DeepZoom Image (DZI) descriptor XML
        
        Args:
            format: Image format (default: 'jpeg')
            
        Returns:
            DZI XML string
        """
        width, height = self._osr.dimensions
        
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<Image xmlns="http://schemas.microsoft.com/deepzoom/2008"
  Format="{format}"
  Overlap="{self._overlap}"
  TileSize="{self._tile_size}">
  <Size Height="{height}" Width="{width}"/>
</Image>'''


def main():
    """Example usage"""
    from .isyntax_slide import IsyntaxSlide
    
    slide = IsyntaxSlide("path/to/file.isyntax")
    dz = IsyntaxDeepZoomGenerator(slide)
    
    print(f"DeepZoom levels: {dz.level_count}")
    print(f"Level dimensions: {dz.level_dimensions}")
    print(f"Level tiles: {dz.level_tiles}")
    
    # Get a tile
    tile = dz.get_tile(10, (0, 0))
    tile.show()
    
    slide.close()


if __name__ == '__main__':
    main()

