"""
BIF (Ventana BigTIFF) file format reader.

Supports Ventana DP 600 / DP 200 scanner BIF files that have
Direction="LEFT"/"DOWN" attributes which OpenSlide doesn't support.

Uses tifffile for reading BigTIFF structure directly.
"""

import os
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple, Any

from PIL import Image
from openslide import AbstractSlide

try:
    import tifffile as _tifffile
except ImportError:
    _tifffile = None


class BifSlide(AbstractSlide):
    """
    BIF slide reader for Ventana BigTIFF files.

    BIF file structure:
    - Page 0: Label image (RGB, uncompressed)
    - Page 1: Probability/mask image (grayscale, LZW)
    - Page 2+: Pyramid levels (tiled JPEG YCbCr)
    """

    def __init__(self, filename: str):
        """Initialize BIF slide reader."""
        AbstractSlide.__init__(self)

        if _tifffile is None:
            raise ImportError(
                "tifffile is required for BIF support. Install with: pip install tifffile"
            )

        if not os.path.exists(filename):
            raise FileNotFoundError(f"BIF file not found: {filename}")

        self._filename: str = filename
        self._tiff: Any = None
        self._levels: List[Tuple[int, int]] = []
        self._level_pages: List[int] = []  # Map level index to page index
        self._properties: Dict[str, str] = {}
        self._associated_images: Dict[str, Image.Image] = {}

        self._open()

    def _open(self):
        """Open and parse the BIF file."""
        tifffile_module = _tifffile
        if tifffile_module is None:
            return
        self._tiff = tifffile_module.TiffFile(self._filename)

        # Parse pages to find pyramid levels and associated images
        for i, page in enumerate(self._tiff.pages):
            tags = getattr(page, "tags", None)
            desc = tags.get(270) if tags is not None else None
            desc_value = desc.value if desc is not None else ""

            if desc_value == "Label_Image":
                # Label image - may contain combined label+macro
                self._load_label_macro_image(page)
            elif desc_value == "Probability_Image":
                # Skip probability/mask image
                continue
            elif desc_value.startswith("level="):
                # Pyramid level
                self._level_pages.append(i)
                h, w = page.shape[:2]
                self._levels.append((w, h))

        # Parse metadata from XMLPacket (tag 700)
        self._parse_metadata()

        # Generate thumbnail from lowest resolution level
        self._generate_thumbnail()

        # Generate macro from lowest resolution level if not already present
        self._generate_macro()

    def _load_label_macro_image(self, page: Any):
        """Load label and macro images from Label_Image page.

        Ventana BIF files store a combined label+macro image in the Label_Image page.
        The label is typically a small barcode area, while macro shows the whole slide.
        For this implementation, we store the full image as 'label' and also provide
        it as 'macro' since it typically shows the slide overview.
        """
        try:
            data = page.asarray()
            if len(data.shape) == 3 and data.shape[2] == 3:
                img = Image.fromarray(data, mode="RGB")
            elif len(data.shape) == 2:
                img = Image.fromarray(data, mode="L")
            else:
                img = Image.fromarray(data)

            # Store as label
            self._associated_images["label"] = img

            # For Ventana BIF, the Label_Image typically shows the slide with barcode
            # Use the same image as macro (it's the slide overview)
            self._associated_images["macro"] = img.copy()
        except Exception:
            pass

    def _load_associated_image(self, page: Any, name: str):
        """Load an associated image from a TIFF page."""
        try:
            data = page.asarray()
            if len(data.shape) == 3 and data.shape[2] == 3:
                img = Image.fromarray(data, mode="RGB")
            elif len(data.shape) == 2:
                img = Image.fromarray(data, mode="L")
            else:
                img = Image.fromarray(data)
            self._associated_images[name] = img
        except Exception:
            pass

    def _parse_metadata(self):
        """Parse metadata from XMLPacket."""
        if self._tiff is None or not self._tiff.pages:
            return

        page0 = self._tiff.pages[0]
        tags = getattr(page0, "tags", None)
        xml_tag = tags.get(700) if tags is not None else None  # XMLPacket
        if not xml_tag:
            return

        try:
            xml_data = xml_tag.value
            if isinstance(xml_data, bytes):
                xml_data = xml_data.decode("utf-8", errors="ignore").rstrip("\x00")
            elif not isinstance(xml_data, str):
                xml_data = str(xml_data)

            root = ET.fromstring(xml_data)
            iscan = root.find(".//iScan")

            if iscan is not None:
                self._properties["openslide.vendor"] = "ventana"

                # Extract key attributes
                for attr in [
                    "Magnification",
                    "ScanRes",
                    "ScannerModel",
                    "Mode",
                    "Barcode1D",
                    "Barcode2D",
                    "UnitNumber",
                ]:
                    val = iscan.get(attr)
                    if val:
                        self._properties[f"ventana.{attr}"] = val

                # MPP (microns per pixel)
                scan_res = iscan.get("ScanRes")
                if scan_res:
                    try:
                        mpp = float(scan_res)
                        self._properties["openslide.mpp-x"] = str(mpp)
                        self._properties["openslide.mpp-y"] = str(mpp)
                    except ValueError:
                        pass

                # Magnification
                mag = iscan.get("Magnification")
                if mag:
                    self._properties["openslide.objective-power"] = mag
        except Exception:
            pass

        # Add level count
        self._properties["openslide.level-count"] = str(len(self._levels))

    def _generate_thumbnail(self):
        """Generate thumbnail from the lowest resolution level."""
        if not self._level_pages:
            return

        try:
            # Use the lowest resolution level
            lowest_level_page = self._level_pages[-1]
            tiff = self._tiff
            if tiff is None:
                return
            page = tiff.pages[lowest_level_page]
            data = page.asarray()

            if len(data.shape) == 3:
                img = Image.fromarray(data, mode="RGB")
            else:
                img = Image.fromarray(data)

            # Resize to reasonable thumbnail size
            max_dim = 1024
            if max(img.size) > max_dim:
                ratio = max_dim / max(img.size)
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            self._associated_images["thumbnail"] = img
        except Exception:
            pass

    def _generate_macro(self):
        """Generate macro image from the lowest resolution level if not present."""
        if "macro" in self._associated_images:
            return  # Already have macro

        if not self._level_pages:
            return

        try:
            # Use the lowest resolution level as macro
            lowest_level_page = self._level_pages[-1]
            tiff = self._tiff
            if tiff is None:
                return
            page = tiff.pages[lowest_level_page]
            data = page.asarray()

            if len(data.shape) == 3:
                img = Image.fromarray(data, mode="RGB")
            else:
                img = Image.fromarray(data)

            self._associated_images["macro"] = img
        except Exception:
            pass

    def __repr__(self):
        return f"{self.__class__.__name__}({self._filename!r})"

    @classmethod
    def detect_format(cls, filename) -> Optional[str]:
        try:
            with open(filename, "rb") as f:
                magic = f.read(4)
                if magic == b"II+\x00" or magic == b"MM\x00+":
                    f.seek(0)
                    if _tifffile is None:
                        return None
                    tiff = _tifffile.TiffFile(f)
                    for page in tiff.pages[:5]:
                        tags = getattr(page, "tags", None)
                        xml_tag = tags.get(700) if tags is not None else None
                        if xml_tag is not None:
                            xml_data = xml_tag.value
                            if isinstance(xml_data, bytes):
                                xml_data = xml_data.decode("utf-8", errors="ignore")
                            elif not isinstance(xml_data, str):
                                xml_data = str(xml_data)
                            if "iScan" in xml_data or "Ventana" in xml_data.upper():
                                return "ventana-bif"
            return None
        except Exception:
            return None

    def close(self):
        """Close the slide."""
        if self._tiff is not None:
            self._tiff.close()
            self._tiff = None
        self._associated_images.clear()

    def __del__(self):
        self.close()

    @property
    def dimensions(self) -> Tuple[int, int]:
        """Dimensions (width, height) at level 0."""
        if self._levels:
            return self._levels[0]
        return (0, 0)

    @property
    def level_count(self) -> int:
        """Number of pyramid levels."""
        return len(self._levels)

    @property
    def magnification(self) -> Optional[float]:
        """Get slide magnification."""
        try:
            # Check properties
            props = self.properties
            mag = props.get("openslide.objective-power")
            if mag:
                return float(mag)

            # Fallback to MPP calculation
            mpp = self.mpp
            if mpp and mpp > 0:
                return 10.0 / mpp
        except:
            pass
        return None

    @property
    def level_dimensions(self) -> Tuple[Tuple[int, int], ...]:
        """Dimensions at each pyramid level."""
        return tuple(self._levels)

    @property
    def level_downsamples(self) -> Tuple[float, ...]:
        """Downsample factor for each level."""
        if not self._levels:
            return (1.0,)
        base_width = self._levels[0][0]
        return tuple(base_width / w if w > 0 else 1.0 for w, _ in self._levels)

    @property
    def properties(self) -> Dict[str, str]:
        """Slide properties."""
        return self._properties.copy()

    @property
    def associated_images(self) -> Dict[str, Image.Image]:
        """Associated images (label, thumbnail, macro)."""
        return self._associated_images

    @property
    def mpp(self) -> Optional[float]:
        """Microns per pixel."""
        mpp_str = self._properties.get("openslide.mpp-x")
        if mpp_str:
            try:
                return float(mpp_str)
            except ValueError:
                pass
        return None

    def get_best_level_for_downsample(self, downsample: float) -> int:
        """Find the best level for a given downsample factor."""
        downsamples = self.level_downsamples
        for i, ds in enumerate(downsamples):
            if ds >= downsample:
                return max(0, i - 1) if i > 0 else 0
        return len(downsamples) - 1

    def read_region(
        self, location: Tuple[int, int], level: int, size: Tuple[int, int]
    ) -> Image.Image:
        """Read a region from the slide.

        Args:
            location: (x, y) tuple giving the top left pixel in the level 0 reference frame
            level: The level number
            size: (width, height) tuple giving the region size

        Returns:
            PIL.Image in RGBA mode
        """
        if level < 0 or level >= len(self._level_pages):
            # Return blank image for invalid level
            return Image.new("RGBA", size, (255, 255, 255, 255))

        page_idx = self._level_pages[level]
        if self._tiff is None:
            return Image.new("RGBA", size, (255, 255, 255, 255))

        page = self._tiff.pages[page_idx]

        downsample = self.level_downsamples[level]

        # Convert level 0 coordinates to this level's coordinates
        x = int(location[0] / downsample)
        y = int(location[1] / downsample)
        width, height = size

        # Get page dimensions
        page_height, page_width = page.shape[:2]

        # Clamp coordinates
        x = max(0, min(x, page_width - 1))
        y = max(0, min(y, page_height - 1))

        # Calculate actual region to read
        x_end = min(x + width, page_width)
        y_end = min(y + height, page_height)
        actual_width = x_end - x
        actual_height = y_end - y

        if actual_width <= 0 or actual_height <= 0:
            return Image.new("RGBA", size, (255, 255, 255, 255))

        try:
            # Read region using tifffile
            # For tiled images, tifffile handles tile reading automatically
            region_data = page.asarray()[y:y_end, x:x_end]

            # Convert to PIL Image
            if len(region_data.shape) == 3 and region_data.shape[2] == 3:
                img = Image.fromarray(region_data, mode="RGB")
            elif len(region_data.shape) == 2:
                img = Image.fromarray(region_data, mode="L").convert("RGB")
            else:
                img = Image.fromarray(region_data)

            # Convert to RGBA
            if img.mode != "RGBA":
                img = img.convert("RGBA")

            # If we read a smaller region than requested, paste into full-size image
            if img.size != size:
                result = Image.new("RGBA", size, (255, 255, 255, 255))
                result.paste(img, (0, 0))
                return result

            return img

        except Exception as e:
            # Return blank image on error
            return Image.new("RGBA", size, (255, 255, 255, 255))

    def get_thumbnail(self, size: Tuple[int, int] = (256, 256)) -> Image.Image:
        """Get a thumbnail image."""
        thumb = self._associated_images.get("thumbnail")
        if thumb is not None:
            thumb = thumb.copy()
            thumb.thumbnail(size, Image.Resampling.LANCZOS)
            return thumb
        return Image.new("RGB", size, (255, 255, 255))
