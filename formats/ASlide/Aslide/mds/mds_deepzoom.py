"""
DeepZoom generator for MDS slides
"""

import math
from io import BytesIO
from PIL import Image
from xml.etree.ElementTree import ElementTree, Element, SubElement


class DeepZoomGenerator(object):
    """Generates Deep Zoom tiles and metadata for MDS slides."""

    def __init__(self, osr, tile_size=254, overlap=1, limit_bounds=False):
        """Create a DeepZoomGenerator wrapping an MDS slide object.

        Args:
            osr: MDS slide object
            tile_size: the width and height of a single tile. For best viewer
                      performance, tile_size + 2 * overlap should be a power
                      of two.
            overlap: the number of extra pixels to add to each interior edge
                    of a tile.
            limit_bounds: True to render only the non-empty slide region.
        """
        self._osr = osr
        self._z_t_downsample = tile_size
        self._z_overlap = overlap
        self._limit_bounds = limit_bounds
        self._bg_color = '#ffffff'

        # Get slide dimensions
        self._l0_dimensions = osr.dimensions

        # Calculate Deep Zoom levels
        self._calculate_levels()

    def _calculate_levels(self):
        """Calculate Deep Zoom level structure."""
        # Deep Zoom level dimensions
        z_size = self._l0_dimensions
        z_dimensions = [z_size]
        
        while z_size[0] > 1 or z_size[1] > 1:
            z_size = tuple(max(1, int(math.ceil(z / 2))) for z in z_size)
            z_dimensions.append(z_size)
        
        self._z_dimensions = tuple(reversed(z_dimensions))
        
        # Tile dimensions for each level
        tiles = lambda z_lim: int(math.ceil(z_lim / self._z_t_downsample))
        self._t_dimensions = tuple((tiles(z_w), tiles(z_h))
                                   for z_w, z_h in self._z_dimensions)

        # Deep Zoom level count
        self._dz_levels = len(self._z_dimensions)

        # Total downsamples for each Deep Zoom level
        l0_z_downsamples = tuple(2 ** (self._dz_levels - dz_level - 1)
                                for dz_level in range(self._dz_levels))

        # Preferred slide levels for each Deep Zoom level
        self._slide_from_dz_level = tuple(
            self._osr.get_best_level_for_downsample(d)
            for d in l0_z_downsamples)

        # Slide level downsamples
        self._l_from_z_downsamples = tuple(
            self._osr.level_downsamples[self._slide_from_dz_level[dz_level]]
            for dz_level in range(self._dz_levels))

        # Piecewise downsamples
        self._l0_l_downsamples = tuple(
            self._osr.level_downsamples[l] for l in range(self._osr.level_count))

        self._z_from_l_downsamples = tuple(
            l0_z_downsamples[dz_level] / self._l_from_z_downsamples[dz_level]
            for dz_level in range(self._dz_levels))

    @property
    def level_count(self):
        """The number of Deep Zoom levels in the image."""
        return self._dz_levels

    @property
    def level_tiles(self):
        """A list of (tiles_x, tiles_y) tuples for each Deep Zoom level."""
        return self._t_dimensions

    @property
    def level_dimensions(self):
        """A list of (pixels_x, pixels_y) tuples for each Deep Zoom level."""
        return self._z_dimensions

    @property
    def tile_count(self):
        """The total number of Deep Zoom tiles in the image."""
        return sum(t_cols * t_rows for t_cols, t_rows in self._t_dimensions)

    def _get_tile_info(self, dz_level, t_location):
        """Return the tile information for the given Deep Zoom level and location.
        
        Returns:
            tuple: ((level0_x, level0_y), slide_level, (width, height)), (tile_width, tile_height)
        """
        # Check parameters
        if dz_level < 0 or dz_level >= self._dz_levels:
            raise ValueError("Invalid level")
        
        t_col, t_row = t_location
        if t_col < 0 or t_col >= self._t_dimensions[dz_level][0] or \
           t_row < 0 or t_row >= self._t_dimensions[dz_level][1]:
            raise ValueError("Invalid address")

        # Get preferred slide level
        slide_level = self._slide_from_dz_level[dz_level]

        # Calculate top/left and bottom/right overlap
        z_overlap_tl = self._z_overlap if (t_col > 0 or t_row > 0) else 0
        z_overlap_br = self._z_overlap if (
            t_col < self._t_dimensions[dz_level][0] - 1 or
            t_row < self._t_dimensions[dz_level][1] - 1) else 0

        # Get final size of the tile
        z_size = self._z_dimensions[dz_level]
        z_w = min(self._z_t_downsample, z_size[0] - t_col * self._z_t_downsample) + z_overlap_tl + z_overlap_br
        z_h = min(self._z_t_downsample, z_size[1] - t_row * self._z_t_downsample) + z_overlap_tl + z_overlap_br

        # Calculate level 0 coordinates
        z_downsample = 2 ** (self._dz_levels - dz_level - 1)
        
        # Tile position in level 0 coordinates
        l0_x = int((t_col * self._z_t_downsample - z_overlap_tl) * z_downsample)
        l0_y = int((t_row * self._z_t_downsample - z_overlap_tl) * z_downsample)

        # Size to read from slide
        l_downsample = self._l_from_z_downsamples[dz_level]
        l_w = int(z_w * z_downsample / l_downsample)
        l_h = int(z_h * z_downsample / l_downsample)

        return ((l0_x, l0_y), slide_level, (l_w, l_h)), (z_w, z_h)

    def get_tile(self, level, address):
        """Return an RGB PIL.Image for a tile.

        Args:
            level: the Deep Zoom level
            address: the address of the tile within the level as a (col, row) tuple

        Returns:
            PIL.Image: RGB image of the tile
        """
        # Read tile
        args, z_size = self._get_tile_info(level, address)
        tile = self._osr.read_region(*args)

        # Apply on solid background
        bg = Image.new('RGB', tile.size, self._bg_color)
        
        # Handle different image modes
        if tile.mode == 'RGBA':
            tile = Image.composite(tile, bg, tile)
        elif tile.mode == 'RGB':
            # Already RGB, no compositing needed
            pass
        else:
            # Convert to RGB
            tile = tile.convert('RGB')

        # Scale to the correct size
        if tile.size != z_size:
            # Use LANCZOS for compatibility with newer Pillow versions
            try:
                # Try new Pillow API first
                tile.thumbnail(z_size, Image.Resampling.LANCZOS)
            except AttributeError:
                # Fallback for older Pillow versions
                tile.thumbnail(z_size, Image.Resampling.LANCZOS)

        return tile

    def get_dzi(self, format='jpeg'):
        """Return a string containing the XML metadata for the .dzi file.

        Args:
            format: the format of the individual tiles ('png' or 'jpeg')
            
        Returns:
            str: DZI XML string
        """
        image = Element('Image', TileSize=str(self._z_t_downsample),
                       Overlap=str(self._z_overlap), Format=format,
                       xmlns='http://schemas.microsoft.com/deepzoom/2008')
        w, h = self._l0_dimensions
        SubElement(image, 'Size', Width=str(w), Height=str(h))
        tree = ElementTree(element=image)
        buf = BytesIO()
        tree.write(buf, encoding='UTF-8')
        return buf.getvalue().decode('UTF-8')


def main():
    """Example usage"""
    from .mds_slide import MdsSlide
    
    mds_file_path = "/jhcnas6/Private/MOTIC/WSI/WCDZZQP/1907469/1.mds"
    slide = MdsSlide(mds_file_path)

    dzg = DeepZoomGenerator(slide)
    print("level_count : ", dzg.level_count)
    print("level_tiles : ", dzg.level_tiles)
    print("level_dimensions : ", dzg.level_dimensions)
    print("tile count : ", dzg.tile_count)
    print("dzi : \n")
    print(dzg.get_dzi('jpeg'))
    
    # Get a tile
    tile = dzg.get_tile(13, (0, 0))
    tile.save('mds_deepzoom_tile.jpg')
    print("Tile saved to mds_deepzoom_tile.jpg")
    
    slide.close()


if __name__ == '__main__':
    main()

