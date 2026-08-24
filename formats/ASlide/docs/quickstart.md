# Quick Start

ASlide keeps the public read path simple: create a `Slide`, inspect its family and metadata, read image data through the family-appropriate method, then close the slide. Use a context manager when possible.

## Brightfield Region Read

```python
from Aslide import Slide

with Slide("sample.svs") as slide:
    print(slide.slide_family)
    print(slide.dimensions)
    print(slide.level_count)
    region = slide.read_region((0, 0), 0, (512, 512))
```

Brightfield slides support generic region reads and thumbnails.

```python
with Slide("sample.ndpi") as slide:
    thumbnail = slide.get_thumbnail((500, 500))
    best_level = slide.get_best_level_for_downsample(16)
```

## Multiplex Region Read

Multiplex slides require an explicit biomarker. Generic `read_region()` is intentionally rejected for multiplex images so callers do not accidentally read the wrong channel.

```python
from Aslide import Slide

with Slide("sample.qptiff") as slide:
    biomarkers = slide.list_biomarkers()
    region = slide.read_biomarker_region((0, 0), 0, (512, 512), biomarkers[0])
```

Some containers can be classified at runtime. For example, QPTIFF and CZI files may behave as either brightfield or multiplex depending on metadata.

```python
with Slide("sample.qptiff") as slide:
    if slide.slide_family == "brightfield":
        region = slide.read_region((0, 0), 0, (512, 512))
    else:
        marker = slide.get_default_display_biomarker()
        region = slide.read_biomarker_region((0, 0), 0, (512, 512), marker)
```

## DeepZoom Tiles

```python
from Aslide import DeepZoom, Slide

with Slide("sample.svs") as slide:
    dz = DeepZoom(slide)
    dzi_xml = dz.get_dzi("jpeg")
    tile = dz.get_tile(0, (0, 0))
```

For multiplex slides, pass a biomarker or let ASlide resolve the default display biomarker when the backend defines one.

```python
with Slide("sample.ims") as slide:
    dz = DeepZoom(slide, biomarker=slide.get_default_display_biomarker())
    tile = dz.get_tile(0, (0, 0))
```

## Runtime Setup for Native SDKs

If a vendor SDK library cannot be loaded, initialize runtime library paths before opening slides.

```python
from Aslide.bootstrap import setup_runtime_environment

setup_runtime_environment()
```

See [Troubleshooting](troubleshooting.md) for details.
