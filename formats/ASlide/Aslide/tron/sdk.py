#!/usr/bin/env python3
"""
Python bindings for the official TRON SDK
"""

import ctypes
import os
from ctypes import (
    Structure,
    c_int32,
    c_float,
    c_uint8,
    c_size_t,
    c_char_p,
    POINTER,
    c_bool,
)


# Find the library path
def find_tron_library():
    """Find the TRON library file"""
    # First try the bundled SDK
    bundled_lib = os.path.join(os.path.dirname(__file__), "lib", "libtronc.so")
    if os.path.exists(bundled_lib):
        return bundled_lib

    # Fallback to other possible locations
    possible_paths = [
        os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "c", "lib", "libtronc.so"
        ),
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "c",
            "demo",
            "bin",
            "libtronc.so",
        ),
        "libtronc.so",
        "./libtronc.so",
    ]

    for path in possible_paths:
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            return abs_path

    raise FileNotFoundError("Cannot find libtronc.so library")


# Load the library
try:
    lib_path = find_tron_library()
    tronc = ctypes.CDLL(lib_path)
except Exception as e:
    print(f"Warning: Cannot load TRON SDK library: {e}")
    tronc = None

# Error codes
TRON_SUCCESS = 0
TRON_INVALID_PATH = 1
TRON_IO_ERROR = 2
TRON_INVALID_ARCHIVE = 3
TRON_INVALID_HANDLER = 10
TRON_INVALID_LOD_LEVEL = 20
TRON_INSUFFICIENT_LENGTH = 30
TRON_INVALID_IMAGE_NAME = 40
TRON_CLIP_ARCHIVE_ERROR = 100
TRON_CLIP_INVALID_ARGUMENT = 101
TRON_UNKNOWN_ERROR = -1


# Structures
class TronResolution(Structure):
    _fields_ = [("horizontal", c_float), ("vertical", c_float)]


class TronBackgroundColor(Structure):
    _fields_ = [("red", c_uint8), ("green", c_uint8), ("blue", c_uint8)]


class TronContentRegion(Structure):
    _fields_ = [
        ("left", c_int32),
        ("top", c_int32),
        ("width", c_int32),
        ("height", c_int32),
    ]


class TronLodLevelRange(Structure):
    _fields_ = [("minimum", c_int32), ("maximum", c_int32)]


class TronImageInfo(Structure):
    _fields_ = [
        ("existed", c_bool),
        ("width", c_size_t),
        ("height", c_size_t),
        ("length", c_size_t),
    ]


class TronTileSize(Structure):
    _fields_ = [("width", c_int32), ("height", c_int32)]


class TronTileCount(Structure):
    _fields_ = [("horizontal", c_int32), ("vertical", c_int32)]


class TronVersion(Structure):
    _fields_ = [("major", c_int32), ("minor", c_int32)]


# Function signatures
if tronc:
    # tron_open
    tronc.tron_open.argtypes = [c_char_p]
    tronc.tron_open.restype = ctypes.c_void_p

    # tron_close
    tronc.tron_close.argtypes = [ctypes.c_void_p]
    tronc.tron_close.restype = None

    # tron_get_last_error
    tronc.tron_get_last_error.argtypes = []
    tronc.tron_get_last_error.restype = c_int32

    # tron_get_resolution
    tronc.tron_get_resolution.argtypes = [ctypes.c_void_p]
    tronc.tron_get_resolution.restype = TronResolution

    # tron_get_background_color
    tronc.tron_get_background_color.argtypes = [ctypes.c_void_p]
    tronc.tron_get_background_color.restype = TronBackgroundColor

    # tron_get_content_region
    tronc.tron_get_content_region.argtypes = [ctypes.c_void_p]
    tronc.tron_get_content_region.restype = TronContentRegion

    # tron_get_lod_level_range
    tronc.tron_get_lod_level_range.argtypes = [ctypes.c_void_p]
    tronc.tron_get_lod_level_range.restype = TronLodLevelRange

    # tron_get_tile_size
    tronc.tron_get_tile_size.argtypes = [ctypes.c_void_p]
    tronc.tron_get_tile_size.restype = TronTileSize

    # tron_get_version
    tronc.tron_get_version.argtypes = [ctypes.c_void_p]
    tronc.tron_get_version.restype = TronVersion

    # tron_get_layer_count
    tronc.tron_get_layer_count.argtypes = [ctypes.c_void_p]
    tronc.tron_get_layer_count.restype = c_int32

    # tron_get_representative_layer_index
    tronc.tron_get_representative_layer_index.argtypes = [ctypes.c_void_p]
    tronc.tron_get_representative_layer_index.restype = c_int32

    # tron_get_name
    tronc.tron_get_name.argtypes = [ctypes.c_void_p, c_char_p, c_size_t]
    tronc.tron_get_name.restype = c_size_t

    # tron_get_vendor
    tronc.tron_get_vendor.argtypes = [ctypes.c_void_p, c_char_p, c_size_t]
    tronc.tron_get_vendor.restype = c_size_t

    # tron_get_comments
    tronc.tron_get_comments.argtypes = [ctypes.c_void_p, c_char_p, c_size_t]
    tronc.tron_get_comments.restype = c_size_t

    # tron_get_named_image_info
    tronc.tron_get_named_image_info.argtypes = [ctypes.c_void_p, c_char_p]
    tronc.tron_get_named_image_info.restype = TronImageInfo

    # tron_get_named_image_data
    tronc.tron_get_named_image_data.argtypes = [
        ctypes.c_void_p,
        c_char_p,
        POINTER(c_uint8),
    ]
    tronc.tron_get_named_image_data.restype = c_size_t

    # tron_read_region
    tronc.tron_read_region.argtypes = [
        ctypes.c_void_p,
        c_int32,
        c_int32,
        c_int32,
        c_int32,
        c_size_t,
        c_size_t,
        POINTER(c_uint8),
    ]
    tronc.tron_read_region.restype = c_size_t

    # tron_get_tile_count
    tronc.tron_get_tile_count.argtypes = [ctypes.c_void_p]
    tronc.tron_get_tile_count.restype = TronTileCount

    # tron_get_tile_image_info
    tronc.tron_get_tile_image_info.argtypes = [
        ctypes.c_void_p,
        c_int32,
        c_int32,
        c_int32,
        c_int32,
    ]
    tronc.tron_get_tile_image_info.restype = TronImageInfo


class TronSDK:
    """Python wrapper for the official TRON SDK"""

    def __init__(self, filepath):
        self._sdk = self._require_sdk()
        if not self._sdk:
            raise RuntimeError("TRON SDK library not available")

        self.filepath = filepath
        self.handle = None
        self._open()

    def _open(self):
        """Open the TRON file"""
        sdk = self._require_sdk()
        self.handle = sdk.tron_open(self.filepath.encode("utf-8"))
        if not self.handle:
            error_code = sdk.tron_get_last_error()
            raise RuntimeError(f"Failed to open TRON file: error code {error_code}")

    @staticmethod
    def _require_sdk():
        if tronc is None:
            raise RuntimeError("TRON SDK library not available")
        return tronc

    def _require_handle(self):
        if not self.handle:
            raise RuntimeError("TRON file not opened")
        return self.handle

    def close(self):
        """Close the TRON file"""
        if self.handle:
            self._require_sdk().tron_close(self.handle)
            self.handle = None

    def __del__(self):
        self.close()

    def get_resolution(self):
        """Get the resolution (MPP) information"""
        handle = self._require_handle()
        resolution = self._require_sdk().tron_get_resolution(handle)
        return resolution.horizontal, resolution.vertical

    def get_background_color(self):
        """Get the background color"""
        handle = self._require_handle()
        color = self._require_sdk().tron_get_background_color(handle)
        return color.red, color.green, color.blue

    def get_content_region(self):
        """Get the content region"""
        handle = self._require_handle()
        region = self._require_sdk().tron_get_content_region(handle)
        return region.left, region.top, region.width, region.height

    def get_lod_level_range(self):
        """Get the LOD level range"""
        handle = self._require_handle()
        range_info = self._require_sdk().tron_get_lod_level_range(handle)
        return range_info.minimum, range_info.maximum

    def get_tile_size(self):
        """Get the tile size"""
        handle = self._require_handle()
        tile_size = self._require_sdk().tron_get_tile_size(handle)
        return tile_size.width, tile_size.height

    def get_string_property(self, func, buffer_size=256):
        """Get a string property from TRON"""
        handle = self._require_handle()
        buffer = ctypes.create_string_buffer(buffer_size)
        length = func(handle, buffer, buffer_size)

        if length > buffer_size:
            # Need larger buffer
            buffer = ctypes.create_string_buffer(length)
            func(handle, buffer, length)

        return buffer.value.decode("utf-8")

    def get_name(self):
        """Get the slide name"""
        return self.get_string_property(self._require_sdk().tron_get_name)

    def get_vendor(self):
        """Get the vendor name"""
        return self.get_string_property(self._require_sdk().tron_get_vendor)

    def get_comments(self):
        """Get the comments"""
        return self.get_string_property(self._require_sdk().tron_get_comments)

    def get_tile_count(self):
        """Get the tile count for each level"""
        handle = self._require_handle()
        tile_count = self._require_sdk().tron_get_tile_count(handle)
        return tile_count.horizontal, tile_count.vertical

    def get_tile_image_info(self, lod_level, layer, row, column):
        """Get tile image info to check if tile exists"""
        handle = self._require_handle()
        tile_info = self._require_sdk().tron_get_tile_image_info(
            handle, lod_level, layer, row, column
        )
        return tile_info.existed, tile_info.width, tile_info.height, tile_info.length
