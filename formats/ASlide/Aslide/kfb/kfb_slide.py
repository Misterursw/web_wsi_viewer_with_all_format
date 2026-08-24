import io
from typing import Optional
from PIL import Image
from openslide import AbstractSlide, _OpenSlideMap

from . import kfb_lowlevel
from .color_correction import ColorCorrection


class kfbRef:
    img_count = 0


class KfbSlide(AbstractSlide):
    def __init__(self, filename):
        AbstractSlide.__init__(self)
        self.__filename = filename
        self._osr = kfb_lowlevel.kfbslide_open(filename)
        # Color correction
        self._color_correction = ColorCorrection(style="Real")

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, self.__filename)

    @classmethod
    def detect_format(cls, filename):
        """Detect if file is KFB format"""
        vendor = kfb_lowlevel.detect_vendor(filename)
        if vendor:
            # Convert bytes to string if needed
            if isinstance(vendor, bytes):
                return vendor.decode("utf-8", "replace")
            return str(vendor) if vendor else None
        return None

    def close(self):
        kfb_lowlevel.kfbslide_close(self._osr)

    @property
    def level_count(self):
        return kfb_lowlevel.kfbslide_get_level_count(self._osr)

    @property
    def dimensions(self):
        """Return the dimensions of the highest resolution level (level 0)."""
        return self.level_dimensions[0] if self.level_dimensions else (0, 0)

    @property
    def level_dimensions(self):
        return tuple(
            kfb_lowlevel.kfbslide_get_level_dimensions(self._osr, i)
            for i in range(self.level_count)
        )

    @property
    def level_downsamples(self):
        return tuple(
            kfb_lowlevel.kfbslide_get_level_downsample(self._osr, i)
            for i in range(self.level_count)
        )

    @property
    def mpp(self):
        """Microns per pixel"""
        try:
            # Try to get mpp from properties
            props = self.properties
            if "openslide.mpp-x" in props:
                return float(props["openslide.mpp-x"])
        except:
            pass
        return None

    @property
    def magnification(self) -> Optional[float]:
        """Get slide magnification"""
        try:
            # Check properties for common keys
            props = self.properties
            for key in ["openslide.objective-power", "Magnification"]:
                if key in props:
                    return float(props[key])

            # Fallback to mpp-based calculation
            mpp = self.mpp
            if mpp and mpp > 0:
                return 10.0 / mpp
        except:
            pass
        return None

    @property
    def properties(self):
        return _KfbPropertyMap(self._osr)

    @property
    def associated_images(self):
        return _AssociatedImageMap(self._osr)

    def get_best_level_for_downsample(self, downsample):
        return kfb_lowlevel.kfbslide_get_best_level_for_downsample(
            self._osr, downsample
        )

    def read_fixed_region(self, location, level, size):
        """
        Read a fixed region from the slide (tile-based reading)

        Args:
            location: (x, y) tuple of the top-left corner in level 0 coordinates
            level: pyramid level to read from
            size: (width, height) tuple of the region size (not used in this method)

        Returns:
            PIL Image object
        """
        x = int(location[0])
        y = int(location[1])
        img_index = kfbRef.img_count
        kfbRef.img_count += 1
        print("img_index : ", img_index, "Level : ", level, "Location : ", x, y)

        # Convert level-0 coordinates to level-specific coordinates
        # KFB SDK expects coordinates in the current level's coordinate system,
        # not level 0 coordinates (similar to SDPC format, different from OpenSlide)
        downsample = self.level_downsamples[level]
        level_x = int(x / downsample)
        level_y = int(y / downsample)

        return kfb_lowlevel.kfbslide_read_region(self._osr, level, level_x, level_y)

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
        x = int(location[0])
        y = int(location[1])
        width = int(size[0])
        height = int(size[1])
        img_index = kfbRef.img_count
        kfbRef.img_count += 1

        # Convert level-0 coordinates to level-specific coordinates
        # KFB SDK expects coordinates in the current level's coordinate system,
        # not level 0 coordinates (similar to SDPC format, different from OpenSlide)
        downsample = self.level_downsamples[level]
        level_x = int(x / downsample)
        level_y = int(y / downsample)

        # Pass the level-specific coordinates to the underlying function
        result = kfb_lowlevel.kfbslide_read_roi_region(
            self._osr, level, level_x, level_y, width, height
        )

        # Apply color correction if enabled
        result = self._color_correction.apply(result)

        return result

    def apply_color_correction(self, apply: bool = True, style: str = "Real"):
        """Apply or disable color correction.

        Args:
            apply: Whether to apply color correction
            style: Color correction style ("Real")
        """
        self._color_correction.enabled = apply
        if style:
            self._color_correction.set_style(style)

    def get_color_correction_info(self) -> dict[str, object]:
        """Get current color correction parameters."""
        return self._color_correction.get_info()

    def get_thumbnail(self, size):
        """Return a PIL.Image containing an RGB thumbnail of the image."""
        thumb = self.read_region(
            (0, 0), self.level_count - 1, self.level_dimensions[-1]
        )
        thumb = thumb.resize(size=size, resample=Image.Resampling.LANCZOS)
        return thumb


class _KfbPropertyMap(_OpenSlideMap[str]):
    def _keys(self):
        return kfb_lowlevel.kfbslide_property_names(self._osr)

    def __getitem__(self, key):
        v = kfb_lowlevel.kfbslide_property_value(self._osr, key)
        if v is None:
            raise KeyError()
        return v


class _AssociatedImageMap(_OpenSlideMap[Image.Image]):
    def _keys(self):
        return kfb_lowlevel.kfbslide_get_associated_image_names(self._osr)

    def __getitem__(self, key):
        if key not in self._keys():
            raise KeyError()
        return kfb_lowlevel.kfbslide_read_associated_image(self._osr, key)


def open_kfbslide(filename):
    try:
        return KfbSlide(filename)
    except Exception:
        return None


def main():
    kfb_file_path = "path/to/kfb/file"
    slide = KfbSlide(kfb_file_path)
    print("Format : ", slide.detect_format(kfb_file_path))
    print("level_count : ", slide.level_count)
    print("level_dimensions : ", slide.level_dimensions)
    print("level_downsamples : ", slide.level_downsamples)
    print("properties : ", slide.properties)
    print("Associated Images : ")
    for key, val in slide.associated_images.items():
        print(key, " --> ", val)

    print("best level for downsample 20 : ", slide.get_best_level_for_downsample(20))
    im = slide.read_region((1000, 1000), 4, (1000, 1000))
    print(im.mode)
    im.show()
    im.close()


if __name__ == "__main__":
    main()
