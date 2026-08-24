"""
IBL format reader for ASlide.

IBL Format Structure (苏州秉理 BingLi WSI format):
- SQLite 3.x database
- Magic number: "ibl" in tbl_base_info.magicNo

Version 1.x (legacy):
- tbl_base_info: Basic slide information (dimensions, tile size, layers)
- tbl_tile_info: Tile data (JPEG compressed)
  - Layer 0: 4x4 sub-tiles per image block (612x512 each, total 2448x2048)
  - Layer 1: 1 tile per image block (612x512, 4x downsample)
- tbl_shrink_info: Shrink layer tiles (layer 2, 16x downsample)
- tbl_img_info: Image block index (maps img_id to grid position)
- tbl_ext_info: Associated images (thumbnail, label, macro)

Version 2.x (new):
- tbl_base_info: Basic slide information
- tbl_tileex_info: Direct tile storage by (layer, col, row)
  - Multiple pyramid layers (0-7+), each tile is 512x512
  - Tiles stored directly with JPEG data
- tbl_ext_info: Associated images (thumbnail, label, macro)
"""

import sqlite3
import io
import os
from typing import Any, TypedDict
from PIL import Image


class IblV2LayerInfo(TypedDict):
    min_col: int
    max_col: int
    min_row: int
    max_row: int
    tile_count: int


class IblImgIndexInfo(TypedDict):
    col: int
    row: int
    nX: int
    nY: int


class IblSlide:
    """
    IBL slide reader for 苏州秉理 (BingLi) WSI files.

    Supports:
    - Reading header information (dimensions, tile size)
    - Extracting thumbnail, label, and macro images
    - read_region for reading arbitrary regions
    - Multiple pyramid levels
    - Both v1.x and v2.x format versions
    """

    # Associated image types in tbl_ext_info
    EXT_TYPE_MACRO: int = 1
    EXT_TYPE_LABEL: int = 2
    EXT_TYPE_THUMBNAIL: int = 3

    def __init__(self, filename: str):
        """Initialize IBL slide reader.

        Args:
            filename: Path to the IBL file
        """
        if not os.path.exists(filename):
            raise FileNotFoundError(f"IBL file not found: {filename}")

        self._filename: str = filename
        self._closed: bool = False

        # Open SQLite connection
        self._conn: sqlite3.Connection | None = sqlite3.connect(filename)
        self._conn.row_factory = sqlite3.Row
        self._cursor: sqlite3.Cursor | None = self._conn.cursor()

        self._is_v2: bool = False
        self._version: str = ""
        self._ratio_step: int = 1
        self._total_width: int = 0
        self._total_height: int = 0
        self._tile_width: int = 0
        self._tile_height: int = 0
        self._img_width: int = 0
        self._img_height: int = 0
        self._img_col: int = 0
        self._img_row: int = 0
        self._pixel_size: float = 0.00025
        self._max_zoom: Any = None
        self._mpp: float = 0.25
        self._layer_count: int = 0
        self._sub_tile_width: int = 0
        self._sub_tile_height: int = 0
        self._sub_tiles_x: int = 0
        self._sub_tiles_y: int = 0
        self._block_width: int = 0
        self._block_height: int = 0
        self._v2_layer_info: dict[int, IblV2LayerInfo] = {}
        self._v2_layers: list[int] = []
        self._img_index: dict[int, IblImgIndexInfo] = {}
        self._properties: dict[str, str] = {}

        # Detect format version
        self._detect_version()

        # Parse base info
        self._parse_base_info()

        # Build image block index (v1 only)
        if not self._is_v2:
            self._build_img_index()

        # Cache properties
        self._init_properties()

    def _require_cursor(self) -> sqlite3.Cursor:
        cursor = self._cursor
        if self._closed or cursor is None:
            raise RuntimeError("Slide has been closed")
        return cursor

    def _detect_version(self) -> None:
        """Detect IBL format version based on table structure."""
        cursor = self._require_cursor()
        # Check if tbl_tileex_info exists (v2.0 indicator)
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tbl_tileex_info'"
        )
        has_tileex = cursor.fetchone() is not None

        # Check if tbl_img_info exists (v1.0 indicator)
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tbl_img_info'"
        )
        has_img_info = cursor.fetchone() is not None

        # v2.0 uses tbl_tileex_info, v1.0 uses tbl_img_info + tbl_tile_info
        self._is_v2 = has_tileex and not has_img_info

    def _parse_base_info(self) -> None:
        """Parse basic slide information from tbl_base_info."""
        cursor = self._require_cursor()
        cursor.execute("SELECT * FROM tbl_base_info LIMIT 1")
        row = cursor.fetchone()

        if not row:
            raise ValueError("Invalid IBL file: no base info found")

        # Verify magic number
        if row["magicNo"] != "ibl":
            raise ValueError(
                f"Invalid IBL file: expected magic 'ibl', got '{row['magicNo']}'"
            )

        self._version = row["version"]
        self._ratio_step = row[
            "ratio_step"
        ]  # Usually 4 (downsample factor between layers)
        self._total_width = int(row["total_img_width"])
        self._total_height = int(row["total_img_height"])
        self._tile_width = row["tile_width"]  # 612 (v1) or 512 (v2)
        self._tile_height = row["tile_height"]  # 512
        self._img_width = row["img_width"]  # 2448 (v1) or 1664 (v2)
        self._img_height = row["img_height"]  # 2048 (v1) or 1392 (v2)
        self._img_col = row["img_col"]  # Grid columns
        self._img_row = row["img_row"]  # Grid rows
        self._pixel_size = float(row["pixel_size"]) if row["pixel_size"] else 0.00025
        self._max_zoom = row["max_zoom_rate"]

        # Calculate MPP (microns per pixel)
        # pixel_size is in mm, convert to microns
        self._mpp = self._pixel_size * 1000 if self._pixel_size > 0 else 0.25

        if self._is_v2:
            # v2: Build level info from tbl_tileex_info
            self._build_v2_level_info()
        else:
            # v1: Use fixed 3 layers from base_info
            self._layer_count = row["layer_size"]  # Usually 3
            # v1 specific: sub-tile and block sizes
            self._sub_tile_width = 612
            self._sub_tile_height = 512
            self._sub_tiles_x = 4
            self._sub_tiles_y = 4
            self._block_width = self._sub_tile_width * self._sub_tiles_x  # 2448
            self._block_height = self._sub_tile_height * self._sub_tiles_y  # 2048

    def _build_v2_level_info(self) -> None:
        """Build level information for v2.0 format from tbl_tileex_info."""
        cursor = self._require_cursor()
        # Get all layers and their tile ranges
        cursor.execute("""
            SELECT layer, MIN(col) as min_col, MAX(col) as max_col,
                   MIN(row) as min_row, MAX(row) as max_row, COUNT(*) as cnt
            FROM tbl_tileex_info
            GROUP BY layer
            ORDER BY layer
        """)

        self._v2_layer_info = {}
        layers: list[int] = []
        for row in cursor.fetchall():
            layer = int(row["layer"])
            layers.append(layer)
            self._v2_layer_info[layer] = {
                "min_col": int(row["min_col"]),
                "max_col": int(row["max_col"]),
                "min_row": int(row["min_row"]),
                "max_row": int(row["max_row"]),
                "tile_count": int(row["cnt"]),
            }

        self._layer_count = len(layers)
        self._v2_layers = sorted(layers)

    def _build_img_index(self) -> None:
        """Build image block index from tbl_img_info (v1.0 only)."""
        self._img_index = {}  # {img_id: {'col': col, 'row': row, 'nX': nX, 'nY': nY}}
        cursor = self._require_cursor()

        cursor.execute("""
            SELECT id, col, row, nX, nY
            FROM tbl_img_info
            WHERE layer = 0
        """)

        for row in cursor.fetchall():
            self._img_index[int(row["id"])] = {
                "col": int(row["col"]),
                "row": int(row["row"]),
                "nX": int(row["nX"]),
                "nY": int(row["nY"]),
            }

    def _init_properties(self):
        """Initialize cached properties."""
        self._properties = {
            "openslide.vendor": "BingLi",
            "openslide.level-count": str(self.level_count),
            "openslide.mpp-x": str(self._mpp),
            "openslide.mpp-y": str(self._mpp),
            "ibl.version": self._version,
            "ibl.tile_width": str(self._tile_width),
            "ibl.tile_height": str(self._tile_height),
            "ibl.img_col": str(self._img_col),
            "ibl.img_row": str(self._img_row),
        }

        # Add objective power to properties
        mag = self.magnification
        if mag:
            self._properties["openslide.objective-power"] = str(mag)

        # Add level info
        for i, (w, h) in enumerate(self.level_dimensions):
            self._properties[f"openslide.level[{i}].width"] = str(w)
            self._properties[f"openslide.level[{i}].height"] = str(h)
            self._properties[f"openslide.level[{i}].downsample"] = str(
                self.level_downsamples[i]
            )

    def _check_closed(self):
        """Check if slide is closed."""
        if self._closed:
            raise RuntimeError("Slide has been closed")

    @classmethod
    def detect_format(cls, filename: str) -> str | None:
        if not os.path.exists(filename):
            return None

        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(filename)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT magicNo FROM tbl_base_info LIMIT 1")
            row = cursor.fetchone()
            if row is not None and row["magicNo"] == "ibl":
                return "ibl"
        except Exception:
            return None
        finally:
            if conn is not None:
                conn.close()

        return None

    @property
    def level_count(self) -> int:
        """Number of pyramid levels."""
        return self._layer_count

    @property
    def dimensions(self) -> tuple[int, int]:
        """Dimensions of level 0 (width, height)."""
        return (self._total_width, self._total_height)

    @property
    def level_dimensions(self) -> tuple[tuple[int, int], ...]:
        """Dimensions at each level."""
        dims: list[tuple[int, int]] = []
        for i in range(self._layer_count):
            downsample = self._ratio_step**i
            w = max(1, self._total_width // downsample)
            h = max(1, self._total_height // downsample)
            dims.append((w, h))
        return tuple(dims)

    @property
    def level_downsamples(self) -> tuple[float, ...]:
        """Downsample factor for each level."""
        return tuple(float(self._ratio_step**i) for i in range(self._layer_count))

    @property
    def mpp(self) -> float:
        """Microns per pixel."""
        return self._mpp

    @property
    def magnification(self) -> float | None:
        """Get the objective power/magnification."""
        if self._max_zoom:
            try:
                return float(self._max_zoom)
            except (ValueError, TypeError):
                pass

        # Fallback to calculation from MPP
        if self._mpp > 0:
            return 10.0 / self._mpp
        return None

    @property
    def properties(self) -> dict[str, Any]:
        """Slide properties."""
        return self._properties.copy()

    @property
    def associated_images(self) -> dict[str, Image.Image]:
        """Associated images (thumbnail, label, macro)."""
        self._check_closed()
        cursor = self._require_cursor()
        result: dict[str, Image.Image] = {}

        for name, ext_type in [
            ("thumbnail", self.EXT_TYPE_THUMBNAIL),
            ("label", self.EXT_TYPE_LABEL),
            ("macro", self.EXT_TYPE_MACRO),
        ]:
            try:
                cursor.execute(
                    "SELECT data FROM tbl_ext_info WHERE type = ?", (ext_type,)
                )
                row = cursor.fetchone()
                if row and row["data"]:
                    result[name] = Image.open(io.BytesIO(row["data"]))
            except Exception:
                pass

        return result

    def get_thumbnail(self, size: tuple[int, int]) -> Image.Image:
        """Get a thumbnail of the slide."""
        self._check_closed()
        cursor = self._require_cursor()

        # Try to get pre-stored thumbnail
        try:
            cursor.execute(
                "SELECT data FROM tbl_ext_info WHERE type = ?",
                (self.EXT_TYPE_THUMBNAIL,),
            )
            row = cursor.fetchone()
            if row and row["data"]:
                thumb = Image.open(io.BytesIO(row["data"]))
                thumb.thumbnail(size, Image.Resampling.LANCZOS)
                return thumb
        except Exception:
            pass

        # Fallback: read from lowest resolution level
        level = self.level_count - 1
        dims = self.level_dimensions[level]
        img = self.read_region((0, 0), level, dims)
        img.thumbnail(size, Image.Resampling.LANCZOS)
        return img

    def get_best_level_for_downsample(self, downsample: float) -> int:
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

    # ==================== V2.0 Tile Methods ====================

    def _get_tile_v2(self, layer: int, col: int, row: int) -> Image.Image | None:
        """Get a tile from v2.0 format (tbl_tileex_info).

        Args:
            layer: Pyramid layer (0, 1, 2, ...)
            col: Tile column
            row: Tile row

        Returns:
            PIL Image of the tile, or None if not found
        """
        cursor = self._require_cursor()
        cursor.execute(
            """
            SELECT data FROM tbl_tileex_info
            WHERE layer = ? AND col = ? AND row = ?
        """,
            (layer, col, row),
        )

        result = cursor.fetchone()
        if result and result["data"]:
            try:
                return Image.open(io.BytesIO(result["data"]))
            except Exception:
                pass
        return None

    # ==================== V1.0 Tile Methods ====================

    def _get_tile_layer0_v1(
        self, img_id: int, sub_col: int, sub_row: int
    ) -> Image.Image | None:
        """Get a sub-tile from layer 0 (v1.0 format).

        Args:
            img_id: Image block ID from tbl_img_info
            sub_col: Sub-tile column within the block (0-3)
            sub_row: Sub-tile row within the block (0-3)

        Returns:
            PIL Image of the sub-tile, or None if not found
        """
        cursor = self._require_cursor()
        cursor.execute(
            """
            SELECT data FROM tbl_tile_info
            WHERE layer = 0 AND id = ? AND col = ? AND row = ?
        """,
            (img_id, sub_col, sub_row),
        )

        row = cursor.fetchone()
        if row and row["data"]:
            try:
                return Image.open(io.BytesIO(row["data"]))
            except Exception:
                pass
        return None

    def _get_tile_layer1_v1(self, img_id: int) -> Image.Image | None:
        """Get a tile from layer 1 (v1.0, 4x downsample).

        Args:
            img_id: Image block ID from tbl_img_info

        Returns:
            PIL Image of the tile, or None if not found
        """
        cursor = self._require_cursor()
        cursor.execute(
            """
            SELECT data FROM tbl_tile_info
            WHERE layer = 1 AND id = ?
        """,
            (img_id,),
        )

        row = cursor.fetchone()
        if row and row["data"]:
            try:
                return Image.open(io.BytesIO(row["data"]))
            except Exception:
                pass
        return None

    def _get_tile_layer2_v1(self, x: int, y: int) -> Image.Image | None:
        """Get a tile from layer 2 (v1.0, shrink layer, 16x downsample).

        Args:
            x: X coordinate in layer 2 coordinates
            y: Y coordinate in layer 2 coordinates

        Returns:
            PIL Image of the tile, or None if not found
        """
        cursor = self._require_cursor()
        cursor.execute(
            """
            SELECT data FROM tbl_shrink_info
            WHERE layerNo = 2 AND x = ? AND y = ?
        """,
            (x, y),
        )

        row = cursor.fetchone()
        if row and row["data"]:
            try:
                return Image.open(io.BytesIO(row["data"]))
            except Exception:
                pass
        return None

    def _find_img_id_for_position(self, grid_col: int, grid_row: int) -> int | None:
        """Find the image block ID for a given grid position (v1.0 only).

        Args:
            grid_col: Column in the image grid
            grid_row: Row in the image grid

        Returns:
            Image block ID, or None if not found
        """
        for img_id, info in self._img_index.items():
            if info["col"] == grid_col and info["row"] == grid_row:
                return img_id
        return None

    # ==================== Read Region ====================

    def read_region(
        self, location: tuple[int, int], level: int, size: tuple[int, int]
    ) -> Image.Image:
        """Read a region from the slide.

        Args:
            location: (x, y) tuple of top-left corner in level 0 coordinates
            level: pyramid level to read from
            size: (width, height) tuple of the region size at the specified level

        Returns:
            PIL Image of the requested region (RGBA)
        """
        self._check_closed()

        if level < 0 or level >= self.level_count:
            raise ValueError(f"Invalid level: {level}")

        req_x, req_y = location
        width, height = size
        downsample = int(self.level_downsamples[level])

        # Create output image
        result = Image.new("RGBA", (width, height), (255, 255, 255, 0))

        if self._is_v2:
            self._read_region_v2(result, req_x, req_y, width, height, level, downsample)
        else:
            # v1.0 format
            if level == 0:
                self._read_region_layer0_v1(result, req_x, req_y, width, height)
            elif level == 1:
                self._read_region_layer1_v1(
                    result, req_x, req_y, width, height, downsample
                )
            else:  # level == 2
                self._read_region_layer2_v1(
                    result, req_x, req_y, width, height, downsample
                )

        return result

    # ==================== V2.0 Read Region ====================

    def _read_region_v2(
        self,
        result: Image.Image,
        req_x: int,
        req_y: int,
        width: int,
        height: int,
        level: int,
        downsample: int,
    ):
        """Read region from v2.0 format using tbl_tileex_info."""
        tile_w = self._tile_width
        tile_h = self._tile_height

        # Tile coverage in level 0 coordinates
        tile_coverage_x = tile_w * downsample
        tile_coverage_y = tile_h * downsample

        # Calculate tile range we need
        start_col = req_x // tile_coverage_x
        start_row = req_y // tile_coverage_y
        end_col = (req_x + width * downsample - 1) // tile_coverage_x
        end_row = (req_y + height * downsample - 1) // tile_coverage_y

        for tile_row in range(start_row, end_row + 1):
            for tile_col in range(start_col, end_col + 1):
                # Get tile
                tile_img = self._get_tile_v2(level, tile_col, tile_row)
                if tile_img is None:
                    continue

                if tile_img.mode != "RGBA":
                    tile_img = tile_img.convert("RGBA")

                # Tile position in level 0 coordinates
                tile_x0 = tile_col * tile_coverage_x
                tile_y0 = tile_row * tile_coverage_y

                # Calculate intersection in level 0 coords
                inter_left = max(tile_x0, req_x)
                inter_top = max(tile_y0, req_y)
                inter_right = min(tile_x0 + tile_coverage_x, req_x + width * downsample)
                inter_bottom = min(
                    tile_y0 + tile_coverage_y, req_y + height * downsample
                )

                # Convert to tile-local coordinates
                crop_left = (inter_left - tile_x0) // downsample
                crop_top = (inter_top - tile_y0) // downsample
                crop_right = (inter_right - tile_x0) // downsample
                crop_bottom = (inter_bottom - tile_y0) // downsample

                # Clamp to actual tile size
                crop_right = min(crop_right, tile_img.width)
                crop_bottom = min(crop_bottom, tile_img.height)

                if crop_right <= crop_left or crop_bottom <= crop_top:
                    continue

                cropped = tile_img.crop((crop_left, crop_top, crop_right, crop_bottom))

                # Paste position in result
                paste_x = (inter_left - req_x) // downsample
                paste_y = (inter_top - req_y) // downsample
                result.paste(cropped, (paste_x, paste_y))

    # ==================== V1.0 Read Region ====================

    def _read_region_layer0_v1(
        self, result: Image.Image, req_x: int, req_y: int, width: int, height: int
    ):
        """Read region from layer 0 (v1.0, full resolution)."""
        # Calculate which image blocks and sub-tiles we need
        start_grid_col = req_x // self._block_width
        start_grid_row = req_y // self._block_height
        end_grid_col = (req_x + width - 1) // self._block_width
        end_grid_row = (req_y + height - 1) // self._block_height

        for grid_row in range(start_grid_row, end_grid_row + 1):
            for grid_col in range(start_grid_col, end_grid_col + 1):
                img_id = self._find_img_id_for_position(grid_col, grid_row)
                if img_id is None:
                    continue

                # Block top-left in level 0 coordinates
                block_x = grid_col * self._block_width
                block_y = grid_row * self._block_height

                # Process each sub-tile in this block
                for sub_row in range(self._sub_tiles_y):
                    for sub_col in range(self._sub_tiles_x):
                        # Sub-tile top-left in level 0 coordinates
                        tile_x = block_x + sub_col * self._sub_tile_width
                        tile_y = block_y + sub_row * self._sub_tile_height

                        # Check if this tile overlaps with our request
                        if (
                            tile_x + self._sub_tile_width <= req_x
                            or tile_x >= req_x + width
                            or tile_y + self._sub_tile_height <= req_y
                            or tile_y >= req_y + height
                        ):
                            continue

                        # Load the sub-tile
                        tile_img = self._get_tile_layer0_v1(img_id, sub_col, sub_row)
                        if tile_img is None:
                            continue

                        if tile_img.mode != "RGBA":
                            tile_img = tile_img.convert("RGBA")

                        # Calculate intersection
                        inter_left = max(tile_x, req_x)
                        inter_top = max(tile_y, req_y)
                        inter_right = min(tile_x + self._sub_tile_width, req_x + width)
                        inter_bottom = min(
                            tile_y + self._sub_tile_height, req_y + height
                        )

                        # Crop from tile
                        crop_left = inter_left - tile_x
                        crop_top = inter_top - tile_y
                        crop_right = inter_right - tile_x
                        crop_bottom = inter_bottom - tile_y
                        cropped = tile_img.crop(
                            (crop_left, crop_top, crop_right, crop_bottom)
                        )

                        # Paste to result
                        paste_x = inter_left - req_x
                        paste_y = inter_top - req_y
                        result.paste(cropped, (paste_x, paste_y))

    def _read_region_layer1_v1(
        self,
        result: Image.Image,
        req_x: int,
        req_y: int,
        width: int,
        height: int,
        downsample: int,
    ):
        """Read region from layer 1 (v1.0, 4x downsample)."""
        # Layer 1 tiles are 612x512, covering block size in level 0
        tile_coverage_x = self._block_width  # Area covered in level 0 coords
        tile_coverage_y = self._block_height

        # Calculate grid range
        start_grid_col = req_x // tile_coverage_x
        start_grid_row = req_y // tile_coverage_y
        end_grid_col = (req_x + width * downsample - 1) // tile_coverage_x
        end_grid_row = (req_y + height * downsample - 1) // tile_coverage_y

        for grid_row in range(start_grid_row, end_grid_row + 1):
            for grid_col in range(start_grid_col, end_grid_col + 1):
                img_id = self._find_img_id_for_position(grid_col, grid_row)
                if img_id is None:
                    continue

                # Block top-left in level 0 coordinates
                block_x = grid_col * tile_coverage_x
                block_y = grid_row * tile_coverage_y

                # Load the tile
                tile_img = self._get_tile_layer1_v1(img_id)
                if tile_img is None:
                    continue

                if tile_img.mode != "RGBA":
                    tile_img = tile_img.convert("RGBA")

                # Calculate intersection in level 0 coords
                inter_left = max(block_x, req_x)
                inter_top = max(block_y, req_y)
                inter_right = min(block_x + tile_coverage_x, req_x + width * downsample)
                inter_bottom = min(
                    block_y + tile_coverage_y, req_y + height * downsample
                )

                # Convert to tile-local coordinates (divide by downsample)
                crop_left = (inter_left - block_x) // downsample
                crop_top = (inter_top - block_y) // downsample
                crop_right = (inter_right - block_x) // downsample
                crop_bottom = (inter_bottom - block_y) // downsample

                # Clamp to tile size
                crop_right = min(crop_right, tile_img.width)
                crop_bottom = min(crop_bottom, tile_img.height)

                if crop_right <= crop_left or crop_bottom <= crop_top:
                    continue

                cropped = tile_img.crop((crop_left, crop_top, crop_right, crop_bottom))

                # Paste position in result
                paste_x = (inter_left - req_x) // downsample
                paste_y = (inter_top - req_y) // downsample
                result.paste(cropped, (paste_x, paste_y))

    def _read_region_layer2_v1(
        self,
        result: Image.Image,
        req_x: int,
        req_y: int,
        width: int,
        height: int,
        downsample: int,
    ):
        """Read region from layer 2 (v1.0, shrink layer, 16x downsample)."""
        # Get all shrink tiles
        cursor = self._require_cursor()
        cursor.execute("SELECT x, y, data FROM tbl_shrink_info WHERE layerNo = 2")

        for row in cursor.fetchall():
            tile_x_level0 = row["x"]  # These are level 0 coordinates
            tile_y_level0 = row["y"]
            tile_data = row["data"]

            if not tile_data:
                continue

            try:
                tile_img = Image.open(io.BytesIO(tile_data))
            except Exception:
                continue

            # Tile coverage in level 0 coords
            tile_coverage_x = tile_img.width * downsample
            tile_coverage_y = tile_img.height * downsample

            # Check overlap
            if (
                tile_x_level0 + tile_coverage_x <= req_x
                or tile_x_level0 >= req_x + width * downsample
                or tile_y_level0 + tile_coverage_y <= req_y
                or tile_y_level0 >= req_y + height * downsample
            ):
                continue

            if tile_img.mode != "RGBA":
                tile_img = tile_img.convert("RGBA")

            # Calculate intersection in level 0 coords
            inter_left = max(tile_x_level0, req_x)
            inter_top = max(tile_y_level0, req_y)
            inter_right = min(
                tile_x_level0 + tile_coverage_x, req_x + width * downsample
            )
            inter_bottom = min(
                tile_y_level0 + tile_coverage_y, req_y + height * downsample
            )

            # Convert to tile-local coordinates
            crop_left = (inter_left - tile_x_level0) // downsample
            crop_top = (inter_top - tile_y_level0) // downsample
            crop_right = (inter_right - tile_x_level0) // downsample
            crop_bottom = (inter_bottom - tile_y_level0) // downsample

            # Clamp to tile size
            crop_right = min(crop_right, tile_img.width)
            crop_bottom = min(crop_bottom, tile_img.height)

            if crop_right <= crop_left or crop_bottom <= crop_top:
                continue

            cropped = tile_img.crop((crop_left, crop_top, crop_right, crop_bottom))

            # Paste position in result
            paste_x = (inter_left - req_x) // downsample
            paste_y = (inter_top - req_y) // downsample
            result.paste(cropped, (paste_x, paste_y))

    def close(self):
        """Close the slide and free resources."""
        if self._closed:
            return

        try:
            cursor = self._cursor
            if cursor is not None:
                cursor.close()
                self._cursor = None
            conn = self._conn
            if conn is not None:
                conn.close()
                self._conn = None
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
        return f"IblSlide({self._filename!r})"
