"""
Color Correction module for MDS/MDSX format.

Uses ICC color profile (real.icm) to apply color correction.
The ICC profile is a standard color management format that can be applied
using PIL's ImageCms module.
"""

import os
from typing import Optional, Dict
from PIL import Image

try:
    from PIL import ImageCms as _ImageCms
except ImportError:
    _ImageCms = None


class ColorCorrection:
    """Color correction processor for MDS/MDSX images using ICC profile."""

    # Default ICC directory (relative to this file)
    ICC_DIR = os.path.join(os.path.dirname(__file__), "icc")

    # Predefined ICC profiles (aligned with SDPC/DYJ/KFB naming)
    PROFILES = {
        "Real": "real.icm",
    }

    def __init__(self, style: str = "Real", icc_path: Optional[str] = None):
        """Initialize color correction with an ICC profile.

        Args:
            style: Predefined style name ('Real')
            icc_path: Custom ICC profile path (overrides style if provided)
        """
        self._enabled = False
        self._style = style
        self._transform = None
        self._icc_profile = None

        if _ImageCms is None:
            print("Warning: PIL.ImageCms not available. Color correction disabled.")
            return

        # Load ICC profile
        if icc_path:
            self._load_icc(icc_path)
        elif style in self.PROFILES:
            icc_file = os.path.join(self.ICC_DIR, self.PROFILES[style])
            if os.path.exists(icc_file):
                self._load_icc(icc_file)

    def _load_icc(self, icc_path: str):
        """Load ICC profile and create color transform.

        Args:
            icc_path: Path to the ICC profile file
        """
        if _ImageCms is None:
            return

        try:
            # Load the ICC profile
            self._icc_profile = _ImageCms.getOpenProfile(icc_path)

            # Create sRGB profile as output
            srgb_profile = _ImageCms.createProfile("sRGB")

            # Create transform from device RGB to sRGB
            self._transform = _ImageCms.buildTransform(
                self._icc_profile,
                srgb_profile,
                "RGB",
                "RGB",
                renderingIntent=_ImageCms.Intent.PERCEPTUAL,
            )
        except Exception as e:
            print(f"Warning: Failed to load ICC profile {icc_path}: {e}")
            self._transform = None

    @property
    def enabled(self) -> bool:
        """Check if color correction is enabled."""
        return self._enabled and self._transform is not None

    @enabled.setter
    def enabled(self, value: bool):
        """Enable or disable color correction."""
        self._enabled = value

    @property
    def style(self) -> str:
        """Get current style name."""
        return self._style

    def set_style(self, style: str):
        """Change color correction style.

        Args:
            style: Style name ('Real')
        """
        if style in self.PROFILES:
            icc_file = os.path.join(self.ICC_DIR, self.PROFILES[style])
            if os.path.exists(icc_file):
                self._load_icc(icc_file)
                self._style = style

    def apply(self, image: Image.Image) -> Image.Image:
        """Apply color correction to an image.

        Args:
            image: Input PIL Image (RGB or RGBA)

        Returns:
            Color-corrected PIL Image
        """
        if not self._enabled or self._transform is None:
            return image

        try:
            # Handle RGBA images
            has_alpha = image.mode == "RGBA"
            alpha_channel = None
            if has_alpha:
                # Split alpha channel
                r, g, b, alpha_channel = image.split()
                rgb_image = Image.merge("RGB", (r, g, b))
            else:
                rgb_image = image.convert("RGB") if image.mode != "RGB" else image

            # Apply ICC transform
            transform = self._transform
            if _ImageCms is None or transform is None:
                return image
            corrected = _ImageCms.applyTransform(rgb_image, transform)
            if corrected is None:
                return image

            # Restore alpha channel if needed
            if has_alpha and alpha_channel is not None:
                r, g, b = corrected.split()
                return Image.merge("RGBA", (r, g, b, alpha_channel))
            else:
                return corrected

        except Exception as e:
            print(f"Warning: Color correction failed: {e}")
            return image

    def get_info(self) -> Dict[str, object]:
        """Get color correction parameters info."""
        return {
            "enabled": self._enabled,
            "style": self._style,
            "has_transform": self._transform is not None,
            "has_imagecms": _ImageCms is not None,
        }
