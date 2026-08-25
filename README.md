# web_wsi_viewer_with_all_format

A server-side browser viewer for whole-slide imaging, multi-format pathology
files, and spatial omics overlays.

The repository combines three related components:

- A web-based WSI viewer for server-hosted slides.
- A unified slide-reading engine covering common and vendor-specific pathology
  formats.
- A spatial transcriptomics/proteomics viewer that overlays spot-level heatmaps
  on top of the source image.

## Why This Exists

Digital pathology workflows often run into three practical problems:

1. Slide formats are fragmented across scanner vendors and proprietary SDKs.
2. Whole-slide images are too large to casually move between machines.
3. Spatial omics predictions are usually inspected in notebooks, away from the
   original H&E morphology.

This project keeps the data on the server and exposes interactive viewing
through the browser.

## Components

### 1. WSI Viewer

`wsi_viewer/` is a lightweight browser-based digital microscope for server-side
whole-slide images.

Key capabilities:

- File-tree browsing for slide directories.
- Single-slide, dual-slide, and four-slide layouts.
- Synchronized pan and zoom across multiple slides.
- Real-time DeepZoom tile serving.
- Box annotation support.
- Convenient linking of related stains or serial sections from the same case.

The viewer is built on Flask, OpenSlide, and OpenSeadragon. Tiles are streamed
from the server, so large slides can be inspected from a laptop or tablet
without copying the raw files locally.

```bash
pip install flask openslide-python pillow

export WSI_ROOT=/path/to/your/wsi_slides
python3 wsi_viewer/app.py --port 5000
```

Then open:

```text
http://<server-ip>:5000
```

### 2. Format Engine

`formats/ASlide/` provides a unified WSI reading API based on the open-source
[ASlide](https://github.com/MrPeterJin/ASlide) project. It wraps OpenSlide
formats, vendor-specific SDK formats, and multiplex imaging containers behind a
single interface:

```python
from Aslide import Slide

with Slide("/path/to/slide.kfb") as slide:
    print(slide.dimensions)
    region = slide.read_region((0, 0), 0, (512, 512))
```

The same code path can be used for formats such as `.svs`, `.qptiff`, `.mcd`,
`.czi`, and many others.

| Family | Formats |
|---|---|
| Brightfield / OpenSlide | SVS, NDPI, SCN, MRXS, VMS, VMU, TIFF |
| Vendor-specific SDK formats | KFB, SDPC/DYQX, TMAP, MDS/MDSX, TRON, iSyntax, DYJ, iBL, ZYP, BIF |
| Multiplex imaging and spatial protein | QPTIFF, OME-TIFF, MCD, IMS, CZI, VSI, HDF5/H5AD |

Additional notes:

- Backend selection is handled through a registry and capability metadata.
- DeepZoom DZI and tile generation are available out of the box.
- Native Linux x86_64 `.so` libraries are bundled for several vendor formats,
  including SDPC, KFB, and OpenCV-backed readers.
- See `formats/ASlide/README.md` and `formats/ASlide/docs/` for more details.

### 3. Spot Studio

`spot_viewer/` is a server-side viewer for spatial transcriptomics or spatial
protein prediction results. It displays an H&E whole-slide image with a
spot/tile-level heatmap overlay.

Key capabilities:

- Zoomable source image with overlaid spot or tile measurements.
- Adjustable overlay opacity.
- Gene or protein-channel dropdown selection.
- Mean, median, and max aggregation options.
- Reusable structure for both transcript and protein predictions.

Expected input layout:

- One result directory per slide.
- `done.json` with slide-level metadata.
- `tiles.csv` with spot or tile coordinates.
- `pred_expr_selected.npz` with the expression or intensity matrix.

For protein data, channel intensities can be stored in the same matrix format
and treated like gene-level values by the viewer.

```bash
pip install flask openslide-python pillow numpy pandas

export VISUAL_ST_RESULTS_ROOT=/path/to/your/st_results
python3 spot_viewer/app.py --port 8787
```

Then open:

```text
http://<server-ip>:8787
```

## Who It Is For

| User | Recommended component |
|---|---|
| Pathology departments and digital pathology teams | Deploy `wsi_viewer/` on an internal server for browser-based slide review |
| Spatial omics researchers | Use `spot_viewer/` to compare predicted molecular patterns against morphology |
| Pathology AI engineers | Use `formats/ASlide/` as a unified reading layer for preprocessing and tile extraction |
| Platform engineers | Deploy the Flask services behind nginx or another internal gateway |

## Project Structure

```text
web_wsi_viewer_with_all_format/
├── wsi_viewer/          # General WSI viewer for OpenSlide-compatible formats
├── spot_viewer/         # Spatial omics spot heatmap viewer
└── formats/ASlide/      # Unified format engine with docs and native SDK files
```

The three components are independent and can be deployed separately.

## License

- `wsi_viewer/` and `spot_viewer/`: MIT
- `formats/ASlide/`: GPL 3.0, following the upstream
  [ASlide](https://github.com/MrPeterJin/ASlide) project and preserving its
  original license and attribution.
