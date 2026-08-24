"""
TMAP file format reader for TMAP06 and TMAP07.

"""

import io
import os
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, BinaryIO

from PIL import Image
from openslide import AbstractSlide

from .color_correction import ColorCorrection


# Image types for associated images
class _ImageType:
    THUMBNAIL = 0
    NAVIGATE = 1
    MACRO = 2
    LABEL = 3
    PREVIEW = 4
    EXTERN = 5
    WHOLE = 6
    RESERVED = 7
    MACRO_LABEL = (
        8  # TMAP06: combined macro+label image (label=left 1/3, macro=right 2/3)
    )


@dataclass
class _TileInfo:
    """Information about a single tile"""

    offset: int
    length: int
    layer_no: int = 0
    col: int = 0
    row: int = 0


@dataclass
class _LayerInfoV6:
    """TMAP06 LayerInfo structure"""

    file_id: int = 0
    layer: int = 0
    top_dx: int = 0
    top_dy: int = 0
    left_dx: int = 0
    left_dy: int = 0
    n_img_col: int = 0
    n_img_row: int = 0
    n_x: int = 0
    n_y: int = 0
    tiles: List[_TileInfo] = field(default_factory=list)


@dataclass
class _LayerInfoV7:
    """TMAP07 LayerInfo structure"""

    layer_id: int = 0
    scale: float = 1.0
    width: int = 0
    height: int = 0
    tile_row: int = 0
    tile_col: int = 0
    offset: int = 0
    tile_start: int = 0


@dataclass
class _ImageInfo:
    """Associated image info"""

    width: int = 0
    height: int = 0
    depth: int = 0
    image_type: int = 0
    offset: int = 0
    length: int = 0


@dataclass
class _ShrinkTileInfo:
    """TMAP06 ShrinkTileInfo for low-resolution tiles"""

    file_id: int = 0
    layer_no: int = 0
    n_x: int = 0
    n_y: int = 0
    offset: int = 0
    length: int = 0


@dataclass
class _TmapHeader:
    """TMAP file header information"""

    version: int
    focus_nums: int = 1
    scan_scale: int = 40
    pixel_size: float = 0.0001
    width: int = 0
    height: int = 0
    tile_width: int = 256
    tile_height: int = 256
    image_format: int = 0
    jpeg_quality: int = 70
    bkg_color: int = 244
    layer_num: int = 0
    ratio_step: int = 2
    img_col: int = 0
    img_row: int = 0
    img_width: int = 0
    img_height: int = 0
    shrink_tile_num: int = 0
    image_num: int = 0
    ext_offset: int = 0
    tile_num: int = 0
    file_num: int = 0  # Number of auxiliary data files (DT1, DT2, etc.)


class TmapSlide(AbstractSlide):
    """TMAP slide reader compatible with OpenSlide API."""

    TILE_SIZE = 256

    def __init__(self, filename):
        AbstractSlide.__init__(self)
        self._filename = filename
        self._file: Optional[BinaryIO] = None
        self._data_files: Dict[
            int, BinaryIO
        ] = {}  # file_id -> file handle for multi-file support
        self._header = _TmapHeader(version=0)
        self._layer_infos_v6: List[_LayerInfoV6] = []
        self._layer_infos_v7: List[_LayerInfoV7] = []
        self._shrink_tile_infos: List[_ShrinkTileInfo] = []
        self._image_infos: List[_ImageInfo] = []
        self._levels: List[Tuple[int, int]] = []
        self._color_correction = ColorCorrection()
        self._open()

    def _open(self):
        """Open and parse the TMAP file."""
        if not os.path.exists(self._filename):
            raise FileNotFoundError(f"TMAP file not found: {self._filename}")
        self._file = open(self._filename, "rb")
        magic = self._require_file().read(6).decode("ascii", errors="ignore")
        if magic == "TMAP07":
            self._header.version = 7
            self._parse_tmap07()
        elif magic == "TMAP06":
            self._header.version = 6
            self._parse_tmap06()
        else:
            self._require_file().close()
            self._file = None
            raise ValueError(f"Unsupported TMAP format: {magic}")

    def _require_file(self) -> BinaryIO:
        if self._file is None:
            raise RuntimeError("TMAP file is not open")
        return self._file

    def _read_byte(self) -> int:
        return struct.unpack("B", self._require_file().read(1))[0]

    def _read_short(self) -> int:
        return struct.unpack("<h", self._require_file().read(2))[0]

    def _read_int(self) -> int:
        return struct.unpack("<i", self._require_file().read(4))[0]

    def _read_long(self) -> int:
        return struct.unpack("<q", self._require_file().read(8))[0]

    def _read_float(self) -> float:
        return struct.unpack("<f", self._require_file().read(4))[0]

    # ========== TMAP06 Parsing ==========

    def _parse_tmap06(self):
        """Parse TMAP06 format."""
        f = self._require_file()
        f.seek(6)
        self._header.focus_nums = self._read_byte()
        self._header.image_format = self._read_byte()
        self._header.file_num = (
            self._read_byte()
        )  # Number of data files (0 or 1 = single file)
        self._header.layer_num = self._read_byte()
        img_color = self._read_byte()
        if img_color == 0:
            img_color = 24
        self._read_byte()  # check_sum
        self._header.ratio_step = self._read_byte()
        if self._header.ratio_step < 2 or self._header.ratio_step > 4:
            self._header.ratio_step = 2
        self._read_byte()  # max_lay_num
        self._read_byte()  # slide_type
        self._header.bkg_color = self._read_byte()
        self._header.pixel_size = self._read_float()
        if self._header.pixel_size < 1e-8:
            self._header.pixel_size = 1e-4
        self._header.image_num = self._read_int()
        self._header.scan_scale = self._read_short()
        self._header.img_col = self._read_short()
        self._header.img_row = self._read_short()
        self._header.img_width = self._read_short()
        self._header.img_height = self._read_short()
        self._header.tile_width = self._read_short()
        self._header.tile_height = self._read_short()
        self._read_short()  # air_img_width
        self._read_short()  # air_img_height
        self._read_byte()  # version_minor
        save_scale = self._read_byte()
        if save_scale <= 0 or save_scale >= 100:
            save_scale = self._header.scan_scale
        self._header.shrink_tile_num = self._read_int()
        self._header.width = self._read_int()
        self._header.height = self._read_int()
        self._read_int()  # air_img_offset
        self._parse_tmap06_ext_info()
        self._parse_tmap06_layer_infos()
        self._parse_tmap06_shrink_tile_infos()
        self._build_tmap06_levels()
        self._open_data_files()

    def _parse_tmap06_ext_info(self):
        """Parse TMAP06 ExtInfo structure.

        ExtInfoType enum values from SDK:
        0 = extTypeNone, 1 = extMacroImage, 2 = extThumbImage,
        3 = extCodeId, 4 = extSlideInfo, 5 = extSystemInfo,
        6 = extRuntimeInfo, 7 = extMarkInfo, 8 = extTotalType
        """
        # Map ExtInfoType ordinal to our ImageType
        # Note: extMacroImage (1) contains combined macro+label, not just macro
        ext_to_img_type = {
            1: _ImageType.MACRO_LABEL,  # Combined macro+label image
            2: _ImageType.THUMBNAIL,
        }
        self._read_int()  # lMaxExtDataLen
        self._read_int()  # lSumExtDataLen
        self._read_int()  # lTMAPDataEndPos
        ext_types = [self._read_int() for _ in range(8)]
        ext_offsets = [self._read_int() for _ in range(8)]
        ext_lengths = [self._read_int() for _ in range(8)]
        self._require_file().read(24)  # reserved
        for i in range(8):
            if (
                ext_types[i] in ext_to_img_type
                and ext_offsets[i] > 0
                and ext_lengths[i] > 0
            ):
                info = _ImageInfo()
                info.image_type = ext_to_img_type[ext_types[i]]
                info.offset = ext_offsets[i]
                info.length = ext_lengths[i]
                self._image_infos.append(info)

    def _parse_tmap06_layer_infos(self):
        """Parse TMAP06 LayerInfo structures."""
        for _ in range(self._header.image_num):
            layer = _LayerInfoV6()
            layer.file_id = self._read_byte()
            layer.layer = self._read_byte()
            self._require_file().read(2)
            layer.top_dx = self._read_byte()
            layer.top_dy = self._read_byte()
            layer.left_dx = self._read_byte()
            layer.left_dy = self._read_byte()
            layer.n_img_col = self._read_short()
            layer.n_img_row = self._read_short()
            layer.n_x = self._read_int()
            layer.n_y = self._read_int()
            for _ in range(24):
                tile = _TileInfo(offset=0, length=0)
                tile.layer_no = self._read_byte()
                tile.col = self._read_byte()
                tile.row = self._read_byte()
                self._require_file().read(1)
                tile.offset = self._read_int()
                tile.length = self._read_int()
                layer.tiles.append(tile)
            self._layer_infos_v6.append(layer)

    def _parse_tmap06_shrink_tile_infos(self):
        """Parse TMAP06 ShrinkTileInfo structures."""
        for _ in range(self._header.shrink_tile_num):
            info = _ShrinkTileInfo()
            info.file_id = self._read_byte()
            info.layer_no = self._read_byte()
            self._require_file().read(2)
            info.n_x = self._read_int()
            info.n_y = self._read_int()
            info.offset = self._read_int()
            info.length = self._read_int()
            self._shrink_tile_infos.append(info)

    def _build_tmap06_levels(self):
        """Build level dimensions for TMAP06."""
        w, h = self._header.width, self._header.height
        scale = self._header.scan_scale
        ratio_step = self._header.ratio_step
        while scale >= 1 and w > 0 and h > 0:
            self._levels.append((w, h))
            w = (w + ratio_step - 1) // ratio_step
            h = (h + ratio_step - 1) // ratio_step
            scale = scale // ratio_step
        # Build LayerInfo index by (n_img_col, n_img_row)
        self._layer_info_index = {}
        for layer in self._layer_infos_v6:
            if layer.n_img_col >= 0 and layer.n_img_row >= 0:
                key = (layer.n_img_col, layer.n_img_row)
                self._layer_info_index[key] = layer
        # Build ShrinkTileInfo index by (layer_no, n_x, n_y)
        self._shrink_tile_index = {}
        for st in self._shrink_tile_infos:
            key = (st.layer_no, st.n_x, st.n_y)
            self._shrink_tile_index[key] = st

    def _open_data_files(self):
        """Open auxiliary data files (DT1, DT2, etc.) for multi-file TMAP06."""
        # Check if any LayerInfo or ShrinkTileInfo references file_id > 0
        max_file_id = 0
        for layer in self._layer_infos_v6:
            if layer.file_id > max_file_id:
                max_file_id = layer.file_id
        for st in self._shrink_tile_infos:
            if st.file_id > max_file_id:
                max_file_id = st.file_id

        if max_file_id == 0:
            return  # Single file mode

        # Open auxiliary files
        base_path = self._filename.rsplit(".", 1)[0]
        for file_id in range(1, max_file_id + 1):
            dt_path = f"{base_path}.DT{file_id}"
            if os.path.exists(dt_path):
                self._data_files[file_id] = open(dt_path, "rb")

    def _get_file_handle(self, file_id: int) -> Optional[BinaryIO]:
        """Get file handle for the given file_id.

        file_id 0 = main TMAP file
        file_id 1+ = auxiliary DT1, DT2, etc. files
        """
        if file_id == 0:
            return self._file
        return self._data_files.get(file_id)

    # ========== TMAP07 Parsing ==========

    def _parse_tmap07(self):
        """Parse TMAP07 format.

        Based on decompiled SDK analysis:
        - Header: 0 to ~304 bytes
        - ImageInfo (8 * 32): 304 to 560
        - LayerInfo (16 * 32): 560 to 1072
        """
        f = self._require_file()
        f.seek(8)
        self._header.image_format = self._read_byte()
        self._header.jpeg_quality = self._read_byte()
        self._header.focus_nums = self._read_byte()
        if self._header.focus_nums == 0:
            self._header.focus_nums = 1
        self._header.scan_scale = self._read_byte()
        self._header.bkg_color = self._read_byte()
        f.seek(0x10)
        self._header.pixel_size = self._read_float()
        self._header.image_num = self._read_int()
        self._header.layer_num = self._read_int()
        self._header.tile_num = self._read_int()
        self._header.ext_offset = self._read_long()

        # Skip to position 304 (after header) for ImageInfo
        f.seek(304)
        self._parse_tmap07_image_infos()

        # LayerInfo starts at position 560
        f.seek(560)
        self._parse_tmap07_layer_infos()
        self._build_tmap07_levels()

    def _parse_tmap07_image_infos(self):
        """Parse TMAP07 ImageInfo structures.

        ImageInfo structure (32 bytes):
        - width: 4 bytes (int)
        - height: 4 bytes (int)
        - depth: 4 bytes (int)
        - imageType: 4 bytes (int)
        - offset: 8 bytes (long)
        - length: 4 bytes (int)
        - padding: 4 bytes

        Note: SDK reads in reverse order (i=7 to i=0)
        """
        assoc_images_raw = []
        for i in range(7, -1, -1):  # Reverse order like SDK
            width = self._read_int()
            height = self._read_int()
            depth = self._read_int()
            img_type = self._read_int()
            offset = self._read_long()
            length = self._read_int()
            self._read_int()  # padding
            if width > 0 and height > 0:
                assoc_images_raw.append(
                    {
                        "width": width,
                        "height": height,
                        "depth": depth,
                        "image_type": img_type,
                        "offset": offset,
                        "length": length,
                    }
                )
        for img in assoc_images_raw:
            info = _ImageInfo()
            info.width, info.height, info.depth = (
                img["width"],
                img["height"],
                img["depth"],
            )
            info.image_type, info.offset, info.length = (
                img["image_type"],
                img["offset"],
                img["length"],
            )
            self._image_infos.append(info)

    def _parse_tmap07_layer_infos(self):
        """Parse TMAP07 LayerInfo structures.

        LayerInfo structure (32 bytes):
        - nLayerID: 4 bytes (int)
        - scale: 4 bytes (float)
        - nWidth: 4 bytes (int)
        - nHeight: 4 bytes (int)
        - nTileRow: 4 bytes (int)
        - nTileCol: 4 bytes (int)
        - nOffset: 4 bytes (int) - tile table start position
        - nTileStart: 4 bytes (int)
        """
        for _ in range(16):  # SDK creates 16 LayerInfo entries
            layer = _LayerInfoV7()
            layer.layer_id = self._read_int()
            layer.scale = self._read_float()
            layer.width = self._read_int()
            layer.height = self._read_int()
            layer.tile_row = self._read_int()
            layer.tile_col = self._read_int()
            layer.offset = self._read_int()  # nOffset - tile table position
            layer.tile_start = self._read_int()
            if layer.width > 0 and layer.height > 0:
                self._layer_infos_v7.append(layer)
        if self._layer_infos_v7:
            self._header.width = self._layer_infos_v7[0].width
            self._header.height = self._layer_infos_v7[0].height

    def _build_tmap07_levels(self):
        """Build level dimensions for TMAP07."""
        w, h = self._header.width, self._header.height
        if w <= 0 or h <= 0:
            return
        scale = self._header.scan_scale
        level_count = 1
        while scale > 2:
            scale = scale / 2
            level_count += 1
        for _ in range(level_count):
            self._levels.append((w, h))
            w = w // 2
            h = h // 2

    # ========== Public API ==========

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, self._filename)

    @classmethod
    def detect_format(cls, filename):
        """Detect if the file is a valid TMAP format."""
        try:
            with open(filename, "rb") as f:
                magic = f.read(6).decode("ascii", errors="ignore")
                if magic in ("TMAP06", "TMAP07"):
                    return "tmap"
            return None
        except Exception:
            return None

    def close(self):
        """Close the slide and all associated data files."""
        if self._file:
            self._file.close()
            self._file = None
        for fh in self._data_files.values():
            try:
                fh.close()
            except Exception:
                pass
        self._data_files.clear()

    def __del__(self):
        self.close()

    @property
    def dimensions(self) -> Tuple[int, int]:
        """Get slide dimensions (width, height) at level 0."""
        return (self._header.width, self._header.height)

    @property
    def level_count(self) -> int:
        """Get the number of pyramid levels."""
        return len(self._levels)

    @property
    def level_dimensions(self) -> Tuple[Tuple[int, int], ...]:
        """Get dimensions for each pyramid level."""
        return tuple(self._levels)

    @property
    def level_downsamples(self) -> Tuple[float, ...]:
        """Get downsample factor for each level."""
        if not self._levels:
            return (1.0,)
        base_width = self._levels[0][0]
        return tuple(base_width / w if w > 0 else 1.0 for w, _ in self._levels)

    @property
    def properties(self) -> Dict[str, str]:
        """Get slide properties as a dictionary."""
        mpp = self._header.pixel_size * 1000
        return {
            "openslide.vendor": "UNIC",
            "tmap.version": str(self._header.version),
            "tmap.scan_scale": str(self._header.scan_scale),
            "tmap.pixel_size": str(self._header.pixel_size),
            "tmap.width": str(self._header.width),
            "tmap.height": str(self._header.height),
            "openslide.mpp-x": str(mpp),
            "openslide.mpp-y": str(mpp),
            "openslide.objective-power": str(self._header.scan_scale),
            "openslide.level-count": str(self.level_count),
        }

    @property
    def mpp(self) -> float:
        """Microns per pixel at level 0."""
        return self._header.pixel_size * 1000

    def _get_image_info_by_name(self, name: str) -> Optional[_ImageInfo]:
        """Get _ImageInfo by name."""
        type_map = {
            "thumbnail": _ImageType.THUMBNAIL,
            "navigate": _ImageType.NAVIGATE,
            "macro": _ImageType.MACRO,
            "label": _ImageType.LABEL,
            "preview": _ImageType.PREVIEW,
            "extern": _ImageType.EXTERN,
        }
        if name not in type_map:
            return None
        target_type = type_map[name]
        for info in self._image_infos:
            if info.image_type == target_type and info.offset > 0:
                return info
        # For TMAP06: label and macro come from MACRO_LABEL
        if target_type in (_ImageType.LABEL, _ImageType.MACRO):
            for info in self._image_infos:
                if info.image_type == _ImageType.MACRO_LABEL and info.offset > 0:
                    return info
        return None

    @property
    def associated_images(self) -> Dict[str, Image.Image]:
        """Get associated images as a dict-like object.

        Returns a dictionary where keys are image names and values are PIL Images.
        """
        result: Dict[str, Image.Image] = {}
        for name in self.associated_image_names:
            img = self.get_associated_image(name)
            if img is not None:
                result[name] = img
        return result

    @property
    def associated_image_names(self) -> List[str]:
        """Get list of available associated image names."""
        type_names = {
            _ImageType.THUMBNAIL: "thumbnail",
            _ImageType.NAVIGATE: "navigate",
            _ImageType.MACRO: "macro",
            _ImageType.LABEL: "label",
            _ImageType.PREVIEW: "preview",
            _ImageType.EXTERN: "extern",
        }
        result: List[str] = []
        for info in self._image_infos:
            if info.image_type in type_names and info.offset > 0:
                result.append(type_names[info.image_type])
            # MACRO_LABEL provides both 'label' and 'macro'
            elif info.image_type == _ImageType.MACRO_LABEL and info.offset > 0:
                result.append("label")
                result.append("macro")
        return result

    def get_best_level_for_downsample(self, downsample: float) -> int:
        """Find the best level for a given downsample factor."""
        downsamples = self.level_downsamples
        for i, ds in enumerate(downsamples):
            if ds >= downsample:
                return max(0, i - 1) if i > 0 else 0
        return len(downsamples) - 1

    def get_associated_image(self, name: str) -> Optional[Image.Image]:
        """Get an associated image by name."""
        info = self._get_image_info_by_name(name)
        if info is None or info.offset <= 0 or info.length <= 0:
            return None
        file_handle = self._require_file()
        file_handle.seek(info.offset)
        data = file_handle.read(info.length)

        # Find JPEG data
        img = None
        if data[:2] == b"\xff\xd8":
            try:
                img = Image.open(io.BytesIO(data))
            except Exception:
                pass
        if img is None:
            jpeg_start = data.find(b"\xff\xd8\xff")
            if jpeg_start >= 0:
                try:
                    img = Image.open(io.BytesIO(data[jpeg_start:]))
                except Exception:
                    pass

        if img is None:
            return None

        # For TMAP06 MACRO_LABEL: crop to get label or macro
        # Label = left 1/3, Macro = right 2/3
        if info.image_type == _ImageType.MACRO_LABEL:
            w, h = img.size
            label_w = w // 3
            if name == "label":
                img = img.crop((0, 0, label_w, h))
            elif name == "macro":
                img = img.crop((label_w, 0, w, h))
            # else: return full MACRO_LABEL image

        return img

    def get_thumbnail(self, size: Optional[Tuple[int, int]] = None) -> Image.Image:
        """Get a thumbnail image."""
        thumb = self.get_associated_image("thumbnail")
        if size is None:
            size = (256, 256)
        if thumb is not None:
            thumb.thumbnail(size, Image.Resampling.LANCZOS)
            return thumb
        if self._levels:
            lowest_level = len(self._levels) - 1
            level_dims = self._levels[lowest_level]
            region = self.read_region((0, 0), lowest_level, level_dims)
            region.thumbnail(size, Image.Resampling.LANCZOS)
            return region
        return self._get_blank_tile(*size)

    def _get_blank_tile(self, width: int = 256, height: int = 256) -> Image.Image:
        """Return a blank tile with background color."""
        return Image.new("RGB", (width, height), color=(self._header.bkg_color,) * 3)

    def _decode_tile(self, tile_data: bytes) -> Optional[Image.Image]:
        """Decode compressed tile data to PIL Image."""
        if not tile_data:
            return None
        try:
            return Image.open(io.BytesIO(tile_data))
        except Exception:
            return None

    def get_tile_v7(
        self, layer_idx: int, col: int, row: int, focus_layer: int = 0
    ) -> Optional[Image.Image]:
        """Get a tile for TMAP07.

        Based on decompiled SDK:
        - layerInfo.nOffset is the tile table start position (file offset)
        - Each tile entry is 40 bytes
        - Tile structure: nLayerID(4), nFocusID(4), nX(4), nY(4), nWidth(4), nHeight(4), lOffset(8), nLength(4), padding(4)
        """
        if (
            self._header.version != 7
            or layer_idx < 0
            or layer_idx >= len(self._layer_infos_v7)
        ):
            return None
        layer = self._layer_infos_v7[layer_idx]
        if col < 0 or col >= layer.tile_col or row < 0 or row >= layer.tile_row:
            return None

        # Calculate focus offset for multi-focus support
        focus_num = (
            focus_layer if focus_layer >= 0 else self._header.focus_nums + focus_layer
        )
        focus_offset = focus_num * layer.tile_col * layer.tile_row * 40

        # Tile table position: layer.offset + (row * tile_col + col) * 40 + focus_offset
        tile_table_offset = (
            layer.offset + (row * layer.tile_col + col) * 40 + focus_offset
        )

        file_handle = self._require_file()
        file_handle.seek(tile_table_offset)
        # Read tile info (40 bytes)
        # Skip: nLayerID(4), nFocusID(4), nX(4), nY(4), nWidth(4), nHeight(4)
        file_handle.read(24)  # Skip first 24 bytes
        offset = self._read_long()  # lOffset: 8 bytes
        length = self._read_int()  # nLength: 4 bytes
        # Remaining 4 bytes are padding

        if offset > 0 and length > 0:
            file_handle.seek(offset)
            return self._decode_tile(file_handle.read(length))
        return None

    def _get_tmap06_layer_params(self, level: int) -> Tuple[int, int, int, int]:
        """Get layer parameters for TMAP06.

        Returns:
            (tile_layer_no, tile_start_idx, tile_end_idx, scale_factor)
        """
        ratio_step = self._header.ratio_step
        scan_scale = self._header.scan_scale

        # Calculate scale for this level
        level_scale = 1
        for _ in range(level):
            level_scale *= ratio_step

        if ratio_step == 2:
            # For ratio_step=2: 16 tiles (4x4) at layer 0, 4 tiles (2x2) at layer 1, 1 tile at layer 2
            if level_scale <= 1:
                return (0, 0, 16, 1)
            elif level_scale <= 2:
                return (1, 16, 20, 2)
            elif level_scale <= 4:
                return (2, 20, 21, 4)
            else:
                return (2, 20, 21, level_scale)
        elif ratio_step == 4:
            # For ratio_step=4: 16 tiles (4x4) at layer 0, 1 tile at layer 1
            if level_scale <= 1:
                return (0, 0, 16, 1)
            elif level_scale <= 4:
                return (1, 16, 17, 4)
            else:
                return (2, 0, 0, level_scale)  # Use ShrinkTileInfo
        else:
            return (0, 0, 16, 1)

    def _get_tile_from_layer_info(
        self, layer_info: _LayerInfoV6, tile_layer: int, tile_col: int, tile_row: int
    ) -> Optional[Image.Image]:
        """Get a specific tile from LayerInfo."""
        for tile in layer_info.tiles:
            if (
                tile.layer_no == tile_layer
                and tile.col == tile_col
                and tile.row == tile_row
                and tile.offset > 0
                and tile.length > 0
            ):
                fh = self._get_file_handle(layer_info.file_id)
                if fh is None:
                    return None
                fh.seek(tile.offset)
                return self._decode_tile(fh.read(tile.length))
        return None

    def _get_shrink_tile(self, layer_no: int, x: int, y: int) -> Optional[Image.Image]:
        """Get a tile from ShrinkTileInfo."""
        # Find the shrink tile that covers position (x, y) at given layer
        tile_w = self._header.tile_width
        tile_h = self._header.tile_height

        # Calculate step size for this layer
        ratio_step = self._header.ratio_step
        scale = ratio_step**layer_no
        step_x = tile_w * scale * 4  # Each shrink tile covers 4x4 area at its scale
        step_y = tile_h * scale * 4

        # Find the grid position
        grid_x = (x // step_x) * step_x
        grid_y = (y // step_y) * step_y

        key = (layer_no, grid_x, grid_y)
        if key in self._shrink_tile_index:
            st = self._shrink_tile_index[key]
            if st.offset > 0 and st.length > 0:
                fh = self._get_file_handle(st.file_id)
                if fh is None:
                    return None
                fh.seek(st.offset)
                return self._decode_tile(fh.read(st.length))
        return None

    def get_tile_v6(
        self, layer_idx: int, n_x: int, n_y: int, col: int, row: int
    ) -> Optional[Image.Image]:
        """Get a tile for TMAP06.

        This is the legacy API, kept for compatibility.
        """
        if self._header.version != 6:
            return None
        key = (n_x, n_y)
        if key in self._layer_info_index:
            layer = self._layer_info_index[key]
            return self._get_tile_from_layer_info(layer, layer_idx, col, row)
        return None

    def apply_color_correction(self, apply: bool, style: str = "Real"):
        """Enable or disable color correction.

        Args:
            apply: Whether to enable color correction
            style: Color correction style ('Real')
        """
        if style != self._color_correction.style:
            self._color_correction.set_style(style)
        self._color_correction.enabled = apply

    def get_color_correction_info(self) -> Dict[str, object]:
        """Get color correction parameters info.

        Returns:
            dict with color correction status and parameters
        """
        return self._color_correction.get_info()

    def read_region(
        self, location: Tuple[int, int], level: int, size: Tuple[int, int]
    ) -> Image.Image:
        """Read a region from the slide."""
        if self._header.version == 7:
            img = self._read_region_v7(location, level, size)
        else:
            img = self._read_region_v6(location, level, size)

        # Apply color correction if enabled
        if self._color_correction.enabled:
            img = self._color_correction.apply(img)

        if img.mode != "RGBA":
            img = img.convert("RGBA")
        return img

    def _read_region_v7(
        self, location: Tuple[int, int], level: int, size: Tuple[int, int]
    ) -> Image.Image:
        """Read region for TMAP07."""
        if level < 0 or level >= len(self._layer_infos_v7):
            return self._get_blank_tile(size[0], size[1])
        layer = self._layer_infos_v7[level]
        downsample = (
            self.level_downsamples[level]
            if level < len(self.level_downsamples)
            else 1.0
        )
        x, y = int(location[0] / downsample), int(location[1] / downsample)
        width, height = size
        tile_size = self.TILE_SIZE
        start_col, end_col = x // tile_size, (x + width - 1) // tile_size + 1
        start_row, end_row = y // tile_size, (y + height - 1) // tile_size + 1
        result = self._get_blank_tile(width, height)
        for row in range(start_row, end_row):
            for col in range(start_col, end_col):
                tile = self.get_tile_v7(level, col, row) or self._get_blank_tile(
                    tile_size, tile_size
                )
                tile_x, tile_y = col * tile_size - x, row * tile_size - y
                src_x, src_y = max(0, -tile_x), max(0, -tile_y)
                dst_x, dst_y = max(0, tile_x), max(0, tile_y)
                paste_w = min(tile_size - src_x, width - dst_x)
                paste_h = min(tile_size - src_y, height - dst_y)
                if paste_w > 0 and paste_h > 0:
                    result.paste(
                        tile.crop((src_x, src_y, src_x + paste_w, src_y + paste_h)),
                        (dst_x, dst_y),
                    )
        return result

    def _read_region_v6(
        self, location: Tuple[int, int], level: int, size: Tuple[int, int]
    ) -> Image.Image:
        """Read region for TMAP06.

        TMAP06 uses a complex tiling system:
        - LayerInfo array: indexed by (n_img_col, n_img_row)
        - Each LayerInfo covers img_width x img_height area
        - Each LayerInfo contains 24 tiles at different zoom levels
        - ShrinkTileInfo for very low resolution levels
        """
        if level < 0 or level >= len(self._levels):
            return self._get_blank_tile(size[0], size[1])

        downsample = (
            self.level_downsamples[level]
            if level < len(self.level_downsamples)
            else 1.0
        )
        # location is in level 0 coordinates, convert to target level
        x = int(location[0] / downsample)
        y = int(location[1] / downsample)
        width, height = size

        result = self._get_blank_tile(width, height)

        # Get tile parameters for this level
        tile_layer, tile_start, tile_end, scale_factor = self._get_tmap06_layer_params(
            level
        )

        tile_w = self._header.tile_width or 512
        tile_h = self._header.tile_height or 512
        img_w = self._header.img_width
        img_h = self._header.img_height
        n_old_col = self._header.img_col
        n_old_row = self._header.img_row
        ratio_step = self._header.ratio_step

        # For high zoom levels, use ShrinkTileInfo
        if tile_end == 0 and self._shrink_tile_infos:
            return self._read_region_v6_shrink(
                location, level, size, x, y, width, height
            )

        # For tile_layer > 0, each tile covers the entire image block (img_w x img_h)
        # but the tile itself is tile_w x tile_h pixels
        if tile_layer == 0:
            # Level 0: 4x4 tiles, each covering tile_w x tile_h in level 0
            scaled_tile_w = tile_w
            scaled_tile_h = tile_h
        else:
            # Level 1+: 1 tile covers entire image block
            scaled_tile_w = img_w
            scaled_tile_h = img_h

        # Convert to level 0 coordinates for finding LayerInfo
        x0 = int(location[0])
        y0 = int(location[1])
        w0 = int(width * downsample)
        h0 = int(height * downsample)

        # Find which image blocks we need (in level 0 coordinates)
        avg_img_w = self._header.width // max(1, n_old_col)
        avg_img_h = self._header.height // max(1, n_old_row)

        start_img_col = max(0, x0 // avg_img_w - 1)
        end_img_col = min(n_old_col, (x0 + w0) // avg_img_w + 2)
        start_img_row = max(0, y0 // avg_img_h - 1)
        end_img_row = min(n_old_row, (y0 + h0) // avg_img_h + 2)

        for img_row in range(start_img_row, end_img_row):
            for img_col in range(start_img_col, end_img_col):
                key = (img_col, img_row)
                if key not in self._layer_info_index:
                    continue

                layer_info = self._layer_info_index[key]
                block_x0 = layer_info.n_x
                block_y0 = layer_info.n_y

                # Check if this block overlaps with our region (in level 0 coords)
                if (
                    block_x0 + img_w < x0
                    or block_x0 > x0 + w0
                    or block_y0 + img_h < y0
                    or block_y0 > y0 + h0
                ):
                    continue

                for tile in layer_info.tiles:
                    if tile.layer_no != tile_layer:
                        continue
                    if tile.offset <= 0 or tile.length <= 0:
                        continue

                    # Calculate tile position in level 0 coordinates
                    tile_x0_l0 = block_x0 + tile.col * scaled_tile_w
                    tile_y0_l0 = block_y0 + tile.row * scaled_tile_h

                    # Check if this tile overlaps with our region
                    if (
                        tile_x0_l0 + scaled_tile_w < x0
                        or tile_x0_l0 > x0 + w0
                        or tile_y0_l0 + scaled_tile_h < y0
                        or tile_y0_l0 > y0 + h0
                    ):
                        continue

                    # Read tile from appropriate file
                    fh = self._get_file_handle(layer_info.file_id)
                    if fh is None:
                        continue
                    fh.seek(tile.offset)
                    tile_img = self._decode_tile(fh.read(tile.length))
                    if tile_img is None:
                        continue

                    # For tile_layer > 0, the tile covers scaled_tile_w x scaled_tile_h
                    # but is stored as tile_w x tile_h pixels
                    # We need to calculate the mapping
                    if tile_layer == 0:
                        # Direct mapping: tile pixel coords = level 0 coords relative to tile
                        tile_x = tile_x0_l0 - x0
                        tile_y = tile_y0_l0 - y0

                        src_x = max(0, -tile_x)
                        src_y = max(0, -tile_y)
                        dst_x = max(0, tile_x)
                        dst_y = max(0, tile_y)
                        paste_w = min(tile_img.width - src_x, width - dst_x)
                        paste_h = min(tile_img.height - src_y, height - dst_y)

                        if paste_w > 0 and paste_h > 0:
                            crop_box = (src_x, src_y, src_x + paste_w, src_y + paste_h)
                            result.paste(tile_img.crop(crop_box), (dst_x, dst_y))
                    else:
                        # tile covers (tile_x0_l0, tile_y0_l0) to (tile_x0_l0 + scaled_tile_w, ...)
                        # in level 0. The tile image is tile_w x tile_h pixels.
                        # Scale factor from level 0 to tile pixels
                        scale_x = tile_img.width / scaled_tile_w
                        scale_y = tile_img.height / scaled_tile_h

                        # Calculate overlap region in level 0 coordinates
                        overlap_x0 = max(x0, tile_x0_l0)
                        overlap_y0 = max(y0, tile_y0_l0)
                        overlap_x1 = min(x0 + w0, tile_x0_l0 + scaled_tile_w)
                        overlap_y1 = min(y0 + h0, tile_y0_l0 + scaled_tile_h)

                        if overlap_x1 <= overlap_x0 or overlap_y1 <= overlap_y0:
                            continue

                        # Convert overlap to tile pixel coordinates
                        src_x = int((overlap_x0 - tile_x0_l0) * scale_x)
                        src_y = int((overlap_y0 - tile_y0_l0) * scale_y)
                        src_w = int((overlap_x1 - overlap_x0) * scale_x)
                        src_h = int((overlap_y1 - overlap_y0) * scale_y)

                        # Destination in result image (target level coordinates)
                        dst_x = int((overlap_x0 - x0) / downsample)
                        dst_y = int((overlap_y0 - y0) / downsample)
                        dst_w = int((overlap_x1 - overlap_x0) / downsample)
                        dst_h = int((overlap_y1 - overlap_y0) / downsample)

                        if src_w > 0 and src_h > 0 and dst_w > 0 and dst_h > 0:
                            cropped = tile_img.crop(
                                (src_x, src_y, src_x + src_w, src_y + src_h)
                            )
                            if cropped.size != (dst_w, dst_h):
                                cropped = cropped.resize(
                                    (dst_w, dst_h), Image.Resampling.BILINEAR
                                )
                            result.paste(cropped, (dst_x, dst_y))

        return result

    def _read_region_v6_shrink(
        self,
        location: Tuple[int, int],
        level: int,
        size: Tuple[int, int],
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> Image.Image:
        """Read region using ShrinkTileInfo for low resolution levels.

        ShrinkTileInfo stores pre-rendered tiles for low resolution levels.
        Each tile covers an area of (tile_w * scale) x (tile_h * scale) in level 0 coords.
        The n_x, n_y fields are the top-left corner in level 0 coordinates.
        """
        result = self._get_blank_tile(width, height)
        downsample = (
            self.level_downsamples[level]
            if level < len(self.level_downsamples)
            else 1.0
        )

        tile_w = self._header.tile_width or 512
        tile_h = self._header.tile_height or 512
        ratio_step = self._header.ratio_step

        # Determine which layer_no to use based on level
        # level corresponds to layer_no (level 2 -> layer_no 2, etc.)
        target_layer_no = level

        # level 0 coordinates of the requested region
        x0 = int(location[0])
        y0 = int(location[1])
        w0 = int(width * downsample)
        h0 = int(height * downsample)

        # Find shrink tiles that cover our region
        for st in self._shrink_tile_infos:
            # Only use tiles from the matching layer
            if st.layer_no != target_layer_no:
                continue

            # Calculate the area this shrink tile covers in level 0 coordinates
            # scale = ratio_step ^ layer_no
            scale = ratio_step**st.layer_no
            st_w = tile_w * scale  # Tile covers tile_w * scale pixels in level 0
            st_h = tile_h * scale

            st_x0 = st.n_x
            st_y0 = st.n_y

            # Check overlap with requested region
            if (
                st_x0 + st_w <= x0
                or st_x0 >= x0 + w0
                or st_y0 + st_h <= y0
                or st_y0 >= y0 + h0
            ):
                continue

            if st.offset <= 0 or st.length <= 0:
                continue

            # Read tile from appropriate file
            fh = self._get_file_handle(st.file_id)
            if fh is None:
                continue
            fh.seek(st.offset)
            tile_img = self._decode_tile(fh.read(st.length))
            if tile_img is None:
                continue

            # Calculate paste position in target level coordinates
            # The tile's position in target level = (n_x / downsample, n_y / downsample)
            tile_x = int(st_x0 / downsample) - x
            tile_y = int(st_y0 / downsample) - y

            src_x = max(0, -tile_x)
            src_y = max(0, -tile_y)
            dst_x = max(0, tile_x)
            dst_y = max(0, tile_y)
            paste_w = min(tile_img.width - src_x, width - dst_x)
            paste_h = min(tile_img.height - src_y, height - dst_y)

            if paste_w > 0 and paste_h > 0:
                crop_box = (src_x, src_y, src_x + paste_w, src_y + paste_h)
                result.paste(tile_img.crop(crop_box), (dst_x, dst_y))

        return result

    # Legacy properties
    @property
    def get_scan_scale(self):
        return self._header.scan_scale

    @property
    def get_tmap_version(self):
        return self._header.version

    @property
    def get_pixel_size(self):
        return self._header.pixel_size

    @property
    def get_focus_layer(self):
        return self._header.focus_nums

    @property
    def get_tile_mumber(self):
        return self._header.tile_num
