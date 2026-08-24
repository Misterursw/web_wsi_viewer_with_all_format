#!/usr/bin/env python3
"""
MDSX (BKIO) format support for ASlide
Based on OpenSlide PR #624 by peterchen183
"""

import struct
import base64
import xml.etree.ElementTree as ET
from io import BytesIO
from typing import Any, BinaryIO
from PIL import Image
import re

from .color_correction import ColorCorrection


class MdsxSlide:
    """
    MDSX (BKIO) format slide reader
    """

    def __init__(self, filename, silent=True):
        self.filename = filename
        self._silent = silent
        self._file_handle: BinaryIO | None = None
        self._properties: dict[str, str] = {}
        self._level_data: list[dict[str, Any]] = []
        self._associated_images: dict[str, Image.Image] = {}
        self._metadata_offsets: dict[str, tuple[int, int]] = {}
        self._associated_images_info_offset: int | None = None

        # Color correction
        self._color_correction = ColorCorrection(style="Real")

        # Open and parse the file
        self._open_file()
        self._parse_header()
        self._parse_metadata()
        self._parse_tiles_info()

    def _open_file(self):
        """Open the MDSX file and verify magic header"""
        self._file_handle = open(self.filename, "rb")

        # Check BKIO magic header
        magic = self._file_handle.read(4)
        if magic != b"BKIO":
            raise ValueError(
                f"Not a valid MDSX file: magic header is {magic}, expected b'BKIO'"
            )

    def _require_file_handle(self) -> BinaryIO:
        if self._file_handle is None:
            raise RuntimeError("MDSX file is not open")
        return self._file_handle

    def _require_int32(self, value: int | None, field_name: str) -> int:
        if value is None:
            raise ValueError(f"Missing {field_name} in MDSX metadata")
        return value

    def _read_int32_le(self):
        """Read a little-endian 32-bit integer"""
        data = self._require_file_handle().read(4)
        if len(data) != 4:
            return None
        return struct.unpack("<I", data)[0]

    def _read_string(self, length):
        """Read a string of specified length"""
        return self._require_file_handle().read(length)

    def _remove_inside_zeros(self, data):
        """Remove null bytes from UTF-16LE encoded data"""
        # UTF-16LE has null bytes between ASCII characters
        result = bytearray()
        for i in range(0, len(data), 2):
            if i + 1 < len(data) and data[i] != 0:
                result.append(data[i])
        return bytes(result)

    def _get_length_without_trailing_zeros(self, data):
        """Get length without trailing zeros"""
        length = len(data)
        while length > 1:
            if data[length - 2] == 0 and data[length - 1] == 0:
                length -= 2
            else:
                break
        return length

    def _remove_scan_path(self, xml_str):
        """Remove ScanPath element from XML"""
        # Find and remove <ScanPath>...</ScanPath>
        pattern = r"<ScanPath[^>]*>.*?</ScanPath>"
        return re.sub(pattern, "", xml_str, flags=re.DOTALL)

    def _process_xml(self, data, is_base64=True, remove_scan_path=False):
        """Process XML data (possibly base64 encoded and UTF-16LE)"""
        # Decode base64 if needed
        if is_base64:
            data = base64.b64decode(data)

        # Decode UTF-16LE to string
        # The data is in UTF-16LE format, decode it directly
        xml_str = data.decode("utf-16le", errors="ignore")

        # Remove trailing null characters
        xml_str = xml_str.rstrip("\x00")

        # Remove ScanPath element if needed
        if remove_scan_path:
            xml_str = self._remove_scan_path(xml_str)

        # Replace XML header
        if xml_str.startswith("<?xml"):
            # Find end of XML declaration
            end_idx = xml_str.find("?>") + 2
            xml_str = '<?xml version="1.0" ?>' + xml_str[end_idx:]

        return xml_str

    def _parse_xml_properties(self, xml_str, prefix="motic"):
        """Parse XML and extract properties"""
        try:
            root = ET.fromstring(xml_str)

            # Parse all elements recursively
            def parse_element(element, parent_path=""):
                for child in element:
                    value = child.get("value")
                    if value:
                        if parent_path:
                            key = f"{prefix}.{parent_path}.{child.tag}"
                        else:
                            key = f"{prefix}.{child.tag}"
                        self._properties[key] = value

                    # Recursively parse children
                    if parent_path:
                        new_path = f"{parent_path}.{child.tag}"
                    else:
                        new_path = child.tag
                    parse_element(child, new_path)

            parse_element(root)

        except Exception as e:
            if not self._silent:
                print(f"Warning: Failed to parse XML: {e}")

    def _parse_header(self):
        """Parse MDSX file header"""
        # According to C code: skip 80 bytes after magic header
        # Then read 5 data blocks, each with structure:
        # - 4 bytes marker (64, 65, 66, 67, 68)
        # - 4 bytes unknown
        # - 4 bytes offset
        # - 4 bytes marker
        file_handle = self._require_file_handle()
        file_handle.seek(84)  # Skip to first data block (4 bytes magic + 80 bytes)

        # Read 5 data blocks info (each 16 bytes: 4+4+4+4)
        associated_images_info_offset = None
        for i in range(5):
            marker1 = self._read_int32_le()  # Should be 0x64, 0x65, 0x66, 0x67, 0x68
            unknown = self._read_int32_le()
            offset = self._read_int32_le()
            marker2 = self._read_int32_le()

            if i == 0:
                associated_images_info_offset = offset

        # Parse associated images info block
        associated_images_info_offset = self._require_int32(
            associated_images_info_offset, "associated images info offset"
        )
        file_handle.seek(associated_images_info_offset)
        file_handle.seek(6, 1)  # Skip
        file_handle.seek(14, 1)  # Skip slide xml

        property_xml_offset = self._require_int32(
            self._read_int32_le(), "property xml offset"
        )
        property_xml_length = self._require_int32(
            self._read_int32_le(), "property xml length"
        )

        file_handle.seek(6, 1)  # Skip
        preview_offset = self._require_int32(self._read_int32_le(), "preview offset")
        preview_length = self._require_int32(self._read_int32_le(), "preview length")

        file_handle.seek(6, 1)  # Skip
        label_offset = self._require_int32(self._read_int32_le(), "label offset")
        label_length = self._require_int32(self._read_int32_le(), "label length")

        file_handle.seek(6, 1)  # Skip
        slide_image_xml_offset = self._require_int32(
            self._read_int32_le(), "slide image xml offset"
        )
        slide_image_xml_length = self._require_int32(
            self._read_int32_le(), "slide image xml length"
        )

        # Store for later use
        self._metadata_offsets = {
            "property_xml": (property_xml_offset, property_xml_length),
            "slide_image_xml": (slide_image_xml_offset, slide_image_xml_length),
            "preview": (preview_offset, preview_length),
            "label": (label_offset, label_length),
        }

        self._associated_images_info_offset = associated_images_info_offset

    def _parse_metadata(self):
        """Parse XML metadata"""
        file_handle = self._require_file_handle()

        # Check if XML is base64 encoded
        slide_xml_offset, slide_xml_length = self._metadata_offsets["slide_image_xml"]
        file_handle.seek(slide_xml_offset)
        first_char = file_handle.read(1)
        is_base64 = first_char != b"<"

        # Parse slide image XML
        file_handle.seek(slide_xml_offset)
        slide_xml_data = self._read_string(slide_xml_length)
        slide_xml_str = self._process_xml(
            slide_xml_data, is_base64=is_base64, remove_scan_path=False
        )
        self._parse_xml_properties(slide_xml_str, prefix="motic")

        # Parse property XML
        prop_xml_offset, prop_xml_length = self._metadata_offsets["property_xml"]
        file_handle.seek(prop_xml_offset)
        prop_xml_data = self._read_string(prop_xml_length)
        prop_xml_str = self._process_xml(
            prop_xml_data, is_base64=is_base64, remove_scan_path=True
        )

        self._parse_xml_properties(prop_xml_str, prefix="motic")

        # Add vendor
        self._properties["openslide.vendor"] = "Motic"

        # Load associated images
        self._load_associated_images()

    def _load_associated_images(self):
        """Load label and preview images"""
        file_handle = self._require_file_handle()

        # Load label
        label_offset, label_length = self._metadata_offsets["label"]
        if label_offset > 0 and label_length > 0:
            file_handle.seek(label_offset)
            label_data = self._read_string(label_length)
            try:
                self._associated_images["label"] = Image.open(BytesIO(label_data))
            except Exception as e:
                if not self._silent:
                    print(f"Warning: Failed to load label image: {e}")

        # Load preview (macro)
        preview_offset, preview_length = self._metadata_offsets["preview"]
        if preview_offset > 0 and preview_length > 0:
            file_handle.seek(preview_offset)
            preview_data = self._read_string(preview_length)
            try:
                self._associated_images["macro"] = Image.open(BytesIO(preview_data))
            except Exception as e:
                if not self._silent:
                    print(f"Warning: Failed to load preview image: {e}")

    def _parse_tiles_info(self):
        """Parse tiles information for all levels"""
        file_handle = self._require_file_handle()

        # Get basic properties (try both with and without ImageMatrix prefix)
        width = int(
            self._properties.get(
                "motic.ImageMatrix.Width", self._properties.get("motic.Width", 0)
            )
        )
        height = int(
            self._properties.get(
                "motic.ImageMatrix.Height", self._properties.get("motic.Height", 0)
            )
        )
        layer_count = int(
            self._properties.get(
                "motic.ImageMatrix.LayerCount",
                self._properties.get("motic.LayerCount", 0),
            )
        )
        tile_size = int(
            self._properties.get(
                "motic.ImageMatrix.CellWidth",
                self._properties.get("motic.CellWidth", 256),
            )
        )

        if width == 0 or height == 0 or layer_count == 0:
            raise ValueError(
                f"Invalid slide dimensions or layer count: width={width}, height={height}, layer_count={layer_count}"
            )

        # Parse tiles info for each level
        tiles_info_offset = 164

        for level in range(layer_count):
            # Read level info
            file_handle.seek(tiles_info_offset + level * 16)
            file_handle.seek(4, 1)  # Skip marker
            file_handle.seek(4, 1)  # Skip unknown
            level_tiles_offset = self._require_int32(
                self._read_int32_le(), f"level {level} tiles offset"
            )
            level_tiles_length = self._require_int32(
                self._read_int32_le(), f"level {level} tiles length"
            )
            if level_tiles_length < 4:
                raise ValueError(
                    f"Invalid tile data length at level {level}: {level_tiles_length}"
                )

            tile_count = (level_tiles_length - 4) // 10

            # Get tile rows and cols from properties (try both with and without ImageMatrix prefix)
            rows = int(
                self._properties.get(
                    f"motic.ImageMatrix.Layer{level}.Rows",
                    self._properties.get(f"motic.Layer{level}.Rows", 0),
                )
            )
            cols = int(
                self._properties.get(
                    f"motic.ImageMatrix.Layer{level}.Cols",
                    self._properties.get(f"motic.Layer{level}.Cols", 0),
                )
            )

            if rows * cols != tile_count:
                if not self._silent:
                    print(
                        f"Warning: Tile count mismatch at level {level}: {rows}x{cols} != {tile_count}"
                    )

            # Read tile offsets and lengths
            file_handle.seek(level_tiles_offset + 4)
            tiles = []
            for i in range(tile_count):
                file_handle.seek(2, 1)  # Skip 2 bytes
                offset = self._require_int32(
                    self._read_int32_le(), f"level {level} tile {i} offset"
                )
                length = self._require_int32(
                    self._read_int32_le(), f"level {level} tile {i} length"
                )
                tiles.append((offset, length))

            # Store level data
            downsample = 2**level
            self._level_data.append(
                {
                    "width": width // downsample,
                    "height": height // downsample,
                    "downsample": downsample,
                    "tile_size": tile_size,
                    "tiles_across": cols,
                    "tiles_down": rows,
                    "tiles": tiles,
                }
            )

    @property
    def level_count(self):
        """Number of pyramid levels"""
        return len(self._level_data)

    @property
    def dimensions(self):
        """Dimensions of level 0 (width, height)"""
        if self._level_data:
            return (self._level_data[0]["width"], self._level_data[0]["height"])
        return (0, 0)

    @property
    def level_dimensions(self):
        """Dimensions of all levels"""
        return [(level["width"], level["height"]) for level in self._level_data]

    @property
    def level_downsamples(self):
        """Downsample factors for all levels"""
        return [level["downsample"] for level in self._level_data]

    @property
    def properties(self):
        """Slide properties"""
        return self._properties.copy()

    @property
    def associated_images(self):
        """Associated images (label, macro)"""
        return self._associated_images.copy()

    @property
    def magnification(self):
        """Get the objective power/magnification."""
        # Check standard properties
        for key in ["openslide.objective-power", "motic.Objective", "Objective"]:
            val = self._properties.get(key)
            if val:
                try:
                    return float(val)
                except:
                    pass

        # Fallback to MPP calculation
        mpp = self.mpp
        if mpp and mpp > 0:
            return 10.0 / mpp
        return None

    @property
    def mpp(self):
        """Microns per pixel"""
        scale = self._properties.get("motic.Scale")
        if scale:
            try:
                return float(scale)
            except:
                pass
        return None

    def _read_tile(self, level, tile_row, tile_col):
        """Read a single tile as PIL Image"""
        if level >= len(self._level_data):
            raise ValueError(f"Invalid level: {level}")

        level_info = self._level_data[level]
        tile_idx = tile_row * level_info["tiles_across"] + tile_col

        if tile_idx >= len(level_info["tiles"]):
            # Return blank tile
            tile_size = level_info["tile_size"]
            return Image.new("RGB", (tile_size, tile_size), (255, 255, 255))

        offset, length = level_info["tiles"][tile_idx]

        if length == 0:
            # Return blank tile
            tile_size = level_info["tile_size"]
            return Image.new("RGB", (tile_size, tile_size), (255, 255, 255))

        # Read JPEG data
        self._require_file_handle().seek(offset)
        jpeg_data = self._read_string(length)

        try:
            return Image.open(BytesIO(jpeg_data))
        except Exception as e:
            if not self._silent:
                print(
                    f"Warning: Failed to decode tile at level {level}, row {tile_row}, col {tile_col}: {e}"
                )
            tile_size = level_info["tile_size"]
            return Image.new("RGB", (tile_size, tile_size), (255, 255, 255))

    def read_region(self, location, level, size):
        """
        Read a region from the slide

        Args:
            location: (x, y) tuple in level 0 coordinates
            level: pyramid level
            size: (width, height) of the region to read

        Returns:
            PIL Image
        """
        if level >= len(self._level_data):
            raise ValueError(f"Invalid level: {level}")

        x, y = location
        width, height = size

        level_info = self._level_data[level]
        downsample = level_info["downsample"]
        tile_size = level_info["tile_size"]

        # Convert to level coordinates
        level_x = x // downsample
        level_y = y // downsample

        # Calculate tile range
        start_tile_col = level_x // tile_size
        start_tile_row = level_y // tile_size
        end_tile_col = (level_x + width - 1) // tile_size
        end_tile_row = (level_y + height - 1) // tile_size

        # Create output image
        output = Image.new("RGB", (width, height), (255, 255, 255))

        # Read and composite tiles
        for tile_row in range(start_tile_row, end_tile_row + 1):
            for tile_col in range(start_tile_col, end_tile_col + 1):
                # Read tile
                tile = self._read_tile(level, tile_row, tile_col)

                # Calculate paste position
                tile_x = tile_col * tile_size
                tile_y = tile_row * tile_size

                # Calculate crop and paste regions
                src_x = max(0, level_x - tile_x)
                src_y = max(0, level_y - tile_y)
                dst_x = max(0, tile_x - level_x)
                dst_y = max(0, tile_y - level_y)

                crop_width = min(tile_size - src_x, width - dst_x)
                crop_height = min(tile_size - src_y, height - dst_y)

                if crop_width > 0 and crop_height > 0:
                    cropped = tile.crop(
                        (src_x, src_y, src_x + crop_width, src_y + crop_height)
                    )
                    output.paste(cropped, (dst_x, dst_y))

        # Apply color correction if enabled
        output = self._color_correction.apply(output)

        return output

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

    def get_thumbnail(self, size):
        """
        Get a thumbnail of the slide

        Args:
            size: (width, height) tuple for maximum dimensions

        Returns:
            PIL Image
        """
        # Find the best level for thumbnail
        target_width, target_height = size
        best_level = 0

        for i, (w, h) in enumerate(self.level_dimensions):
            if w <= target_width * 2 and h <= target_height * 2:
                best_level = i
                break

        # Read the entire level
        level_width, level_height = self.level_dimensions[best_level]
        thumbnail = self.read_region((0, 0), best_level, (level_width, level_height))

        # Resize to fit within size
        thumbnail.thumbnail(size, Image.Resampling.LANCZOS)

        return thumbnail

    def get_best_level_for_downsample(self, downsample):
        """Get the best level for a given downsample factor.

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

    def close(self):
        """Close the file"""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None

    def __del__(self):
        self.close()
