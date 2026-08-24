# DeepZoom

`DeepZoom` provides DZI metadata and tile extraction for viewer workflows. It wraps backend-specific DeepZoom generators when available and falls back to OpenSlide's generator for OpenSlide-compatible brightfield slides.

## Constructor

```python
from Aslide import DeepZoom, Slide

with Slide("sample.svs") as slide:
    dz = DeepZoom(
        slide,
        tile_size=254,
        overlap=1,
        limit_bounds=False,
        biomarker=None,
    )
```

Parameters:

- `slide`: an ASlide `Slide` instance
- `tile_size`: tile edge size, default `254`
- `overlap`: overlap in pixels between adjacent tiles, default `1`
- `limit_bounds`: passed to the backend generator when supported
- `max_level_size`: accepted for compatibility; current facade does not use it directly
- `biomarker`: optional biomarker for multiplex slides

## Properties

- `backend`: concrete DeepZoom backend
- `biomarker`: selected biomarker for biomarker-aware backends, otherwise `None`
- `tile_size`: backend tile size
- `level_count`: number of DeepZoom levels
- `level_tiles`: tile grid shape per level
- `level_dimensions`: pixel dimensions per level
- `tile_count`: total tile count

## DZI and Tile Reads

```python
with Slide("sample.svs") as slide:
    dz = DeepZoom(slide)
    dzi_xml = dz.get_dzi("jpeg")
    tile = dz.get_tile(0, (0, 0))
```

`get_dzi(image_format)` returns Deep Zoom Image XML for the chosen image format. `get_tile(level, address)` returns a tile image for `(column, row)` at the requested DeepZoom level.

## Multiplex DeepZoom

For multiplex slides, pass a biomarker explicitly or let ASlide ask the slide for its default display biomarker.

```python
with Slide("sample.qptiff") as slide:
    dz = DeepZoom(slide, biomarker="DAPI")
    tile = dz.get_tile(0, (0, 0))
```

```python
with Slide("sample.ims") as slide:
    dz = DeepZoom(slide)
    print(dz.biomarker)
```

If a multiplex slide has no default display biomarker and the caller does not pass `biomarker`, construction raises `MissingDefaultBiomarkerError` through the slide facade.

## Alias

`ADeepZoomGenerator` is an alias for `DeepZoom` and is exported for compatibility.
