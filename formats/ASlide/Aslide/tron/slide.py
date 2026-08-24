#!/usr/bin/env python3
"""
Integrated TRON Slide implementation using official SDK for all operations
"""

import os
import tempfile
import zipfile
import shutil
from PIL import Image
import numpy as np
from typing import Dict, List, Tuple, Optional, Any

# Import official TRON SDK
try:
    from .sdk import TronSDK as _TronSDK
except ImportError:
    _TronSDK = None

OFFICIAL_SDK_AVAILABLE = _TronSDK is not None


class TronSlide:
    """
    TRON slide reader with official SDK integration
    """

    def __init__(self, filepath: str):
        """Initialize TRON slide with official SDK integration"""
        self.filepath = filepath
        self.format = ".tron"  # Add format attribute for DeepZoom compatibility
        self._sdk = None
        self._temp_dir = None
        self._zip_file = None

        # Slide properties
        self._level_count = 0
        self._level_dimensions = []
        self._level_downsamples = []
        self._properties = {}
        self._associated_images = {}

        # MPP values
        self.mpp_x = None
        self.mpp_y = None

        # Initialize
        self._initialize()

    def _initialize(self):
        """Initialize the slide using both SDK and ZIP access"""
        # Try to use official SDK
        sdk_cls = _TronSDK
        if sdk_cls is not None:
            try:
                self._sdk = sdk_cls(self.filepath)
                self._load_from_sdk()
            except Exception as e:
                print(f"⚠️  Official SDK failed: {e}")
                self._sdk = None

        # Always open ZIP for associated images and fallback
        self._open_zip_file()
        self._load_associated_images()

        # If SDK failed, use fallback methods
        if not self._sdk:
            self._analyze_zip_structure()

    def _load_from_sdk(self):
        """Load slide information from official SDK"""
        if not self._sdk:
            return

        try:
            # Get MPP
            mpp_x, mpp_y = self._sdk.get_resolution()
            if mpp_x > 0 and mpp_y > 0:
                self.mpp_x = mpp_x
                self.mpp_y = mpp_y

            # Get LOD level range
            min_lod, max_lod = self._sdk.get_lod_level_range()
            self._level_count = max_lod - min_lod + 1

            # Get content region for dimensions calculation
            left, top, width, height = self._sdk.get_content_region()

            # Calculate level dimensions (approximate)
            base_width, base_height = width, height
            self._level_dimensions = []
            self._level_downsamples = []

            for level in range(self._level_count):
                downsample = 2**level
                level_width = max(1, base_width // downsample)
                level_height = max(1, base_height // downsample)
                self._level_dimensions.append((level_width, level_height))
                self._level_downsamples.append(float(downsample))

            # Get other properties
            try:
                name = self._sdk.get_name()
                self._properties["tron.name"] = name
            except:
                pass

            try:
                vendor = self._sdk.get_vendor()
                self._properties["tron.vendor"] = vendor
            except:
                pass

            try:
                comments = self._sdk.get_comments()
                self._properties["tron.comments"] = comments
            except:
                pass

            # Get background color
            try:
                r, g, b = self._sdk.get_background_color()
                self._properties["tron.background-color"] = f"rgb({r},{g},{b})"
            except:
                pass

            # Get tile size
            try:
                tile_w, tile_h = self._sdk.get_tile_size()
                self._properties["tron.tile-width"] = str(tile_w)
                self._properties["tron.tile-height"] = str(tile_h)
            except:
                pass

            # Add MPP to properties
            if self.mpp_x is not None:
                self._properties["openslide.mpp-x"] = str(self.mpp_x)
            if self.mpp_y is not None:
                self._properties["openslide.mpp-y"] = str(self.mpp_y)

            if self.mpp_x and self.mpp_x > 0:
                self._properties["openslide.objective-power"] = str(
                    int(10.0 / self.mpp_x)
                )

            self._properties["tron.sdk-version"] = "official-1.1.1"
            self._properties["openslide.vendor"] = "Intermedic"

        except Exception as e:
            print(f"⚠️  SDK property loading failed: {e}")

    def _open_zip_file(self):
        """Open ZIP file for associated images and fallback access"""
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"TRON file not found: {self.filepath}")

        if not zipfile.is_zipfile(self.filepath):
            raise ValueError(f"File is not a valid ZIP archive: {self.filepath}")

        # Keep ZIP file open for DeepZoom access
        self._zip_file = zipfile.ZipFile(self.filepath, "r")

        # Create temporary directory for extraction
        self._temp_dir = tempfile.mkdtemp(prefix="tron_integrated_")

        # Extract ZIP contents
        for member in self._zip_file.infolist():
            member.filename = member.filename.replace("\\", "/")
            self._zip_file.extract(member, self._temp_dir)

    def _analyze_zip_structure(self):
        """Analyze ZIP structure as fallback when SDK is not available"""
        if not self._temp_dir:
            return

        # Find level directories
        level_dirs = []
        for item in os.listdir(self._temp_dir):
            item_path = os.path.join(self._temp_dir, item)
            if os.path.isdir(item_path) and item.isdigit():
                level_dirs.append(int(item))

        level_dirs.sort()
        self._level_count = len(level_dirs)

        # Analyze each level
        self._level_dimensions = []
        self._level_downsamples = []

        for level in level_dirs:
            level_path = os.path.join(self._temp_dir, str(level), "1")
            if os.path.exists(level_path):
                # Find tile coordinate ranges
                tiles = []
                for tile_file in os.listdir(level_path):
                    if tile_file.endswith(".jpg"):
                        parts = tile_file[:-4].split("/")
                        if len(parts) >= 2:
                            try:
                                x, y = int(parts[-2]), int(parts[-1])
                                tiles.append((x, y))
                            except:
                                continue

                if tiles:
                    min_x = min(t[0] for t in tiles)
                    max_x = max(t[0] for t in tiles)
                    min_y = min(t[1] for t in tiles)
                    max_y = max(t[1] for t in tiles)

                    # Estimate dimensions (assuming 1024x1024 tiles)
                    width = (max_x - min_x + 1) * 1024
                    height = (max_y - min_y + 1) * 1024

                    self._level_dimensions.append((width, height))
                else:
                    self._level_dimensions.append((1024, 1024))
            else:
                self._level_dimensions.append((1024, 1024))

        # Calculate downsamples
        if self._level_dimensions:
            base_width, base_height = self._level_dimensions[0]
            for width, height in self._level_dimensions:
                downsample = base_width / width if width > 0 else 1.0
                self._level_downsamples.append(downsample)

    def _load_associated_images(self):
        """Load associated images from ZIP"""
        if not self._temp_dir:
            return

        associated_files = ["label", "macro", "thumbnail", "sample", "blank"]

        for assoc_name in associated_files:
            assoc_path = os.path.join(self._temp_dir, assoc_name)
            if os.path.exists(assoc_path):
                try:
                    with open(assoc_path, "rb") as f:
                        image_data = f.read()
                    image = Image.open(assoc_path)
                    self._associated_images[assoc_name] = image
                except Exception as e:
                    print(f"⚠️  Failed to load {assoc_name}: {e}")

    @property
    def dimensions(self) -> Tuple[int, int]:
        """Get the dimensions of level 0"""
        if self._level_dimensions:
            return self._level_dimensions[0]
        return (0, 0)

    @property
    def level_count(self) -> int:
        """Get the number of levels"""
        return self._level_count

    @property
    def level_dimensions(self) -> Tuple[Tuple[int, int], ...]:
        """Get dimensions for all levels"""
        return tuple(self._level_dimensions)

    @property
    def level_downsamples(self) -> Tuple[float, ...]:
        """Get downsamples for all levels"""
        return tuple(self._level_downsamples)

    def get_best_level_for_downsample(self, downsample):
        """Return best slide level for a given overall downsample.

        This mirrors OpenSlide's behavior:
        - Return the largest level whose downsample is <= target
        - This ensures we don't over-downsample (lose resolution)
        """
        # Get downsamples
        downs = list(self.level_downsamples)

        # Ensure downsamples are monotonically increasing
        for i in range(1, len(downs)):
            if downs[i] < downs[i - 1]:
                downs[i] = max(downs[i], downs[i - 1])

        # If target is smaller than level 0, return level 0
        if downsample < downs[0]:
            return 0

        # Find the largest level with downsample <= target
        for i in range(1, len(downs)):
            if downs[i] > downsample:
                return i - 1

        # Target is >= all levels, return the last level
        return self.level_count - 1

    @property
    def properties(self) -> Dict[str, str]:
        """Get slide properties"""
        return self._properties.copy()

    @property
    def associated_images(self) -> Dict[str, Image.Image]:
        """Get associated images"""
        return self._associated_images.copy()

    def close(self):
        """Close the slide and clean up resources"""
        if self._sdk:
            self._sdk.close()
            self._sdk = None

        if self._zip_file:
            self._zip_file.close()
            self._zip_file = None

        if self._temp_dir and os.path.exists(self._temp_dir):
            shutil.rmtree(self._temp_dir)
            self._temp_dir = None

    def __del__(self):
        self.close()

    @classmethod
    def detect_format(cls, filename) -> Optional[str]:
        if not os.path.exists(filename):
            return None
        return ".tron" if zipfile.is_zipfile(filename) else None

    def read_region(
        self, location: Tuple[int, int], level: int, size: Tuple[int, int]
    ) -> Image.Image:
        """
        Read a region from the slide using official SDK when available

        Args:
            location: (x, y) coordinates in level 0 reference frame
            level: pyramid level
            size: (width, height) of the region to read

        Returns:
            PIL Image of the requested region
        """
        x, y = location
        width, height = size

        # Try to use official SDK first
        if self._sdk:
            try:
                return self._read_region_sdk(x, y, level, width, height)
            except Exception as e:
                print(f"⚠️  SDK read_region failed, using fallback: {e}")

        # Fallback to ZIP-based reading
        return self._read_region_zip(x, y, level, width, height)

    def _read_region_sdk(
        self, x: int, y: int, level: int, width: int, height: int
    ) -> Image.Image:
        """Read region using official SDK"""
        import ctypes

        if self._sdk is None:
            raise RuntimeError("TRON SDK not initialized")

        # Allocate buffer for BGR24 data (3 bytes per pixel)
        buffer_size = width * height * 3
        buffer = (ctypes.c_uint8 * buffer_size)()

        # Call SDK read_region (layer=1 for single-layer slides)
        from .sdk import tronc

        if tronc is None:
            raise RuntimeError("TRON SDK library not available")
        bytes_read = tronc.tron_read_region(
            self._sdk.handle,
            ctypes.c_int32(level),
            ctypes.c_int32(1),  # layer
            ctypes.c_int32(x),
            ctypes.c_int32(y),
            ctypes.c_size_t(width),
            ctypes.c_size_t(height),
            buffer,
        )

        if bytes_read != buffer_size:
            raise RuntimeError(
                f"SDK read_region returned {bytes_read} bytes, expected {buffer_size}"
            )

        # SDK returns RGB24 format directly
        rgb_array = np.frombuffer(buffer, dtype=np.uint8).reshape((height, width, 3))

        return Image.fromarray(rgb_array, "RGB")

    def _read_region_zip(
        self, x: int, y: int, level: int, width: int, height: int
    ) -> Image.Image:
        """Read region using ZIP-based fallback method.

        This method is not implemented. The TRON SDK is required for reading regions.
        """
        raise NotImplementedError(
            "TRON ZIP-based fallback reading is not implemented. "
            "Please ensure the TRON SDK library (libtronc.so) is available."
        )

    def get_thumbnail(self, size: Tuple[int, int]) -> Image.Image:
        """
        Get a thumbnail of the slide

        Args:
            size: (width, height) of the thumbnail

        Returns:
            PIL Image thumbnail
        """
        # Try to use existing thumbnail first
        if "thumbnail" in self._associated_images:
            thumbnail = self._associated_images["thumbnail"]
            thumbnail.thumbnail(size, Image.Resampling.LANCZOS)
            return thumbnail

        # Generate thumbnail from the slide
        # Find the appropriate level for the thumbnail
        target_downsample = max(
            self.dimensions[0] / size[0], self.dimensions[1] / size[1]
        )

        # Find the best level
        best_level = 0
        for i, downsample in enumerate(self._level_downsamples):
            if downsample <= target_downsample:
                best_level = i
            else:
                break

        # Read from the best level
        level_width, level_height = self._level_dimensions[best_level]
        thumbnail = self.read_region((0, 0), best_level, (level_width, level_height))
        thumbnail.thumbnail(size, Image.Resampling.LANCZOS)

        return thumbnail
