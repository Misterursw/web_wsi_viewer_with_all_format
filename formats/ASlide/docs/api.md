# API Reference

This page documents ASlide's public Python API. Backend-specific low-level SDK bindings are intentionally not treated as stable public API.

## Public Imports

```python
from Aslide import ADeepZoomGenerator, DeepZoom, FormatEntry, FormatRegistry, Slide, registry
```

## `Slide`

`Slide(filepath, acquisition_id=None)` opens a slide and selects the correct backend through the registry. `acquisition_id` is used by MCD inputs when the caller wants a specific acquisition.

Use `Slide` as a context manager when possible:

```python
from Aslide import Slide

with Slide("sample.svs") as slide:
    print(slide.dimensions)
```

### Properties

- `backend`: concrete backend object selected by the registry
- `format`: primary file extension from the registry entry, such as `.svs` or `.qptiff`
- `slide_family`: semantic family, usually `brightfield` or `multiplex`
- `qptiff_semantics`: QPTIFF semantic family, or `None` for non-QPTIFF inputs
- `supports_biomarkers`: true when biomarker-aware operations are available
- `mpp`: microns-per-pixel when the backend or metadata provides it
- `magnification`: backend magnification value when available
- `level_count`: number of pyramid levels
- `dimensions`: level-0 `(width, height)` dimensions
- `level_dimensions`: dimensions for all levels
- `level_downsamples`: downsample factor for each level
- `properties`: metadata dictionary or mapping from the backend
- `associated_images`: mapping of associated images; may synthesize `thumbnail` for brightfield slides

### Methods

- `classify_slide_family()`: returns the backend-resolved slide family when a backend supports runtime classification
- `label_image(save_path=None)`: returns or saves a label image when available
- `get_best_level_for_downsample(downsample)`: asks the backend for the closest pyramid level
- `get_thumbnail(size)`: returns a brightfield thumbnail
- `list_biomarkers()`: returns multiplex biomarker names
- `get_default_display_biomarker()`: returns a backend default display biomarker, or raises `MissingDefaultBiomarkerError` when none can be selected
- `read_biomarker_region(location, level, size, biomarker)`: reads a multiplex channel region as RGBA
- `read_region(location, level, size)`: reads a brightfield region as RGBA; multiplex slides raise `UnsupportedOperationError` and require `read_biomarker_region()` instead
- `read_fixed_region(location, level, size)`: reads a backend fixed brightfield region when supported
- `close()`: closes the backend
- `apply_color_correction(apply=True, style="Real")`: toggles backend color correction when supported

### Brightfield and Multiplex Guards

Brightfield-only methods reject multiplex slides. Multiplex-only methods reject brightfield slides. These guards prevent accidental reads through the wrong semantic API.

## `DeepZoom` and `ADeepZoomGenerator`

`DeepZoom(slide, tile_size=254, overlap=1, limit_bounds=False, max_level_size=10000, biomarker=None)` wraps the slide's DeepZoom backend.

Properties:

- `backend`
- `biomarker`
- `tile_size`
- `level_count`
- `level_tiles`
- `level_dimensions`
- `tile_count`

Methods:

- `get_dzi(image_format)`: returns DZI XML
- `get_tile(level, address)`: returns a tile image

`ADeepZoomGenerator` is an alias for `DeepZoom`.

## Registry API

`registry` is the default `FormatRegistry` built by `build_default_registry()`.

```python
from Aslide import registry

entry = registry.resolve_path("sample.svs")
print(entry.format_id)
```

`FormatRegistry` methods:

- `register(entry)`: adds or replaces a format entry by `format_id`
- `get(format_id)`: returns one entry or raises `LookupError`
- `entries()`: returns all entries as a tuple
- `resolve_path(path)`: selects a matching and available entry for a file path

`FormatEntry` fields:

- `format_id`
- `extensions`
- `slide_backend`
- `slide_family`
- `deepzoom_backend`
- `availability_check`
- `probe`
- `capabilities`

`FormatEntry` methods:

- `is_available()`
- `load_slide_backend()`
- `load_deepzoom_backend()`
- `create_slide(path, **kwargs)`
- `matches_path(path)`

## Backend Capabilities

`BackendCapabilities` describes static backend capabilities known before a file is opened:

- `has_label_image`
- `has_color_correction`
- `has_associated_images`
- `has_deepzoom`
- `requires_bootstrap`
- `supports_biomarkers`
- `requires_explicit_channel_read`
- `default_display_biomarker`

Runtime-classified formats may have conservative static capabilities and still expose multiplex behavior after opening a specific file.

## Runtime Bootstrap Helpers

```python
from Aslide.bootstrap import collect_library_paths, preload_shared_libraries, setup_runtime_environment
```

- `collect_library_paths(package_root=None)`: returns package library directories for OpenCV, SDPC, KFB, and TRON when present
- `setup_runtime_environment(lib_paths=None)`: prepends library paths to `LD_LIBRARY_PATH` and `sys.path`
- `preload_shared_libraries(lib_paths=None)`: attempts to load shared libraries with `ctypes.RTLD_GLOBAL`

## Public Errors

```python
from Aslide.errors import AslideError, MissingDefaultBiomarkerError, UnknownBiomarkerError, UnsupportedOperationError
```

- `AslideError`: base package error
- `UnsupportedOperationError`: raised when a method is not valid for the slide family or backend
- `UnknownBiomarkerError`: raised by biomarker-aware paths when a marker is not known
- `MissingDefaultBiomarkerError`: raised when a default display biomarker cannot be selected
