"""
MDS slide implementation
Supports both OLE2 format (.mds) and BKIO format (.mdsx)
"""

import os
import sys
from PIL import Image
import xml.etree.ElementTree as ET
from io import BytesIO
from collections import defaultdict
from typing import Any

try:
    import olefile
except ImportError:
    raise ImportError(
        "olefile is required for MDS support. Install with: pip install olefile"
    )

from .color_correction import ColorCorrection


def detect_mds_format(filename):
    """
    Detect MDS file format (OLE2 or BKIO)

    Returns:
        'ole2' for OLE2 format (.mds files)
        'bkio' for BKIO format (.mdsx files)
        None if not a valid MDS file
    """
    try:
        with open(filename, "rb") as f:
            magic = f.read(4)
            if magic == b"BKIO":
                return "bkio"
            elif magic == b"\xd0\xcf\x11\xe0":  # OLE2 magic
                return "ole2"
    except:
        pass
    return None


class MdsSlide:
    """
    MDS slide reader - automatically detects and handles both formats:
    - OLE2 format (.mds): uses olefile
    - BKIO format (.mdsx): uses custom parser
    """

    def __new__(cls, filename, silent=True):
        """Factory method to create appropriate slide reader"""
        format_type = detect_mds_format(filename)

        if format_type == "ole2":
            return MdsSlideOLE2(filename, silent)
        elif format_type == "bkio":
            # Import here to avoid circular dependency
            from .mdsx_slide import MdsxSlide

            return MdsxSlide(filename, silent)
        else:
            raise ValueError(f"Unsupported MDS format: {filename}")

    @classmethod
    def detect_format(cls, filename):
        """Detect if file is MDS/MDSX format"""
        ext = os.path.splitext(filename)[1].lower()
        return "mds" if ext in [".mds", ".mdsx"] else None


class MdsSlideOLE2:
    """MDS slide reader for OLE2 format using olefile"""

    def __init__(self, filename, silent=True):
        """Initialize MDS slide

        Args:
            filename: Path to MDS file
            silent: If True, suppress debug output (default: True)
        """
        self.__filename = filename
        self._silent = silent
        self.ole: Any | None = None
        self._dimensions: tuple[int, int] | None = None
        self._level_dimensions: list[tuple[int, int]] | None = None
        self._level_downsamples: tuple[float, ...] | None = None

        # Open OLE file
        self.ole = olefile.OleFileIO(filename)

        # Color correction
        self._color_correction = ColorCorrection(style="Real")

        # Parse structure
        self._parse_structure()

        # Get properties from XML
        self._get_properties()

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, self.__filename)

    def _require_ole(self) -> Any:
        if self.ole is None:
            raise RuntimeError("MDS OLE file is not open")
        return self.ole

    def _parse_structure(self):
        """Parse MDS OLE file structure"""
        # Analyze levels and tiles
        self._levels_data = defaultdict(list)
        ole = self._require_ole()

        for stream in ole.listdir():
            if len(stream) >= 3 and stream[0] == "DSI0":
                level_name = stream[1]
                tile_name = stream[2]
                self._levels_data[level_name].append(tile_name)

        # Sort levels by scale (descending - highest resolution first)
        self._level_names = sorted(
            self._levels_data.keys(), key=lambda x: float(x), reverse=True
        )

        # Calculate tile grid for each level
        self._level_grids = {}
        for level_name in self._level_names:
            tiles = self._levels_data[level_name]
            rows = set()
            cols = set()
            for tile in tiles:
                parts = tile.split("_")
                if len(parts) == 2:
                    try:
                        row = int(parts[0])
                        col = int(parts[1])
                        rows.add(row)
                        cols.add(col)
                    except:
                        pass

            if rows and cols:
                self._level_grids[level_name] = {
                    "rows": max(rows) + 1,
                    "cols": max(cols) + 1,
                }

        # Determine tile size by reading first tile
        if self._level_names:
            first_level = self._level_names[0]
            first_tile = self._levels_data[first_level][0]
            tile_data = self._read_tile_data(first_level, first_tile)
            if tile_data:
                img = Image.open(BytesIO(tile_data))
                self._tile_width, self._tile_height = img.size
            else:
                # Default tile size
                self._tile_width = 512
                self._tile_height = 512
        else:
            self._tile_width = 512
            self._tile_height = 512

    def _read_tile_data(self, level_name, tile_name):
        """Read raw tile data from OLE stream"""
        try:
            stream_path = ["DSI0", level_name, tile_name]
            data = self._require_ole().openstream(stream_path).read()
            return data
        except:
            return None

    def _parse_info_xml(self):
        """Parse info.xml file for slide properties"""
        info_xml_path = os.path.join(os.path.dirname(self.__filename), "info.xml")
        if os.path.exists(info_xml_path):
            try:
                # Try to read and fix encoding issues
                with open(info_xml_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    # Replace problematic encoding declaration
                    content = content.replace('encoding="unicode"', 'encoding="utf-8"')

                # Parse the corrected content
                root = ET.fromstring(content)

                properties = {}
                for item in root.findall("item"):
                    for key, value in item.attrib.items():
                        if key == "rows":
                            properties["rows"] = int(value)
                        elif key == "cols":
                            properties["cols"] = int(value)
                        elif key == "objective":
                            properties["objective"] = float(value)
                        elif key == "create_time":
                            properties["create_time"] = value
                        elif key == "scan_machine":
                            properties["scan_machine"] = value

                return properties
            except Exception as e:
                # Silently ignore XML parsing errors to reduce noise
                return {}
        return {}

    def _get_properties(self):
        """Get slide properties from XML"""
        # Parse XML properties
        xml_props = self._parse_info_xml()

        # Calculate MPP from objective
        objective = xml_props.get("objective", 40.0)
        # Typical conversion: 40x objective ≈ 0.25 μm/pixel
        self.sampling_rate = 10.0 / objective if objective > 0 else 0.25

        # Store XML properties
        self._xml_properties = xml_props

    @property
    def level_count(self):
        """Get number of levels"""
        return len(self._level_names)

    @property
    def dimensions(self):
        """Return the dimensions of the highest resolution level (level 0)."""
        if self._dimensions is None:
            # Level 0 is the highest resolution (scale = 1.0)
            level_name = self._level_names[0]
            grid = self._level_grids.get(level_name, {"rows": 1, "cols": 1})
            width = grid["cols"] * self._tile_width
            height = grid["rows"] * self._tile_height
            self._dimensions = (width, height)
        return self._dimensions

    @property
    def level_dimensions(self):
        """Get dimensions for all levels"""
        if self._level_dimensions is None:
            self._level_dimensions = []
            for level_name in self._level_names:
                grid = self._level_grids.get(level_name, {"rows": 1, "cols": 1})
                width = grid["cols"] * self._tile_width
                height = grid["rows"] * self._tile_height
                self._level_dimensions.append((width, height))
        return self._level_dimensions

    @property
    def level_downsamples(self):
        """Get downsample factors for all levels"""
        if self._level_downsamples is None:
            # Calculate downsamples based on level scales
            base_scale = float(self._level_names[0])  # Should be 1.0
            self._level_downsamples = tuple(
                base_scale / float(level_name) for level_name in self._level_names
            )
        return self._level_downsamples

    @property
    def magnification(self):
        """Get the magnification of the slide."""
        objective = self._xml_properties.get("objective")
        if objective:
            return float(objective)

        # Fallback to calculating from sampling rate (mpp)
        if self.sampling_rate > 0:
            return 10.0 / self.sampling_rate
        return None

    @property
    def properties(self):
        """Get slide properties"""
        props = {
            "openslide.mpp-x": str(self.sampling_rate),
            "openslide.mpp-y": str(self.sampling_rate),
            "openslide.vendor": "MDS",
        }

        # Add XML properties if available
        xml_props = getattr(self, "_xml_properties", {})
        if "objective" in xml_props:
            props["openslide.objective-power"] = str(xml_props["objective"])
        if "create_time" in xml_props:
            props["mds.create_time"] = xml_props["create_time"]
        if "scan_machine" in xml_props:
            props["mds.scan_machine"] = xml_props["scan_machine"]

        return props

    @property
    def associated_images(self):
        """Get associated images from external files"""
        images = {}

        base_dir = os.path.dirname(self.__filename)

        # Try to load label.jpg
        label_path = os.path.join(base_dir, "label.jpg")
        if os.path.exists(label_path):
            try:
                images["label"] = Image.open(label_path)
            except:
                pass

        # Try to load macro.jpg
        macro_path = os.path.join(base_dir, "macro.jpg")
        if os.path.exists(macro_path):
            try:
                images["macro"] = Image.open(macro_path)
            except:
                pass

        return images

    def get_best_level_for_downsample(self, downsample):
        """Find the best level for a given downsample factor.

        This mirrors OpenSlide's behavior:
        - Return the largest level whose downsample is <= target
        - This ensures we don't over-downsample (lose resolution)
        """
        downsamples = self.level_downsamples

        # If target is smaller than level 0, return level 0
        if downsample < downsamples[0]:
            return 0

        # Find the largest level with downsample <= target
        for i in range(1, len(downsamples)):
            if downsamples[i] > downsample:
                return i - 1

        # Target is >= all levels, return the last level
        return self.level_count - 1

    def get_thumbnail(self, size):
        """Get thumbnail image"""
        try:
            # For single-level images, read a small region and resize
            if self.level_count == 1:
                # Calculate a reasonable sample size
                base_width, base_height = self.dimensions
                sample_size = min(1024, base_width // 4, base_height // 4)
                sample_size = max(256, sample_size)  # Minimum sample size

                # Read from center of image
                x = max(0, (base_width - sample_size) // 2)
                y = max(0, (base_height - sample_size) // 2)

                thumbnail = self.read_region((x, y), 0, (sample_size, sample_size))
                thumbnail = thumbnail.resize(size, Image.Resampling.LANCZOS)
                return thumbnail
            else:
                # For multi-level images, use the highest level
                highest_level = self.level_count - 1
                level_dims = self.level_dimensions[highest_level]

                # Read a reasonable portion of the highest level
                read_width = min(level_dims[0], 512)
                read_height = min(level_dims[1], 512)

                thumbnail = self.read_region(
                    (0, 0), highest_level, (read_width, read_height)
                )
                thumbnail = thumbnail.resize(size, Image.Resampling.LANCZOS)
                return thumbnail

        except Exception as e:
            # Fallback to solid color
            return Image.new("RGB", size, (200, 200, 200))

    def read_region(self, location, level, size):
        """Read a region from the slide

        Args:
            location: (x, y) tuple of top-left corner in level 0 coordinates
            level: pyramid level
            size: (width, height) of region to read

        Returns:
            PIL Image
        """
        x, y = location
        width, height = size

        # Get level info
        if level >= len(self._level_names):
            raise ValueError(f"Invalid level: {level}")

        level_name = self._level_names[level]
        downsample = self.level_downsamples[level]

        # Convert level 0 coordinates to current level coordinates
        level_x = int(x / downsample)
        level_y = int(y / downsample)

        # Calculate which tiles we need
        start_tile_col = level_x // self._tile_width
        start_tile_row = level_y // self._tile_height
        end_tile_col = (level_x + width - 1) // self._tile_width
        end_tile_row = (level_y + height - 1) // self._tile_height

        # Create output image
        result = Image.new("RGB", (width, height), (240, 240, 240))

        # Read and composite tiles
        for tile_row in range(start_tile_row, end_tile_row + 1):
            for tile_col in range(start_tile_col, end_tile_col + 1):
                tile_name = f"{tile_row:04d}_{tile_col:04d}"

                # Check if tile exists
                if tile_name not in self._levels_data[level_name]:
                    continue

                # Read tile
                tile_data = self._read_tile_data(level_name, tile_name)
                if not tile_data:
                    continue

                try:
                    tile_img = Image.open(BytesIO(tile_data))

                    # Calculate paste position
                    tile_x = tile_col * self._tile_width - level_x
                    tile_y = tile_row * self._tile_height - level_y

                    # Crop tile if needed
                    crop_left = max(0, -tile_x)
                    crop_top = max(0, -tile_y)
                    crop_right = min(tile_img.width, width - tile_x)
                    crop_bottom = min(tile_img.height, height - tile_y)

                    if crop_right > crop_left and crop_bottom > crop_top:
                        cropped = tile_img.crop(
                            (crop_left, crop_top, crop_right, crop_bottom)
                        )
                        paste_x = max(0, tile_x)
                        paste_y = max(0, tile_y)
                        result.paste(cropped, (paste_x, paste_y))
                except Exception as e:
                    if not self._silent:
                        print(f"Warning: Failed to read tile {tile_name}: {e}")
                    continue

        # Apply color correction if enabled
        result = self._color_correction.apply(result)

        return result

    def apply_color_correction(self, apply: bool = True, style: str = "Real"):
        """Apply or disable color correction.

        Args:
            apply: Whether to apply color correction
            style: Color correction style ("Real")
        """
        self._color_correction.enabled = apply
        if style:
            self._color_correction.set_style(style)

    def get_color_correction_info(self) -> dict[str, Any]:
        """Get current color correction parameters."""
        return self._color_correction.get_info()

    def close(self):
        """Close the slide"""
        if hasattr(self, "ole") and self.ole:
            try:
                self.ole.close()
            except:
                pass
            self.ole = None

    def __del__(self):
        """Destructor"""
        self.close()
