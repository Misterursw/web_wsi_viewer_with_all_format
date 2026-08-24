# Brightfield Slides

Brightfield slides expose the classic whole-slide image workflow: pyramid metadata, generic region reads, thumbnails, and optional associated images.

## Family Semantics

For brightfield slides:

```python
slide.slide_family == "brightfield"
```

Brightfield formats include OpenSlide-backed SVS, SVSLIDE, NDPI, VMS, VMU, SCN, and MRXS inputs, plus several native SDK formats when their backends expose ordinary RGB imagery.

## Core Metadata

```python
from Aslide import Slide

with Slide("sample.svs") as slide:
    print(slide.dimensions)
    print(slide.level_count)
    print(slide.level_dimensions)
    print(slide.level_downsamples)
    print(slide.properties)
```

`slide.mpp` returns microns-per-pixel when the backend exposes it or when OpenSlide metadata contains MPP fields. `slide.magnification` returns the backend magnification value when available.

## Region Reads

```python
with Slide("sample.svs") as slide:
    region = slide.read_region((10_000, 20_000), 0, (1024, 1024))
```

`read_region(location, level, size)` returns an RGBA image. The `location` is given in level-0 coordinates.

Some backends also expose `read_fixed_region(location, level, size)`. ASlide keeps it as a brightfield-only helper and rejects it for multiplex slides.

## Thumbnails and Levels

```python
with Slide("sample.svs") as slide:
    thumbnail = slide.get_thumbnail((500, 500))
    level = slide.get_best_level_for_downsample(16)
```

`get_thumbnail(size)` is brightfield-only. Multiplex slides need a biomarker-aware display path instead.

## Associated and Label Images

```python
with Slide("sample.kfb") as slide:
    for name, image in slide.associated_images.items():
        print(name, getattr(image, "size", None))
    label = slide.label_image()
```

Associated image availability is backend-dependent. `label_image(save_path=None)` first uses backend-specific label APIs, then falls back to associated image data when available. Some backends require `save_path` for label extraction.

## Color Correction

Some native backends support color correction. ASlide exposes the common facade method:

```python
with Slide("sample.sdpc") as slide:
    slide.apply_color_correction(apply=True, style="Real")
```

If the backend does not support color correction, ASlide raises `NotImplementedError`.
