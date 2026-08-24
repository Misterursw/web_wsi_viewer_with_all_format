"""
Bio-Formats based VSI slide reader for ASlide.
This implementation uses the python-bioformats wrapper to read VSI files.
"""

import os
import logging
import importlib
import numpy as np
from typing import Tuple, List, Dict, Any, Optional
from PIL import Image

try:
    _bioformats = importlib.import_module("bioformats")
    _javabridge = importlib.import_module("javabridge")
except ImportError:
    _bioformats = None
    _javabridge = None

from openslide import AbstractSlide

from ..errors import (
    MissingDefaultBiomarkerError,
    UnknownBiomarkerError,
)

logger = logging.getLogger(__name__)


def _select_largest_image_index(ome: Any) -> int:
    best_index = 0
    best_area = -1
    for index in range(ome.image_count):
        pixels = ome.image(index).Pixels
        area = int(pixels.SizeX) * int(pixels.SizeY)
        if area > best_area:
            best_index = index
            best_area = area
    return best_index


def _channel_metadata_name(channel: Any) -> Optional[str]:
    for attr in ("Name", "Fluor"):
        value = getattr(channel, attr, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _build_biomarker_map(pixels: Any) -> Dict[str, int]:
    biomarker_map: Dict[str, int] = {}
    size_c = int(getattr(pixels, "SizeC", 0) or 0)

    for index in range(size_c):
        try:
            channel = pixels.Channel(index)
        except Exception:
            channel = None
        if channel is not None:
            name = _channel_metadata_name(channel)
            if name and name not in biomarker_map:
                biomarker_map[name] = index

    for index in range(size_c):
        alias = f"channel_{index}"
        if alias not in biomarker_map:
            biomarker_map[alias] = index

    return biomarker_map


def _array_to_image(img_array: np.ndarray) -> Image.Image:
    if len(img_array.shape) == 3:
        return Image.fromarray(img_array)
    return Image.fromarray(img_array, mode="L")


class BioFormatsVsiSlide(AbstractSlide):
    """VSI slide reader using Bio-Formats."""

    def __init__(self, filename: str):
        """Initialize VSI slide using Bio-Formats."""
        if _bioformats is None or _javabridge is None:
            raise ImportError(
                "Bio-Formats not available. Install with: pip install python-bioformats"
            )

        AbstractSlide.__init__(self)
        self._filename = filename
        self._metadata = None
        self._ome = None
        self._image_reader = None
        self._java_started = False
        self._main_series = 0
        self._biomarker_to_channel: Dict[str, int] = {}

        # Start Java VM if not already started
        if not _javabridge.get_env():
            _javabridge.start_vm(class_path=_bioformats.JARS)
            self._java_started = True

        try:
            # Get metadata
            self._metadata = _bioformats.get_omexml_metadata(filename)
            self._ome = _bioformats.OMEXML(self._metadata)
            self._image_reader = _bioformats.ImageReader(filename)

            # Initialize slide properties
            self._init_properties()

        except Exception as e:
            self.close()
            raise Exception(f"Failed to initialize VSI slide: {e}")

    def _init_properties(self):
        """Initialize slide properties from Bio-Formats metadata."""
        if self._ome is None or self._ome.image_count == 0:
            raise ValueError("No images found in VSI file")

        self._main_series = _select_largest_image_index(self._ome)
        main_image = self._ome.image(self._main_series)
        pixels = main_image.Pixels
        self._biomarker_to_channel = _build_biomarker_map(pixels)

        # Basic dimensions
        self._level_count = 1  # Bio-Formats handles pyramid levels internally
        self._dimensions = (pixels.SizeX, pixels.SizeY)
        self._level_dimensions = (self._dimensions,)
        self._level_downsamples = (1.0,)

        # Try to get physical pixel size
        self._mpp_x = self._mpp_y = None
        try:
            phys_x = pixels.PhysicalSizeX
            phys_y = pixels.PhysicalSizeY
            if phys_x is not None and phys_y is not None:
                # Convert to microns per pixel (MPP)
                self._mpp_x = float(phys_x)
                self._mpp_y = float(phys_y)
                logger.info(
                    f"Physical pixel size from OME: {self._mpp_x} x {self._mpp_y} microns"
                )
            else:
                logger.warning(
                    "Physical pixel size not available in OME metadata, will try properties"
                )
        except Exception as e:
            logger.warning(f"Failed to get physical pixel size from OME: {e}")

        # If OME metadata doesn't have physical size, try to get it from properties later
        # This will be handled in the mpp property getter

        # Properties dictionary
        self._properties = {
            "openslide.vendor": "Olympus",
            "openslide.comment": "cellSens VSI format (Bio-Formats)",
            "bioformats.main.series": str(self._main_series),
        }

        if self._mpp_x and self._mpp_y:
            self._properties["openslide.mpp-x"] = str(self._mpp_x)
            self._properties["openslide.mpp-y"] = str(self._mpp_y)

        # Add Bio-Formats metadata
        if hasattr(main_image, "Name") and main_image.Name:
            self._properties["bioformats.image.name"] = main_image.Name

        self._properties["bioformats.pixel.type"] = pixels.PixelType
        self._properties["bioformats.size.c"] = str(pixels.SizeC)
        self._properties["bioformats.size.z"] = str(pixels.SizeZ)
        self._properties["bioformats.size.t"] = str(pixels.SizeT)
        if self._biomarker_to_channel:
            self._properties["vsi.biomarkers"] = ",".join(self._biomarker_to_channel)
            self._properties["vsi.biomarker-count"] = str(len(self._biomarker_to_channel))

    def classify_slide_family(self) -> str:
        return "multiplex" if self._biomarker_to_channel else "brightfield"

    def list_biomarkers(self) -> List[str]:
        return list(self._biomarker_to_channel)

    def get_biomarkers(self) -> List[str]:
        return self.list_biomarkers()

    def get_default_display_biomarker(self) -> str:
        biomarkers = self.list_biomarkers()
        if not biomarkers:
            raise MissingDefaultBiomarkerError("VSI slide does not define biomarkers")
        return biomarkers[0]

    @property
    def level_count(self) -> int:
        """Number of levels in the image pyramid."""
        return self._level_count

    @property
    def dimensions(self) -> Tuple[int, int]:
        """Dimensions of level 0 image."""
        return self._dimensions

    @property
    def level_dimensions(self) -> Tuple[Tuple[int, int], ...]:
        """List of (width, height) tuples for each level."""
        return self._level_dimensions

    @property
    def level_downsamples(self) -> Tuple[float, ...]:
        """List of downsample factors for each level."""
        return self._level_downsamples

    @property
    def properties(self) -> Dict[str, str]:
        """Metadata properties."""
        return self._properties.copy()

    @property
    def associated_images(self) -> Dict[str, Image.Image]:
        """Associated images (thumbnails, labels, etc.)."""
        # Bio-Formats handles associated images differently
        # For now, return empty dict
        return {}

    @property
    def mpp(self) -> Optional[float]:
        """Microns per pixel."""
        # First try the stored values
        if self._mpp_x and self._mpp_y:
            return (self._mpp_x + self._mpp_y) / 2

        # Fallback: get from properties
        props = self.properties
        if "openslide.mpp-x" in props and "openslide.mpp-y" in props:
            try:
                mpp_x = float(props["openslide.mpp-x"])
                mpp_y = float(props["openslide.mpp-y"])
                return (mpp_x + mpp_y) / 2
            except (ValueError, TypeError):
                pass

        return None

    @property
    def magnification(self) -> Optional[float]:
        """Get slide magnification."""
        # Check properties
        props = self.properties
        if "openslide.objective-power" in props:
            try:
                return float(props["openslide.objective-power"])
            except:
                pass

        # Fallback to MPP calculation
        mpp = self.mpp
        if mpp and mpp > 0:
            return 10.0 / mpp
        return None

    def read_region(
        self, location: Tuple[int, int], level: int, size: Tuple[int, int]
    ) -> Image.Image:
        """Read a region from the slide."""
        if level != 0:
            raise ValueError("Bio-Formats VSI reader only supports level 0")

        x, y = location
        width, height = size

        try:
            # Read region using Bio-Formats
            if self._image_reader is None:
                raise RuntimeError("Bio-Formats reader is closed")

            img_array = self._image_reader.read(
                c=0,
                z=0,
                t=0,
                series=self._main_series,
                rescale=False,
                XYWH=(x, y, width, height),
            )

            return _array_to_image(img_array)

        except Exception as e:
            logger.error(f"Failed to read region {location} at level {level}: {e}")
            # Return a placeholder image
            placeholder = np.zeros((height, width, 3), dtype=np.uint8)
            return Image.fromarray(placeholder)

    def read_biomarker_region(
        self,
        location: Tuple[int, int],
        level: int,
        size: Tuple[int, int],
        biomarker: str,
    ) -> Image.Image:
        if level != 0:
            raise ValueError("Bio-Formats VSI reader only supports level 0")
        if biomarker not in self._biomarker_to_channel:
            raise UnknownBiomarkerError(
                f"Biomarker '{biomarker}' not found. Available: {self.list_biomarkers()}"
            )
        if self._image_reader is None:
            raise RuntimeError("Bio-Formats reader is closed")

        x, y = location
        width, height = size
        channel = self._biomarker_to_channel[biomarker]
        img_array = self._image_reader.read(
            c=channel,
            z=0,
            t=0,
            series=self._main_series,
            rescale=False,
            XYWH=(x, y, width, height),
        )
        return _array_to_image(img_array)

    def read_region_biomarker(
        self,
        location: Tuple[int, int],
        level: int,
        size: Tuple[int, int],
        biomarker: str,
    ) -> Image.Image:
        return self.read_biomarker_region(location, level, size, biomarker)

    def get_best_level_for_downsample(self, downsample: float) -> int:
        """Get the best level for a given downsample factor."""
        # With Bio-Formats, we only have level 0
        return 0

    def get_thumbnail(self, size: Tuple[int, int]) -> Image.Image:
        """Get a thumbnail of the slide."""
        thumb_width, thumb_height = size
        slide_width, slide_height = self._dimensions

        # Calculate scale factor
        scale_x = slide_width / thumb_width
        scale_y = slide_height / thumb_height
        scale = max(scale_x, scale_y)

        # Calculate the size to read at reduced resolution
        read_width = min(int(slide_width / scale), slide_width)
        read_height = min(int(slide_height / scale), slide_height)

        # For efficiency, read a smaller region and then resize
        # Use a maximum read size to avoid memory issues
        max_read_size = 2048
        if read_width > max_read_size or read_height > max_read_size:
            read_scale = max(read_width / max_read_size, read_height / max_read_size)
            read_width = int(read_width / read_scale)
            read_height = int(read_height / read_scale)

        # Read from the center of the image for better representation
        start_x = max(0, (slide_width - read_width) // 2)
        start_y = max(0, (slide_height - read_height) // 2)

        region = self.read_region((start_x, start_y), 0, (read_width, read_height))

        # Resize to requested thumbnail size
        return region.resize(size, Image.Resampling.LANCZOS)

    @classmethod
    def detect_format(cls, filename) -> Optional[str]:
        if _bioformats is None or _javabridge is None:
            return None

        try:
            if not str(filename).lower().endswith(".vsi"):
                return None

            with open(filename, "rb") as f:
                header = f.read(8)
                if len(header) == 8 and header[:4] in [b"II*\x00", b"MM\x00*"]:
                    return "cellSens VSI (Bio-Formats)"
        except (OSError, IOError):
            pass

        return None

    def close(self):
        """Close the slide and clean up resources."""
        if self._image_reader:
            try:
                self._image_reader.close()
            except:
                pass
            self._image_reader = None

        # Clean up Java VM if we started it
        if self._java_started:
            try:
                if _javabridge is not None and _javabridge.get_env():
                    _javabridge.kill_vm()
                    logger.info("Java VM cleaned up by Bio-Formats VSI slide")
            except:
                pass
            self._java_started = False
