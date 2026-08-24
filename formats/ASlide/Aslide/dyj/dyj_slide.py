"""
DYJ format reader for ASlide.

DYJ Format Structure:
- Magic: "DPTWSI" + 2-byte version suffix (8 bytes total)
  - Version 0x2370 ("p#"): older format, records at offset from 0xb0
  - Version 0x2490 ("\x90$"): newer format, records at fixed 0x150
- Header: 0x00 - 0xFF (256 bytes)
- ImageInfo records (22 bytes each)
- Contains embedded thumbnail (JPEG), label (PNG), macro (BMP)
- Tile-based JPEG storage with z-stack support (16 z-layers)
- Three layers: layer 0 (1280x1280), layer 1 (320x320), layer 2 (80x80)
- All layers share unified coordinate system (X, Y are pixel positions)
- Layer downsample: layer 0 = 1x, layer 1 = 4x, layer 2 = 16x

ImageInfo Record Structure (22 bytes):
- offset+0:  1 byte  - layer (uint8) - pyramid level (0, 1, 2)
- offset+1:  4 bytes - X position (uint32) - pixel coordinate in unified system
- offset+5:  4 bytes - Y position (uint32) - pixel coordinate in unified system
- offset+9:  1 byte  - Z (uint8) - z-stack layer (0-15)
- offset+10: 4 bytes - Length (int32) - JPEG data size
- offset+14: 8 bytes - Offset (int64) - JPEG file offset
"""

import struct
import io
from typing import Any, BinaryIO, TypedDict
from PIL import Image

from .color_correction import ColorCorrection


class DyjTileInfo(TypedDict):
    length: int
    offset: int


class DyjSlide:
    """
    DYJ slide reader for WSI files.

    Supports:
    - Reading header information (dimensions, tile size)
    - Extracting thumbnail, label, and macro images
    - read_region for reading arbitrary regions
    - Basic properties
    """

    MAGIC_PREFIX: bytes = b"DPTWSI"  # Common prefix for all DYJ files
    MAGIC_V1: bytes = b"DPTWSIp#"  # Version 0x2370 - older format
    MAGIC_V2: bytes = b"DPTWSI\x90$"  # Version 0x2490 - newer format

    # Fixed record start offset for V2 format
    FIXED_RECORD_OFFSET: int = 0x150

    RECORD_SIZE: int = 22  # Size of each ImageInfo record
    Z_LAYERS: int = 16  # Number of z-stack layers (0-15)
    DEFAULT_Z: int = 0  # Default z-layer to use

    # Tile sizes for each layer (in the tile's own resolution)
    TILE_SIZES: dict[int, int] = {0: 1280, 1: 320, 2: 80}

    # Downsample factors for each layer
    LAYER_DOWNSAMPLES: dict[int, int] = {0: 1, 1: 4, 2: 16}

    def __init__(self, filename: str, z_layer: int | None = None):
        """Initialize DYJ slide reader.

        Args:
            filename: Path to the DYJ file
            z_layer: Z-stack layer to use (0-15). If None, uses DEFAULT_Z (0).
        """
        self._filename: str = filename
        self._closed: bool = False
        self._file: BinaryIO | None = open(filename, "rb")
        self._z_layer: int = z_layer if z_layer is not None else self.DEFAULT_Z

        # Tile index: {(layer, x, y, z): {'length': int, 'offset': int}}
        self._tile_index: dict[tuple[int, int, int, int], DyjTileInfo] = {}

        # Unified coordinate system coverage
        self._unified_width: int = 0
        self._unified_height: int = 0

        self._format_version: int = 0
        self._magic_suffix: int = 0
        self._version: int = 0
        self._config1: int = 0
        self._tile_size: int = self.TILE_SIZES[0]
        self._width: int = 0
        self._height: int = 0
        self._thumbnail_offset: int = 0
        self._thumbnail_size: int = 0
        self._label_offset: int = 0
        self._label_size: int = 0
        self._macro_offset: int = 0
        self._macro_size: int = 0
        self._mpp: float = 0.25
        self._image_info_offset_from_header: int = 0
        self._image_info_offset: int = self.FIXED_RECORD_OFFSET
        self._tiles_x: int = 0
        self._tiles_y: int = 0
        self._properties: dict[str, str] = {}

        # Color correction
        self._color_correction: ColorCorrection = ColorCorrection(style="Real")

        # Parse header
        self._parse_header()

        # Build tile index
        self._build_tile_index()

        # Cache properties
        self._init_properties()

    def _require_file(self) -> BinaryIO:
        file = self._file
        if self._closed or file is None:
            raise RuntimeError("Slide has been closed")
        return file

    def _parse_header(self) -> None:
        """Parse the DYJ file header."""
        file = self._require_file()
        file.seek(0)
        magic = file.read(8)

        # Check magic prefix
        if not magic.startswith(self.MAGIC_PREFIX):
            raise ValueError(
                f"Invalid DYJ file: expected magic prefix {self.MAGIC_PREFIX}, got {magic[:6]}"
            )

        # Determine format version based on magic suffix
        magic_suffix = struct.unpack("<H", magic[6:8])[0]
        if magic == self.MAGIC_V1:
            self._format_version = 1
        elif magic == self.MAGIC_V2:
            self._format_version = 2
        else:
            # Unknown version, try to auto-detect record start
            self._format_version = 0

        self._magic_suffix = magic_suffix

        # Version (0x08)
        file.seek(0x08)
        self._version = struct.unpack("<I", file.read(4))[0]

        # Config and tile size (0x0c - 0x0f)
        file.seek(0x0C)
        self._config1 = struct.unpack("<H", file.read(2))[0]  # 4096
        self._tile_size = struct.unpack("<H", file.read(2))[0]  # 1280

        # Image dimensions (0x1a - 0x1d)
        file.seek(0x1A)
        self._width = struct.unpack("<H", file.read(2))[0]
        self._height = struct.unpack("<H", file.read(2))[0]

        # Thumbnail (JPEG) offset and size
        file.seek(0x20)
        self._thumbnail_offset = struct.unpack("<I", file.read(4))[0]
        file.seek(0x28)
        self._thumbnail_size = struct.unpack("<I", file.read(4))[0]

        # Label (PNG) offset and size
        file.seek(0x38)
        self._label_offset = struct.unpack("<I", file.read(4))[0]
        file.seek(0x40)
        self._label_size = struct.unpack("<I", file.read(4))[0]

        # Macro (BMP) offset and size
        file.seek(0x50)
        self._macro_offset = struct.unpack("<I", file.read(4))[0]
        file.seek(0x58)
        self._macro_size = struct.unpack("<I", file.read(4))[0]

        # MPP (microns per pixel) - try to read from header at offset 0x10
        # DYJ format stores mpp as a float (4 bytes)
        file.seek(0x10)
        mpp_raw = struct.unpack("<f", file.read(4))[0]
        # Validate mpp value: should be positive and reasonable (0.1 - 1.0 μm/pixel typical)
        if 0.05 < mpp_raw < 5.0:
            self._mpp = mpp_raw
        else:
            # Default to 0.25 μm/pixel (40x magnification typical value)
            self._mpp = 0.25

        # ImageInfo records offset
        # For V1 format: read offset from 0xb0
        # For V2 format: use fixed offset 0x150
        file.seek(0xB0)
        self._image_info_offset_from_header = struct.unpack("<I", file.read(4))[0]

        # Determine actual record start offset
        self._image_info_offset = self._determine_record_offset()

        # Calculate tile grid (will be updated after building tile index)
        self._tiles_x = (self._width + self._tile_size - 1) // self._tile_size
        self._tiles_y = (self._height + self._tile_size - 1) // self._tile_size

    def _determine_record_offset(self) -> int:
        """Determine the correct offset for ImageInfo records.

        Different DYJ format versions store records at different locations:
        - V1 (0x2370): records at offset read from 0xb0
        - V2 (0x2490): records at fixed offset 0x150

        Returns:
            The correct offset to start reading records from.
        """
        # Try the offset from header first (V1 style)
        if self._format_version == 1:
            if self._validate_record_offset(self._image_info_offset_from_header):
                return self._image_info_offset_from_header

        # For V2 or unknown versions, try fixed offset 0x150
        if self._validate_record_offset(self.FIXED_RECORD_OFFSET):
            return self.FIXED_RECORD_OFFSET

        # Fallback: try offset from header anyway
        if self._validate_record_offset(self._image_info_offset_from_header):
            return self._image_info_offset_from_header

        # Last resort: use fixed offset
        return self.FIXED_RECORD_OFFSET

    def _validate_record_offset(self, offset: int) -> bool:
        """Validate if an offset points to valid ImageInfo records.

        Args:
            offset: The offset to validate

        Returns:
            True if valid records are found at this offset
        """
        try:
            file = self._require_file()
            file.seek(offset)
            # Check first few records
            valid_count = 0
            for _ in range(5):
                record = file.read(self.RECORD_SIZE)
                if len(record) < self.RECORD_SIZE:
                    return False

                layer = record[0]
                z = record[9]
                length = struct.unpack("<i", record[10:14])[0]
                file_offset = struct.unpack("<q", record[14:22])[0]

                # Basic validation
                if layer > 2 or z >= self.Z_LAYERS:
                    return False
                if length <= 0 or length > 500000:
                    return False
                if file_offset <= 0:
                    return False

                # Verify JPEG magic at offset
                cur_pos = file.tell()
                file.seek(file_offset)
                jpeg_magic = file.read(2)
                file.seek(cur_pos)

                if jpeg_magic == b"\xff\xd8":
                    valid_count += 1

            return valid_count >= 3  # At least 3 valid JPEG records
        except Exception:
            return False

    def _build_tile_index(self) -> None:
        """Build tile index from ImageInfo records.

        Each record is 22 bytes:
        - offset+0:  layer (1 byte)
        - offset+1:  X (4 bytes, uint32) - pixel coordinate
        - offset+5:  Y (4 bytes, uint32) - pixel coordinate
        - offset+9:  Z (1 byte)
        - offset+10: Length (4 bytes, int32)
        - offset+14: Offset (8 bytes, int64)
        """
        file = self._require_file()
        self._tile_index = {}
        max_x = 0
        max_y = 0

        file.seek(self._image_info_offset)

        # Read records until we hit invalid data
        while True:
            record = file.read(self.RECORD_SIZE)
            if len(record) < self.RECORD_SIZE:
                break

            layer = record[0]
            x = struct.unpack("<I", record[1:5])[0]
            y = struct.unpack("<I", record[5:9])[0]
            z = record[9]
            length = struct.unpack("<i", record[10:14])[0]
            offset = struct.unpack("<q", record[14:22])[0]

            # Validate record
            if layer > 2 or z >= self.Z_LAYERS:
                break
            if length <= 0 or length > 500000:
                break
            if offset <= 0:
                break

            # Verify it's a valid JPEG (check first time for each offset)
            current_pos = file.tell()
            file.seek(offset)
            magic = file.read(2)
            file.seek(current_pos)

            if magic != b"\xff\xd8":
                break

            # Store in index
            key = (layer, x, y, z)
            self._tile_index[key] = {"length": length, "offset": offset}

            # Track unified coordinate coverage
            if x > max_x:
                max_x = x
            if y > max_y:
                max_y = y

        # Calculate unified coordinate system size
        # The last tile at (max_x, max_y) covers tile_size more pixels
        self._unified_width = max_x + self._tile_size
        self._unified_height = max_y + self._tile_size

    def _init_properties(self):
        """Initialize cached properties."""
        self._properties = {
            "openslide.vendor": "DPT",
            "openslide.level-count": str(self.level_count),
            "openslide.level[0].width": str(self._width),
            "openslide.level[0].height": str(self._height),
            "openslide.level[0].downsample": "1.0",
            "openslide.level[1].width": str(self._width // 4),
            "openslide.level[1].height": str(self._height // 4),
            "openslide.level[1].downsample": "4.0",
            "openslide.level[2].width": str(self._width // 16),
            "openslide.level[2].height": str(self._height // 16),
            "openslide.level[2].downsample": "16.0",
            "openslide.mpp-x": str(self._mpp),
            "openslide.mpp-y": str(self._mpp),
            "openslide.objective-power": str(int(10.0 / self._mpp))
            if self._mpp > 0
            else "40",
            "dyj.version": hex(self._version),
            "dyj.tile_size": str(self._tile_size),
            "dyj.tiles_x": str(self._tiles_x),
            "dyj.tiles_y": str(self._tiles_y),
            "dyj.z_layers": str(self.Z_LAYERS),
            "dyj.current_z": str(self._z_layer),
        }

    def _check_closed(self):
        """Check if slide is closed."""
        if self._closed:
            raise RuntimeError("Slide has been closed")

    def _get_tile_by_position(
        self, layer: int, x: int, y: int, z: int | None = None
    ) -> Image.Image | None:
        """Read a tile by its unified coordinate position.

        Args:
            layer: Layer index (0, 1, or 2)
            x: X position in unified coordinate system
            y: Y position in unified coordinate system
            z: Z-stack layer (0-15). If None, uses instance default.

        Returns:
            PIL Image of the tile, or None if not found
        """
        file = self._require_file()
        z = self._z_layer if z is None else z

        key = (layer, x, y, z)
        if key not in self._tile_index:
            return None

        tile_info = self._tile_index[key]
        file.seek(tile_info["offset"])
        data = file.read(tile_info["length"])

        try:
            return Image.open(io.BytesIO(data))
        except Exception:
            return None

    def _get_tiles_for_layer(
        self, layer: int, z: int | None = None
    ) -> dict[tuple[int, int], DyjTileInfo]:
        """Get all tiles for a specific layer and z value.

        Args:
            layer: Layer index (0, 1, or 2)
            z: Z-stack layer (0-15). If None, uses instance default.

        Returns:
            Dict mapping (x, y) to tile info
        """
        z = self._z_layer if z is None else z

        result: dict[tuple[int, int], DyjTileInfo] = {}
        for key, value in self._tile_index.items():
            if key[0] == layer and key[3] == z:
                result[(key[1], key[2])] = value
        return result

    @classmethod
    def detect_format(cls, filename: str) -> str | None:
        """Detect if file is DYJ format.

        Supports both V1 (magic "DPTWSIp#") and V2 (magic "DPTWSI\x90$") formats.
        """
        try:
            with open(filename, "rb") as f:
                magic = f.read(8)
                # Check if magic starts with common prefix
                if magic.startswith(cls.MAGIC_PREFIX):
                    return "dyj"
        except Exception:
            pass
        return None

    @property
    def magnification(self) -> float:
        """Get slide magnification."""
        if self._mpp > 0:
            return 10.0 / self._mpp
        return 40.0

    @property
    def level_count(self) -> int:
        """Number of pyramid levels."""
        # DYJ has 3 tile sizes: 1280, 320, 80
        # This corresponds to 3 levels with downsamples 1, 4, 16
        return 3

    @property
    def dimensions(self) -> tuple[int, int]:
        """Dimensions of level 0 (width, height).

        Uses the unified coordinate system dimensions which represent
        the actual tile coverage area.
        """
        return (self._unified_width, self._unified_height)

    @property
    def level_dimensions(self) -> tuple[tuple[int, int], ...]:
        """Dimensions at each level.

        Based on unified coordinate system with downsample factors.
        """
        return (
            (self._unified_width, self._unified_height),
            (self._unified_width // 4, self._unified_height // 4),
            (self._unified_width // 16, self._unified_height // 16),
        )

    @property
    def level_downsamples(self) -> tuple[float, ...]:
        """Downsample factor for each level."""
        return (1.0, 4.0, 16.0)

    @property
    def mpp(self) -> float:
        """Microns per pixel at level 0."""
        return self._mpp

    @property
    def properties(self) -> dict[str, Any]:
        """Slide properties."""
        return self._properties.copy()

    @property
    def associated_images(self) -> dict[str, Image.Image]:
        """Associated images (thumbnail, label, macro)."""
        self._check_closed()
        result = {}

        try:
            result["thumbnail"] = self._read_thumbnail()
        except Exception:
            pass

        try:
            result["label"] = self._read_label()
        except Exception:
            pass

        try:
            result["macro"] = self._read_macro()
        except Exception:
            pass

        return result

    def _read_thumbnail(self) -> Image.Image:
        """Read thumbnail image (JPEG)."""
        file = self._require_file()
        file.seek(self._thumbnail_offset)
        data = file.read(self._thumbnail_size)
        return Image.open(io.BytesIO(data))

    def _read_label(self) -> Image.Image:
        """Read label image (PNG)."""
        file = self._require_file()
        file.seek(self._label_offset)
        data = file.read(self._label_size)
        return Image.open(io.BytesIO(data))

    def _read_macro(self) -> Image.Image:
        """Read macro image (BMP)."""
        file = self._require_file()
        file.seek(self._macro_offset)
        data = file.read(self._macro_size)
        return Image.open(io.BytesIO(data))

    def get_thumbnail(self, size: tuple[int, int]) -> Image.Image:
        """Get a thumbnail of the slide.

        Args:
            size: (width, height) tuple for the thumbnail size

        Returns:
            PIL Image of the thumbnail
        """
        self._check_closed()
        thumb = self._read_thumbnail()
        try:
            thumb.thumbnail(size, Image.Resampling.LANCZOS)
        except AttributeError:
            # Older PIL versions
            thumb.thumbnail(size, Image.Resampling.LANCZOS)
        return thumb

    def get_best_level_for_downsample(self, downsample: float) -> int:
        """Get the best level for a given downsample factor.

        This mirrors OpenSlide's behavior:
        - Return the largest level whose downsample is <= target
        - This ensures we don't over-downsample (lose resolution)

        Args:
            downsample: The desired downsample factor

        Returns:
            The level number
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

    def read_region(
        self, location: tuple[int, int], level: int, size: tuple[int, int]
    ) -> Image.Image:
        """Read a region from the slide.

        Args:
            location: (x, y) tuple of top-left corner in level 0 coordinates
                     (unified coordinate system)
            level: pyramid level to read from (0, 1, or 2)
            size: (width, height) tuple of the region size at the specified level

        Returns:
            PIL Image of the requested region (RGBA)
        """
        file = self._require_file()

        if level < 0 or level >= self.level_count:
            raise ValueError(f"Invalid level: {level}")

        req_x, req_y = location
        width, height = size

        # Get parameters for this level
        tile_size = self.TILE_SIZES[level]
        downsample = int(self.level_downsamples[level])
        layer_downsample = self.LAYER_DOWNSAMPLES[level]

        # Location is in level 0 (unified) coordinates
        # Convert to unified coordinates for tile lookup
        unified_x = req_x
        unified_y = req_y

        # Output size in unified coordinates
        unified_width = width * downsample
        unified_height = height * downsample

        # Get all tiles for this layer and z
        tiles = self._get_tiles_for_layer(level, self._z_layer)

        # Create output image
        result = Image.new("RGBA", (width, height), (255, 255, 255, 0))

        # Find tiles that overlap with our region
        for (tile_x, tile_y), tile_info in tiles.items():
            # Each tile covers [tile_x, tile_x + 1280) in unified coordinates
            tile_coverage = self._tile_size  # 1280 in unified coords

            # Check if this tile overlaps with our request
            tile_right = tile_x + tile_coverage
            tile_bottom = tile_y + tile_coverage
            req_right = unified_x + unified_width
            req_bottom = unified_y + unified_height

            if tile_x >= req_right or tile_right <= unified_x:
                continue
            if tile_y >= req_bottom or tile_bottom <= unified_y:
                continue

            # Load the tile
            file.seek(tile_info["offset"])
            data = file.read(tile_info["length"])

            try:
                tile_img = Image.open(io.BytesIO(data))
            except Exception:
                continue

            if tile_img.mode != "RGBA":
                tile_img = tile_img.convert("RGBA")

            # Calculate intersection in unified coordinates
            inter_left = max(tile_x, unified_x)
            inter_top = max(tile_y, unified_y)
            inter_right = min(tile_right, req_right)
            inter_bottom = min(tile_bottom, req_bottom)

            # Convert to tile-local coordinates
            # Tile pixel coords: (unified_coord - tile_x) / layer_downsample
            crop_left = (inter_left - tile_x) // layer_downsample
            crop_top = (inter_top - tile_y) // layer_downsample
            crop_right = (inter_right - tile_x) // layer_downsample
            crop_bottom = (inter_bottom - tile_y) // layer_downsample

            # Clamp to tile size
            crop_right = min(crop_right, tile_size)
            crop_bottom = min(crop_bottom, tile_size)

            if crop_right <= crop_left or crop_bottom <= crop_top:
                continue

            # Crop the tile
            cropped = tile_img.crop((crop_left, crop_top, crop_right, crop_bottom))

            # Calculate paste position in result
            # Result coords: (inter_unified - req_unified) / downsample
            paste_x = (inter_left - unified_x) // downsample
            paste_y = (inter_top - unified_y) // downsample

            result.paste(cropped, (paste_x, paste_y))

        # Apply color correction if enabled
        result = self._color_correction.apply(result)

        return result

    def read_fixed_region(
        self, location: tuple[int, int], level: int, size: tuple[int, int]
    ) -> Image.Image:
        """Read a fixed region from the slide (tile-based reading).

        This method reads a single tile at the given location. The size parameter
        indicates the expected tile size but is not strictly enforced.

        Args:
            location: (x, y) tuple of top-left corner in level 0 coordinates
            level: pyramid level to read from (0, 1, or 2)
            size: (width, height) tuple of the expected region size (used as hint)

        Returns:
            PIL Image of the tile at the requested location
        """
        # For DYJ format, read_fixed_region uses the same logic as read_region
        # since DYJ tiles are already fixed-size (1280x1280 at level 0)
        return self.read_region(location, level, size)

    def apply_color_correction(self, apply: bool = True, style: str = "Real"):
        """Apply or disable color correction.

        Args:
            apply: Whether to apply color correction
            style: Color correction style ("Real" or "Real2")
        """
        self._color_correction.enabled = apply
        if style:
            self._color_correction.set_style(style)

    def get_color_correction_info(self) -> dict[str, Any]:
        """Get current color correction parameters."""
        return self._color_correction.get_info()

    def close(self):
        """Close the slide and free resources."""
        if self._closed:
            return

        try:
            file = self._file
            if file is not None:
                file.close()
                self._file = None
        except Exception:
            pass
        finally:
            self._closed = True

    def __del__(self):
        """Destructor."""
        try:
            if not self._closed:
                self.close()
        except Exception:
            pass

    def __repr__(self):
        return f"DyjSlide({self._filename!r})"
