# Backends and Registry

ASlide uses a registry to map file paths to backend classes. This keeps the public `Slide(path)` API stable while allowing each format to provide its own reader and DeepZoom implementation.

## Resolution Flow

When `Slide(filepath)` is created:

1. `registry.resolve_path(filepath)` scans registered `FormatEntry` objects.
2. The file extension must match an entry.
3. If the entry has a `probe`, the probe must accept the path.
4. `entry.is_available()` must return true.
5. `entry.create_slide(filepath, acquisition_id=...)` constructs the backend.
6. `Slide` resolves the runtime `slide_family` when the backend supports classification.

Entries with probes are useful when one extension can represent multiple families. OME-like TIFF is probe-selected before generic TIFF fallback.

## `FormatEntry`

`FormatEntry` describes one backend registration:

- `format_id`: stable registry name
- `extensions`: accepted suffixes
- `slide_backend`: backend class or lazy factory
- `slide_family`: static family or runtime-classified family marker
- `deepzoom_backend`: optional backend-specific DeepZoom class
- `availability_check`: optional dependency check
- `probe`: optional file content/metadata check
- `capabilities`: static `BackendCapabilities`

`FormatEntry.create_slide()` only forwards keyword arguments accepted by the backend constructor. This lets `Slide(..., acquisition_id=...)` work for MCD without breaking backends that do not accept `acquisition_id`.

## Static Capabilities vs Runtime Behavior

`BackendCapabilities` are known before opening a specific file. Runtime-classified formats such as CZI and QPTIFF can advertise conservative static capabilities, then expose brightfield or multiplex behavior after metadata inspection.

Capability flags:

- `has_label_image`
- `has_color_correction`
- `has_associated_images`
- `has_deepzoom`
- `requires_bootstrap`
- `supports_biomarkers`
- `requires_explicit_channel_read`
- `default_display_biomarker`

Use `slide.slide_family` and `slide.supports_biomarkers` for file-specific behavior.

## Adding a Backend

To add a backend, implement the backend contract used by `Slide`:

- shared fields: `level_count`, `dimensions`, `level_dimensions`, `level_downsamples`, `properties`
- `close()`
- brightfield: `read_region()` and optional thumbnail, associated image, label, color correction helpers
- multiplex: `list_biomarkers()`, `read_biomarker_region()`, and `get_default_display_biomarker()` when a safe default exists

Then register a `FormatEntry` in `build_default_registry()`. If the format needs optional dependencies, use `availability_check`. If extension alone is not enough, add a `probe`.

## DeepZoom Backends

If a format has a specialized DeepZoom generator, set `deepzoom_backend`. Otherwise `DeepZoom` falls back to OpenSlide's generator when possible. Multiplex DeepZoom backends should accept or expose a biomarker-aware source.
