import numpy as np
from ctypes import *
import gc
from PIL import Image
import io
from .sdpc_bindings import sdpc_sdk, SDPCError, SDPCWSIType, ColorStyle, c_int32


class SdpcSlide:
    """
    SDPC slide reader using the native SDPC SDK
    """

    def __init__(self, sdpcPath):
        """Initialize SDPC slide reader"""
        self.slide_path = sdpcPath
        self.slide = None
        self._closed = False  # Track if slide has been closed
        self._level_count = None
        self._level_dimensions = None
        self._level_downsamples = None
        self._properties = None

        # Open the slide
        status = c_int()
        self.slide = sdpc_sdk.sqrayslide_open(sdpcPath.encode("utf-8"), byref(status))

        if not self.slide or status.value != SDPCError.SqSuccess:
            error_msg = (
                f"Failed to open SDPC file: {sdpcPath}, error code: {status.value}"
            )
            raise RuntimeError(error_msg)

        # Initialize cached properties
        self._init_properties()

    @classmethod
    def detect_format(cls, filename):
        """Detect if file is SDPC format"""
        import os

        ext = os.path.splitext(filename)[1].lower()
        if ext in [".sdpc"]:
            return "sdpc"
        return None

    def _init_properties(self):
        """Initialize cached properties"""
        # Get basic properties
        mpp_x = c_double()
        mpp_y = c_double()
        sdpc_sdk.sqrayslide_get_mpp(self.slide, byref(mpp_x), byref(mpp_y))

        magnification = c_float()
        sdpc_sdk.sqrayslide_get_magnification(self.slide, byref(magnification))

        # Cache properties for openslide compatibility
        self._properties = {
            "openslide.mpp-x": str(mpp_x.value),
            "openslide.mpp-y": str(mpp_y.value),
            "openslide.objective-power": str(magnification.value),
            "openslide.vendor": "TEKSQRAY",
            "sdpc.magnification": magnification.value,
        }

    def _check_closed(self):
        """Check if slide is closed and raise exception if so"""
        if getattr(self, "_closed", False) or not self.slide:
            raise RuntimeError("Slide has been closed")

    @property
    def level_count(self):
        """Get the number of levels in the slide"""
        self._check_closed()
        if self._level_count is None:
            self._level_count = sdpc_sdk.sqrayslide_get_level_count(self.slide)
        return self._level_count

    @property
    def level_dimensions(self):
        """Get dimensions for each level (excluding padding)"""
        if self._level_dimensions is None:
            dimensions = []
            for level in range(self.level_count):
                width = c_int32()
                height = c_int32()
                sdpc_sdk.sqrayslide_get_level_size(
                    self.slide, level, byref(width), byref(height)
                )
                # Get padding size and subtract it
                right_padding = c_int32()
                bottom_padding = c_int32()
                sdpc_sdk.sqrayslide_get_level_right_buttom_bounds_size(
                    self.slide, level, byref(right_padding), byref(bottom_padding)
                )
                actual_width = width.value - right_padding.value
                actual_height = height.value - bottom_padding.value
                dimensions.append((actual_width, actual_height))
            self._level_dimensions = tuple(dimensions)
        return self._level_dimensions

    @property
    def level_downsamples(self):
        """Get downsample factors for each level

        Returns standard OpenSlide-compatible downsamples (1.0, 2.0, 4.0, ...)
        SDPC SDK returns inverse downsamples (1.0, 0.5, 0.25, ...), so we convert them here.
        """
        if self._level_downsamples is None:
            downsamples = []
            for level in range(self.level_count):
                downsample = sdpc_sdk.sqrayslide_get_level_downsample(self.slide, level)

                # SDPC SDK returns inverse downsamples (1.0, 0.5, 0.25, etc.)
                # Convert to standard format (1.0, 2.0, 4.0, etc.) for OpenSlide compatibility
                if downsample > 0 and downsample <= 1.0 and level > 0:
                    # Inverse the value for levels > 0
                    downsample = 1.0 / downsample
                elif downsample <= 0:
                    # Handle invalid values
                    downsample = float("inf")

                downsamples.append(downsample)

            # Ensure downsamples are monotonically increasing
            for i in range(1, len(downsamples)):
                if downsamples[i] < downsamples[i - 1]:
                    downsamples[i] = max(downsamples[i], downsamples[i - 1])

            self._level_downsamples = tuple(downsamples)
        return self._level_downsamples

    @property
    def dimensions(self):
        """Return the dimensions of the highest resolution level (level 0)."""
        return self.level_dimensions[0] if self.level_dimensions else (0, 0)

    @property
    def properties(self):
        """Get slide properties"""
        return self._properties

    def get_best_level_for_downsample(self, downsample):
        """Return best slide level for a given overall downsample.

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

    def read_region(self, location, level, size):
        """
        Read a region from the slide

        Args:
            location: (x, y) tuple of the top-left corner in level 0 coordinates
            level: pyramid level to read from
            size: (width, height) tuple of the region size

        Returns:
            PIL Image object
        """
        self._check_closed()
        startX, startY = location
        width, height = size

        # Validate parameters
        if level < 0 or level >= self.level_count:
            raise ValueError(f"Invalid level: {level}")

        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid size: {size}")

        # Convert level-0 coordinates to level-specific coordinates
        # SDPC SDK expects coordinates in the current level's coordinate system,
        # not level 0 coordinates (similar to KFB format, different from OpenSlide)
        downsample = self.level_downsamples[level]
        level_x = int(startX / downsample)
        level_y = int(startY / downsample)

        # Allocate buffer for BGRA data
        buffer_size = width * height * 4  # 4 bytes per pixel (BGRA)
        bgra_buffer = (c_ubyte * buffer_size)()

        # Read region as BGRA using level-specific coordinates
        success = sdpc_sdk.sqrayslide_read_region_bgra(
            self.slide, bgra_buffer, level_x, level_y, width, height, level
        )

        if not success:
            raise RuntimeError(
                f"Failed to read region at level-0 coords ({startX}, {startY}) "
                f"-> level-{level} coords ({level_x}, {level_y}) with size ({width}, {height})"
            )

        # Convert BGRA buffer to numpy array
        bgra_array = np.frombuffer(bgra_buffer, dtype=np.uint8)
        bgra_array = bgra_array.reshape((height, width, 4))

        # Convert BGRA to RGB (drop alpha channel and swap B and R)
        rgb_array = bgra_array[:, :, [2, 1, 0]]  # BGR -> RGB

        # Create PIL Image
        img = Image.fromarray(rgb_array, "RGB")
        return img

    def get_thumbnail(self, size):
        """Get a thumbnail of the slide"""
        self._check_closed()
        # Read from the highest level (lowest resolution)
        highest_level = self.level_count - 1
        thumbnail = self.read_region(
            (0, 0), highest_level, self.level_dimensions[highest_level]
        )
        thumbnail.thumbnail(size, Image.Resampling.LANCZOS)
        return thumbnail

    def get_label_image(self):
        """Get label image as PIL Image object"""
        try:
            width = c_int32()
            height = c_int32()
            data = POINTER(c_ubyte)()
            data_size = c_int32()

            # Try to get label image (imageType=0 for label)
            success = sdpc_sdk.sqrayslide_read_label_jpeg(
                self.slide,
                0,
                byref(width),
                byref(height),
                byref(data),
                byref(data_size),
            )

            if success and data and data_size.value > 0:
                # Convert to bytes
                buf = bytearray(data[: data_size.value])

                # Free the memory allocated by the library
                sdpc_sdk.sqrayslide_free_memory(data)

                # Create PIL Image from JPEG bytes
                image = Image.open(io.BytesIO(buf))
                return image
            else:
                return None
        except Exception as e:
            print(f"Error getting label image: {e}")
            return None

    def saveLabelImg(self, save_path):
        """Save label image to file"""
        try:
            width = c_int32()
            height = c_int32()
            data = POINTER(c_ubyte)()
            data_size = c_int32()

            success = sdpc_sdk.sqrayslide_read_label_jpeg(
                self.slide,
                0,
                byref(width),
                byref(height),
                byref(data),
                byref(data_size),
            )

            if success and data and data_size.value > 0:
                with open(save_path, "wb") as f:
                    buf = bytearray(data[: data_size.value])
                    f.write(buf)

                # Free the memory allocated by the library
                sdpc_sdk.sqrayslide_free_memory(data)
            else:
                raise RuntimeError("Failed to get label image")
        except Exception as e:
            print(f"Error saving label image: {e}")
            raise

    @property
    def associated_images(self):
        """Get associated images"""
        result = {}

        # Try to get label image
        label_img = self.get_label_image()
        if label_img:
            result["label"] = label_img

        # Try to get thumbnail image (imageType=1 for thumbnail)
        try:
            width = c_int32()
            height = c_int32()
            data = POINTER(c_ubyte)()
            data_size = c_int32()

            success = sdpc_sdk.sqrayslide_read_label_jpeg(
                self.slide,
                1,
                byref(width),
                byref(height),
                byref(data),
                byref(data_size),
            )

            if success and data and data_size.value > 0:
                buf = bytearray(data[: data_size.value])
                sdpc_sdk.sqrayslide_free_memory(data)
                thumbnail_img = Image.open(io.BytesIO(buf))
                result["thumbnail"] = thumbnail_img
        except Exception:
            pass  # Thumbnail is optional

        # Try to get macro image (imageType=2 for macro)
        try:
            width = c_int32()
            height = c_int32()
            data = POINTER(c_ubyte)()
            data_size = c_int32()

            success = sdpc_sdk.sqrayslide_read_label_jpeg(
                self.slide,
                2,
                byref(width),
                byref(height),
                byref(data),
                byref(data_size),
            )

            if success and data and data_size.value > 0:
                buf = bytearray(data[: data_size.value])
                sdpc_sdk.sqrayslide_free_memory(data)
                macro_img = Image.open(io.BytesIO(buf))
                result["macro"] = macro_img
        except Exception:
            pass  # Macro is optional

        return result

    def close(self):
        """Close the slide and free resources"""
        # Check if already closed to prevent double-free
        if getattr(self, "_closed", False):
            return

        try:
            if hasattr(self, "slide") and self.slide:
                sdpc_sdk.sqrayslide_close(self.slide)
                self.slide = None
        except Exception as e:
            print(f"Error closing SDPC file: {e}")
        finally:
            # Mark as closed
            self._closed = True
            # Clear cached properties
            self._level_count = None
            self._level_dimensions = None
            self._level_downsamples = None
            self._properties = None
            gc.collect()

    def __del__(self):
        """Destructor - safely close if not already closed"""
        try:
            # Only close if not already closed and slide exists
            if (
                not getattr(self, "_closed", False)
                and hasattr(self, "slide")
                and self.slide
            ):
                self.close()
        except Exception:
            # Silently ignore errors during destruction to prevent crashes
            pass

    # Additional utility methods
    def get_tile_size(self):
        """Get the tile size used by the slide"""
        width = c_int32()
        height = c_int32()
        sdpc_sdk.sqrayslide_get_tile_size(self.slide, byref(width), byref(height))
        return (width.value, height.value)

    def get_barcode(self):
        """Get the barcode of the slide if available"""
        barcode_ptr = sdpc_sdk.sqrayslide_get_barcode(self.slide)
        if barcode_ptr:
            return barcode_ptr.decode("utf-8")
        return None

    def get_slide_type(self):
        """Get the slide type (Brightfield or Fluorescence)"""
        slide_type = sdpc_sdk.sqrayslide_get_type(self.slide)
        return (
            "Brightfield" if slide_type == SDPCWSIType.Brightfield else "Fluorescence"
        )

    def apply_color_correction(self, apply=True, style="Real"):
        """
        Apply or disable color correction

        Args:
            apply: Whether to apply color correction
            style: Color correction style ("Real" or "Gorgeous")
        """
        style_value = ColorStyle.Real if style == "Real" else ColorStyle.Gorgeous
        sdpc_sdk.sqrayslide_apply_color_correction(self.slide, apply, style_value)

    def set_jpeg_quality(self, quality):
        """
        Set JPEG compression quality for tile/region reading

        Args:
            quality: Quality value from 1-99 (higher is better quality)
        """
        if not 1 <= quality <= 99:
            raise ValueError("Quality must be between 1 and 99")
        sdpc_sdk.sqrayslide_set_jpeg_quality(self.slide, quality)

    def get_channel_count(self):
        """Get the number of channels (for fluorescence slides)"""
        return sdpc_sdk.sqrayslide_get_channel_count(self.slide)

    def get_plane_count(self):
        """Get the number of focal planes"""
        return sdpc_sdk.sqrayslide_get_plane_count(self.slide)

    def get_plane_space_between(self):
        """Get the physical distance between focal planes in micrometers"""
        return sdpc_sdk.sqrayslide_get_plane_space_between(self.slide)
