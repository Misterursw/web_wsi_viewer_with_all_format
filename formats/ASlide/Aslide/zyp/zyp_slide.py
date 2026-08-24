"""ZYP slide format reader.

File structure (based on C++ SDK analysis):
- JPEG tiles stored at positions specified in metadata
- Metadata section at the end with FFFE FF <length> format UTF-16LE encoded segments
- Tile coordinate format depends on version:
  - Version 1.10: flat,level,x,y (4 parts)
  - Version 2.01: channel,flat,level,x,y (5 parts)
- ScanMode: 0=Flatbed, 1=Stacked Flatbed, 2=Fused Flatbed
- Each tile entry: coord -> StartPosition -> value -> DataLength -> value

Key metadata fields:
- SliceInfo section: ROILeft, ROITop, SliceWidth, SliceHeight, LevelCount, etc.
- Preview section: Preview image StartPosition/DataLength
- Label section: Label image StartPosition/DataLength
"""

import io
from typing import BinaryIO

from PIL import Image


class ZypSlide:
    """ZYP slide reader compatible with OpenSlide-like interface."""

    TILE_SIZE: int = 256

    def __init__(self, filename: str):
        """Open a ZYP slide file.

        Args:
            filename: Path to the ZYP file
        """
        self._filename: str = filename
        self._file: BinaryIO | None = open(filename, "rb")
        self._file.seek(0, 2)
        self._file_size: int = self._file.tell()
        self._closed: bool = False

        # Slide metadata
        self._version: str = "2.01"  # Default to 2.01
        self._scan_mode: int = 0
        self._flat_num: int = 1
        self._location_channel_id: int = 0
        self._roi_left: int = 0
        self._roi_top: int = 0
        self._metadata_start: int = 0
        self._slice_width: int = 0
        self._slice_height: int = 0
        self._level_count_meta: int = 0
        self._mpp: float | None = None
        self._roi_tile_x: int = 0
        self._roi_tile_y: int = 0
        self._width: int = 0
        self._height: int = 0
        self._level_count: int = 0
        self._level_dimensions: list[tuple[int, int]] = []
        self._level_downsamples: list[float] = []
        self._level_tiles: dict[int, list[tuple[int, int]]] = {}

        # Tile index: coord_str -> (start_pos, data_len)
        self._tile_index: dict[str, tuple[int, int]] = {}

        # Properties
        self._properties: dict[str, str] = {
            "openslide.vendor": "winmedic",
        }

        # Associated images
        self._preview_pos: tuple[int, int] | None = None  # (start_pos, data_len)
        self._original_preview_pos: tuple[int, int] | None = None
        self._label_pos: tuple[int, int] | None = None
        self._barcode_pos: tuple[int, int] | None = None

        # Parse metadata
        self._parse_metadata()
        self._compute_dimensions()

    def _require_file(self) -> BinaryIO:
        file = self._file
        if self._closed or file is None:
            raise RuntimeError("Slide has been closed")
        return file

    def _parse_metadata(self) -> None:
        """Parse the metadata section at the end of the file.

        ZYP metadata format:
        - Starts with FFFE FF <length> pattern
        - Each segment is UTF-16LE encoded
        - Format: FFFE FF <len_byte> <utf16le_text>
        """
        file = self._require_file()
        # Search for first FFFE marker from the end
        search_size = min(10 * 1024 * 1024, self._file_size)  # Search last 10MB
        file.seek(max(0, self._file_size - search_size))
        tail_chunk = file.read(search_size)

        # Find first FFFE FF pattern (metadata start marker)
        first_fffe = -1
        for i in range(len(tail_chunk) - 2):
            if tail_chunk[i : i + 3] == b"\xff\xfe\xff":
                first_fffe = i
                break

        if first_fffe == -1:
            raise ValueError("Invalid ZYP file: no metadata found")

        self._metadata_start = max(0, self._file_size - search_size) + first_fffe

        # Parse segments from metadata
        meta_data = tail_chunk[first_fffe:]
        segments = self._parse_segments(meta_data)
        self._process_segments(segments)

    def _parse_segments(self, meta_data: bytes) -> list[str]:
        """Parse FFFE FF <length> UTF-16LE segments.

        Format: FF FE FF <length_byte> <utf16le_text of length*2 bytes>
        """
        segments: list[str] = []
        i = 0
        while i < len(meta_data) - 3:
            # Look for FFFE FF pattern
            if meta_data[i : i + 3] == b"\xff\xfe\xff":
                length = meta_data[i + 3]
                i += 4
                if length > 0 and i + length * 2 <= len(meta_data):
                    text_bytes = meta_data[i : i + length * 2]
                    try:
                        text = text_bytes.decode("utf-16le")
                        segments.append(text)
                    except UnicodeDecodeError:
                        pass
                    i += length * 2
                else:
                    i += 1
            else:
                i += 1
        return segments

    def _process_segments(self, segments: list[str]) -> None:
        """Process parsed segments into tile index and properties.

        Tile coordinate format:
        - Version 2.01: channel,flat,level,x,y (5 parts)
        - Version 1.10: flat,level,x,y (4 parts)

        Tile entry pattern: coord -> StartPosition -> value -> DataLength -> value
        """
        i = 0
        while i < len(segments):
            seg = segments[i]

            # Parse key-value pairs for properties
            if i + 1 < len(segments):
                key = seg
                value = segments[i + 1]

                # Extract important properties
                if key == "Version":
                    self._version = value
                    self._properties["zyp.version"] = value
                    i += 2
                    continue
                elif key == "ScanMode":
                    try:
                        self._scan_mode = int(value)
                        self._properties["zyp.scan_mode"] = value
                    except ValueError:
                        pass
                    i += 2
                    continue
                elif key == "FlatNum":
                    try:
                        self._flat_num = int(value)
                        self._properties["zyp.flat_num"] = value
                    except ValueError:
                        pass
                    i += 2
                    continue
                elif key == "LocationChannelId":
                    try:
                        self._location_channel_id = int(value)
                    except ValueError:
                        pass
                    i += 2
                    continue
                elif key == "ROILeft":
                    try:
                        self._roi_left = int(value)
                        self._properties["zyp.roi_left"] = value
                    except ValueError:
                        pass
                    i += 2
                    continue
                elif key == "ROITop":
                    try:
                        self._roi_top = int(value)
                        self._properties["zyp.roi_top"] = value
                    except ValueError:
                        pass
                    i += 2
                    continue
                elif key == "SliceWidth":
                    try:
                        self._slice_width = int(value)
                        self._properties["zyp.slice_width"] = value
                    except ValueError:
                        pass
                    i += 2
                    continue
                elif key == "SliceHeight":
                    try:
                        self._slice_height = int(value)
                        self._properties["zyp.slice_height"] = value
                    except ValueError:
                        pass
                    i += 2
                    continue
                elif key == "LevelCount":
                    try:
                        self._level_count_meta = int(value)
                        self._properties["zyp.level_count"] = value
                    except ValueError:
                        pass
                    i += 2
                    continue
                elif key == "MicrometersPerPixel":
                    try:
                        self._mpp = float(value)
                        self._properties["openslide.mpp-x"] = value
                        self._properties["openslide.mpp-y"] = value
                        if self._mpp > 0:
                            self._properties["openslide.objective-power"] = str(
                                int(10.0 / self._mpp)
                            )
                    except ValueError:
                        pass
                    i += 2
                    continue
                elif key == "ScanZoom":
                    try:
                        self._properties["zyp.scan_zoom"] = value
                        self._properties["openslide.objective-power"] = value
                    except ValueError:
                        pass
                    i += 2
                    continue

            # Check for tile position format: coord, StartPosition, pos, DataLength, len
            if (
                i + 4 < len(segments)
                and segments[i + 1] == "StartPosition"
                and segments[i + 3] == "DataLength"
            ):
                try:
                    start_pos = int(segments[i + 2])
                    data_len = int(segments[i + 4])

                    # Check if this is Preview, OriginalPreview, Label, or Barcode
                    if seg == "Preview":
                        self._preview_pos = (start_pos, data_len)
                        i += 5
                        continue
                    elif seg == "OriginalPreview":
                        self._original_preview_pos = (start_pos, data_len)
                        i += 5
                        continue
                    elif seg == "Label":
                        self._label_pos = (start_pos, data_len)
                        i += 5
                        continue
                    elif seg == "Barcode":
                        self._barcode_pos = (start_pos, data_len)
                        i += 5
                        continue

                    # Parse tile coordinates
                    parts = seg.split(",")
                    if len(parts) in [4, 5]:
                        # Store as coordinate string for lookup
                        self._tile_index[seg] = (start_pos, data_len)
                        i += 5
                        continue
                except ValueError:
                    pass

            i += 1

    def _compute_dimensions(self) -> None:
        """Compute image dimensions from tile index.

        Tile coordinate format:
        - Version 2.01: channel,flat,level,x,y (5 parts)
        - Version 1.10: flat,level,x,y (4 parts)

        Level 0 is the highest resolution (base level).
        """
        if not self._tile_index:
            raise ValueError("No tile positions found in ZYP file")

        # Parse tile coordinates and organize by level
        # level -> list of (x, y) tile coordinates
        level_tiles: dict[int, list[tuple[int, int]]] = {}

        for coord_str in self._tile_index.keys():
            parts = coord_str.split(",")
            try:
                if len(parts) == 5:
                    # Version 2.01: channel,flat,level,x,y
                    level = int(parts[2])
                    x = int(parts[3])
                    y = int(parts[4])
                elif len(parts) == 4:
                    # Version 1.10: flat,level,x,y
                    level = int(parts[1])
                    x = int(parts[2])
                    y = int(parts[3])
                else:
                    continue

                if level not in level_tiles:
                    level_tiles[level] = []
                level_tiles[level].append((x, y))
            except ValueError:
                continue

        if not level_tiles:
            raise ValueError("No valid tile coordinates found in ZYP file")

        # Get level 0 tiles (highest resolution)
        if 0 not in level_tiles:
            raise ValueError("No level 0 tiles found in ZYP file")

        level0_tiles = level_tiles[0]

        # Calculate ROI tile offset (tiles may not start from 0,0)
        self._roi_tile_x = min(t[0] for t in level0_tiles)
        self._roi_tile_y = min(t[1] for t in level0_tiles)
        max_tile_x = max(t[0] for t in level0_tiles)
        max_tile_y = max(t[1] for t in level0_tiles)

        # Level 0 dimensions
        self._width = (max_tile_x - self._roi_tile_x + 1) * self.TILE_SIZE
        self._height = (max_tile_y - self._roi_tile_y + 1) * self.TILE_SIZE

        # Use SliceWidth/SliceHeight if available (more accurate)
        if self._slice_width > 0 and self._slice_height > 0:
            self._width = self._slice_width
            self._height = self._slice_height

        # Compute level count and dimensions
        self._level_count = max(level_tiles.keys()) + 1

        # Use LevelCount from metadata if available
        if self._level_count_meta > 0:
            self._level_count = max(self._level_count, self._level_count_meta)

        # Compute level dimensions
        self._level_dimensions = [(self._width, self._height)]
        for level in range(1, self._level_count):
            scale = 2**level
            w = max(1, self._width // scale)
            h = max(1, self._height // scale)
            self._level_dimensions.append((w, h))

        # Compute downsamples
        self._level_downsamples = [float(2**i) for i in range(self._level_count)]

        # Store level tile info for read_region
        self._level_tiles = level_tiles

    def __repr__(self):
        return f"{self.__class__.__name__}({self._filename!r})"

    def close(self):
        """Close the slide file."""
        if self._closed:
            return
        file = self._file
        if file is not None:
            file.close()
            self._file = None
        self._closed = True

    def __del__(self):
        """Destructor."""
        try:
            if not getattr(self, "_closed", True):
                self.close()
        except Exception:
            pass

    @property
    def level_count(self) -> int:
        """Number of pyramid levels."""
        return self._level_count

    @property
    def dimensions(self) -> tuple[int, int]:
        """Dimensions of level 0 (width, height)."""
        return (self._width, self._height)

    @property
    def level_dimensions(self) -> tuple[tuple[int, int], ...]:
        """Dimensions of each pyramid level."""
        return tuple(self._level_dimensions)

    @property
    def level_downsamples(self) -> tuple[float, ...]:
        """Downsample factor for each level."""
        return tuple(self._level_downsamples)

    @property
    def properties(self) -> dict[str, str]:
        """Slide properties."""
        return self._properties

    @property
    def associated_images(self) -> dict[str, Image.Image]:
        """Associated images (thumbnail, label, macro)."""
        file = self._require_file()
        result: dict[str, Image.Image] = {}

        # Read Preview image as thumbnail
        if self._preview_pos:
            try:
                pos, length = self._preview_pos
                file.seek(pos)
                data = file.read(length)
                img = Image.open(io.BytesIO(data))
                result["thumbnail"] = img
            except Exception:
                pass

        # Read OriginalPreview as macro (higher resolution preview)
        if self._original_preview_pos:
            try:
                pos, length = self._original_preview_pos
                file.seek(pos)
                data = file.read(length)
                img = Image.open(io.BytesIO(data))
                result["macro"] = img
            except Exception:
                pass
        elif "thumbnail" in result:
            # Fallback: use thumbnail as macro if no OriginalPreview
            result["macro"] = result["thumbnail"]

        # Read Label image (explicit Label or Barcode)
        # Barcode is used as label in ZYP format
        label_pos = self._label_pos or self._barcode_pos
        if label_pos:
            try:
                pos, length = label_pos
                file.seek(pos)
                data = file.read(length)
                img = Image.open(io.BytesIO(data))
                result["label"] = img
            except Exception:
                pass

        return result

    @property
    def mpp(self) -> float | None:
        """Microns per pixel (if available)."""
        return self._mpp

    def get_best_level_for_downsample(self, downsample: float) -> int:
        """Get the best level for a given downsample factor."""
        for i, ds in enumerate(self._level_downsamples):
            if ds > downsample:
                return max(0, i - 1)
        return self._level_count - 1

    def get_thumbnail(self, size: tuple[int, int]) -> Image.Image:
        """Get a thumbnail of the slide."""
        file = self._require_file()
        # Try to use Preview image first
        if self._preview_pos:
            try:
                pos, length = self._preview_pos
                file.seek(pos)
                data = file.read(length)
                thumb = Image.open(io.BytesIO(data))
                thumb.thumbnail(size, Image.Resampling.LANCZOS)
                return thumb
            except Exception:
                pass

        # Fallback: read from highest level
        highest_level = self._level_count - 1
        level_dims = self._level_dimensions[highest_level]
        thumb = self.read_region((0, 0), highest_level, level_dims)
        thumb.thumbnail(size, Image.Resampling.LANCZOS)
        return thumb

    def _build_tile_coord(self, level: int, x: int, y: int) -> str:
        """Build tile coordinate string for lookup.

        Args:
            level: Pyramid level (0 = highest resolution)
            x: Tile x coordinate
            y: Tile y coordinate

        Returns:
            Coordinate string matching the format in _tile_index
        """
        if self._version.startswith("2"):
            # Version 2.01: channel,flat,level,x,y
            # For ScanMode 0, flat is always 0
            channel = self._location_channel_id
            flat = 0
            return f"{channel},{flat},{level},{x},{y}"
        else:
            # Version 1.10: flat,level,x,y
            flat = 0
            return f"{flat},{level},{x},{y}"

    def _read_tile(self, level: int, x: int, y: int) -> Image.Image | None:
        """Read a single tile from the file.

        Args:
            level: Pyramid level
            x: Tile x coordinate (in file coordinates, not ROI coordinates)
            y: Tile y coordinate

        Returns:
            PIL Image or None if tile not found
        """
        coord = self._build_tile_coord(level, x, y)
        if coord not in self._tile_index:
            return None

        file = self._require_file()
        pos, length = self._tile_index[coord]
        file.seek(pos)
        tile_data = file.read(length)

        try:
            return Image.open(io.BytesIO(tile_data))
        except Exception:
            return None

    def read_region(
        self, location: tuple[int, int], level: int, size: tuple[int, int]
    ) -> Image.Image:
        """Read a region from the slide.

        Args:
            location: (x, y) tuple of the top-left corner in level 0 coordinates
            level: Pyramid level to read from
            size: (width, height) tuple of the region size at the specified level

        Returns:
            PIL Image object (RGBA)
        """
        x, y = location
        width, height = size

        # Convert level 0 coordinates to level coordinates
        downsample = self._level_downsamples[level]
        level_x = int(x / downsample)
        level_y = int(y / downsample)

        # Create output image
        result = Image.new("RGBA", (width, height), (255, 255, 255, 255))

        # Read tiles for this level
        self._read_level_region(result, level, level_x, level_y, width, height)

        return result

    def _get_level_roi_offset(self, level: int) -> tuple[int, int]:
        """Get the ROI tile offset for a specific level.

        For level 0, this is _roi_tile_x, _roi_tile_y.
        For other levels, we need to find the minimum tile coordinates.
        """
        if level == 0:
            return (self._roi_tile_x, self._roi_tile_y)

        # Find tiles for this level
        if level not in self._level_tiles:
            # No tiles for this level, use scaled level 0 offset
            scale = 2**level
            return (self._roi_tile_x // scale, self._roi_tile_y // scale)

        tiles = self._level_tiles[level]
        min_x = min(t[0] for t in tiles)
        min_y = min(t[1] for t in tiles)
        return (min_x, min_y)

    def _read_level_region(
        self, result: Image.Image, level: int, x: int, y: int, width: int, height: int
    ):
        """Read a region from tiles at the specified level.

        Args:
            result: Output image to paste tiles into
            level: Pyramid level
            x: X coordinate in level coordinates (not level 0)
            y: Y coordinate in level coordinates
            width: Width of region
            height: Height of region
        """
        # Check if we have tiles for this level
        if level not in self._level_tiles:
            # No tiles for this level, downsample from level 0
            self._downsample_from_level0(result, level, x, y, width, height)
            return

        # Get ROI offset for this level
        roi_tile_x, roi_tile_y = self._get_level_roi_offset(level)

        # Calculate tile range in ROI coordinates
        start_tile_x = x // self.TILE_SIZE
        start_tile_y = y // self.TILE_SIZE
        end_tile_x = (x + width - 1) // self.TILE_SIZE
        end_tile_y = (y + height - 1) // self.TILE_SIZE

        for tile_y in range(start_tile_y, end_tile_y + 1):
            for tile_x in range(start_tile_x, end_tile_x + 1):
                # Convert ROI tile coordinates to file tile coordinates
                file_tile_x = tile_x + roi_tile_x
                file_tile_y = tile_y + roi_tile_y

                tile = self._read_tile(level, file_tile_x, file_tile_y)
                if tile is None:
                    continue

                # Calculate paste position (in ROI coordinates)
                paste_x = tile_x * self.TILE_SIZE - x
                paste_y = tile_y * self.TILE_SIZE - y

                # Handle partial tiles at edges
                src_x = max(0, -paste_x)
                src_y = max(0, -paste_y)
                dst_x = max(0, paste_x)
                dst_y = max(0, paste_y)

                # Calculate copy size
                copy_w = min(tile.width - src_x, width - dst_x)
                copy_h = min(tile.height - src_y, height - dst_y)

                if copy_w > 0 and copy_h > 0:
                    # Crop tile if needed
                    if (
                        src_x > 0
                        or src_y > 0
                        or copy_w < tile.width
                        or copy_h < tile.height
                    ):
                        tile = tile.crop((src_x, src_y, src_x + copy_w, src_y + copy_h))

                    # Convert to RGBA if needed
                    if tile.mode != "RGBA":
                        tile = tile.convert("RGBA")

                    result.paste(tile, (dst_x, dst_y))

    def _downsample_from_level0(
        self, result: Image.Image, level: int, x: int, y: int, width: int, height: int
    ):
        """Downsample a region from level 0."""
        downsample = self._level_downsamples[level]

        # Calculate level 0 region
        l0_x = int(x * downsample)
        l0_y = int(y * downsample)
        l0_width = int(width * downsample)
        l0_height = int(height * downsample)

        # Read from level 0
        l0_region = Image.new("RGBA", (l0_width, l0_height), (255, 255, 255, 255))
        self._read_level_region(l0_region, 0, l0_x, l0_y, l0_width, l0_height)

        # Downsample
        downsampled = l0_region.resize((width, height), Image.Resampling.LANCZOS)
        result.paste(downsampled, (0, 0))
