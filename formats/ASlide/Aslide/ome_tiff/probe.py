from __future__ import annotations

from pathlib import Path

import tifffile


def is_ome_tiff_candidate(path: str) -> bool:
    file_path = Path(path)
    if file_path.suffix.lower() not in {".tif", ".tiff"}:
        return False

    with tifffile.TiffFile(path) as tiff:
        if tiff.is_ome:
            return True
        page = tiff.pages[0]
        software = page.tags.get("Software")
        page_name = page.tags.get("PageName")
        software_value = str(software.value).lower() if software else ""
        page_name_value = str(page_name.value) if page_name else ""
        return "fluidigm mcd viewer" in software_value and bool(page_name_value)
