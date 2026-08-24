# Multiplex Slides

Multiplex slides store independent biomarker or channel data. ASlide exposes them through explicit channel reads instead of generic RGB reads.

## Family Semantics

For multiplex slides:

```python
slide.slide_family == "multiplex"
```

Multiplex slides support `list_biomarkers()`, `get_default_display_biomarker()`, and `read_biomarker_region()`. Generic `read_region()` is rejected so callers must choose the intended channel.

## Biomarker Reads

```python
from Aslide import Slide

with Slide("sample.qptiff") as slide:
    biomarkers = slide.list_biomarkers()
    marker = biomarkers[0]
    region = slide.read_biomarker_region((0, 0), 0, (512, 512), marker)
```

`read_biomarker_region(location, level, size, biomarker)` returns an RGBA image. `slide.supports_biomarkers` is true for multiplex slides even when static registry capabilities are conservative for runtime-classified formats.

## Default Display Biomarker

Some backends define a default display channel. QPTIFF commonly uses `DAPI` as the default display biomarker. IMS and other multiplex backends may derive a default from channel metadata.

```python
with Slide("sample.ims") as slide:
    marker = slide.get_default_display_biomarker()
    region = slide.read_biomarker_region((0, 0), 0, (512, 512), marker)
```

If no stable default exists, ASlide raises `MissingDefaultBiomarkerError`.

## Runtime-Classified Formats

QPTIFF and CZI are classified after the file is opened. A brightfield QPTIFF behaves like an ordinary brightfield slide. A multiplex QPTIFF requires biomarker-aware reads.

```python
with Slide("sample.qptiff") as slide:
    if slide.slide_family == "brightfield":
        region = slide.read_region((0, 0), 0, (512, 512))
    else:
        marker = slide.get_default_display_biomarker()
        region = slide.read_biomarker_region((0, 0), 0, (512, 512), marker)
```

CZI support can use the lightweight `czi` extra or the Bio-Formats path. Metadata determines whether the opened file behaves as brightfield or multiplex.

## TIFF, HDF5, H5AD, IMS, and MCD

Opening an OME-like TIFF anchor file can resolve to a multiplex backend when the file contains compatible marker/channel data. Generic `.tif` and `.tiff` files still fall back to ordinary TIFF behavior when they do not match the multiplex probe.

Image-backed `.h5`, `.hdf5`, and `.h5ad` containers resolve to multiplex behavior when they expose a direct channel-by-height-by-width raster plus marker metadata. Table-only AnnData `.h5ad` files are not reconstructed into slides by this path.

IMS files use a dedicated multiplex backend that reads channel metadata and pyramid levels directly from the IMS container.

MCD files use `readimc`. When an MCD file contains multiple acquisitions, ASlide selects the largest acquisition by pixel area by default and stores selected acquisition metadata in `slide.properties`. Pass `acquisition_id=<id>` to choose a specific acquisition.

```python
with Slide("sample.mcd", acquisition_id=2) as slide:
    print(slide.properties.get("mcd.selected-acquisition-description"))
    print(slide.list_biomarkers()[:5])
```
