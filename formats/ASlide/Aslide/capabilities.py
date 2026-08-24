from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BackendCapabilities:
    has_label_image: bool = False
    has_color_correction: bool = False
    has_associated_images: bool = True
    has_deepzoom: bool = False
    requires_bootstrap: bool = False
    supports_biomarkers: bool = False
    requires_explicit_channel_read: bool = False
    default_display_biomarker: str | None = None
