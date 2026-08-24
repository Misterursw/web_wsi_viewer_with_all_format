# Examples

These examples are adapted from `example_test_case.py` and focus on public ASlide APIs.

## Inspect Basic Metadata

```python
from Aslide import Slide

with Slide("sample.svs") as slide:
    print("format", slide.format)
    print("family", slide.slide_family)
    print("dimensions", slide.dimensions)
    print("levels", slide.level_count)
    print("level dimensions", slide.level_dimensions)
    print("downsamples", slide.level_downsamples)
    print("mpp", getattr(slide, "mpp", None))
```

## Export a Brightfield Region

```python
with Slide("sample.svs") as slide:
    region = slide.read_region((0, 0), 0, (512, 512))
    region.save("region.png")
```

## Export a Thumbnail

```python
with Slide("sample.ndpi") as slide:
    thumbnail = slide.get_thumbnail((500, 500))
    thumbnail.save("thumbnail.png")
```

## List Associated Images

```python
with Slide("sample.kfb") as slide:
    for name, image in slide.associated_images.items():
        print(name, getattr(image, "size", None))
```

## Pick the Best Level for a Downsample

```python
with Slide("sample.svs") as slide:
    for downsample in (4, 16, 64):
        print(downsample, slide.get_best_level_for_downsample(downsample))
```

## Export DeepZoom Metadata and a Tile

```python
from Aslide import DeepZoom, Slide

with Slide("sample.svs") as slide:
    dz = DeepZoom(slide)
    with open("sample.dzi", "w", encoding="utf-8") as handle:
        handle.write(dz.get_dzi("jpeg"))
    dz.get_tile(dz.level_count // 2, (0, 0)).save("tile.jpg")
```

## Export Multiplex Biomarkers

```python
with Slide("sample.qptiff") as slide:
    for marker in slide.list_biomarkers():
        region = slide.read_biomarker_region((0, 0), 0, (512, 512), marker)
        region.save(f"{marker}.png")
```

## Choose an MCD Acquisition

```python
with Slide("sample.mcd", acquisition_id=2) as slide:
    print(slide.properties.get("mcd.selected-acquisition-id"))
    print(slide.properties.get("mcd.selected-acquisition-description"))
    print(slide.list_biomarkers()[:5])
```

## Inspect SDPC-Specific Metadata

Some SDPC functionality is exposed on the backend object.

```python
with Slide("sample.sdpc") as slide:
    print(slide.backend.get_barcode())
    print(slide.backend.get_slide_type())
    print(slide.backend.get_channel_count())
    print(slide.backend.get_plane_count())
    print(slide.backend.get_plane_space_between())
    print(slide.backend.get_tile_size())
```

## Apply Color Correction When Supported

```python
with Slide("sample.sdpc") as slide:
    slide.apply_color_correction(apply=True, style="Real")
```

## Save a Label Image

```python
with Slide("sample.sdpc") as slide:
    slide.label_image(save_path="label.png")
```
