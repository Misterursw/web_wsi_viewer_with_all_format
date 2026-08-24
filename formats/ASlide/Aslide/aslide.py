from __future__ import annotations

from collections.abc import Mapping, Iterator
from typing import Any, cast

from .errors import MissingDefaultBiomarkerError, UnsupportedOperationError
from .registry import registry


RUNTIME_CLASSIFIED_FAMILIES = {"qptiff", "czi"}


class AssociatedImagesView(Mapping[str, Any]):
    def __init__(self, backend_images: Any, thumbnail_factory: Any) -> None:
        self._backend_images = backend_images
        self._thumbnail_factory = thumbnail_factory

    def __getitem__(self, key: str) -> Any:
        if key == "thumbnail":
            try:
                return self._backend_images[key]
            except Exception:
                if self._thumbnail_factory is None:
                    raise KeyError(key) from None
                return self._thumbnail_factory((512, 512))
        return self._backend_images[key]

    def __iter__(self) -> Iterator[str]:
        seen = set()
        for key in self._backend_images:
            seen.add(key)
            yield key

        if "thumbnail" not in seen and self._thumbnail_factory is not None:
            yield "thumbnail"

    def __len__(self) -> int:
        size = len(self._backend_images)
        if self._thumbnail_factory is None:
            return size

        try:
            self._backend_images["thumbnail"]
        except Exception:
            return size + 1
        return size


class Slide:
    def __init__(self, filepath: str, acquisition_id: int | None = None):
        self.filepath = filepath
        self.acquisition_id = acquisition_id
        self.registry_entry = registry.resolve_path(filepath)
        self.format = self.registry_entry.extensions[0]
        self._backend = self.registry_entry.create_slide(
            filepath, acquisition_id=acquisition_id
        )
        self._slide_family = self._resolve_slide_family()

    @property
    def backend(self) -> Any:
        return self._backend

    @property
    def slide_family(self) -> str:
        return self._slide_family

    @property
    def qptiff_semantics(self) -> str | None:
        if self.format.lower() != ".qptiff":
            return None
        return self.slide_family

    def _resolve_slide_family(self) -> str:
        family = cast(str, self.registry_entry.slide_family)

        classify = getattr(self.backend, "classify_slide_family", None)
        if callable(classify):
            return cast(str, classify())

        if family not in RUNTIME_CLASSIFIED_FAMILIES:
            return family

        if family != "qptiff":
            return family

        markers = None
        list_markers = getattr(self.backend, "list_biomarkers", None)
        if callable(list_markers):
            markers = list_markers()
        elif hasattr(self.backend, "get_biomarkers"):
            maybe_get = getattr(self.backend, "get_biomarkers")
            if callable(maybe_get):
                markers = maybe_get()

        raw_markers = cast(list[Any], markers or [])
        normalized = [
            str(marker).strip().lower() for marker in raw_markers if str(marker).strip()
        ]
        if len(normalized) == 1 and normalized[0] in {"h&e", "he"}:
            return "brightfield"
        return "multiplex"

    def classify_slide_family(self) -> str:
        classifier = getattr(self.backend, "classify_slide_family", None)
        if callable(classifier):
            return cast(str, classifier())
        return self._slide_family

    @property
    def supports_biomarkers(self) -> bool:
        return (
            self.registry_entry.capabilities.supports_biomarkers
            or self.slide_family == "multiplex"
        )

    @property
    def _osr(self) -> Any:
        return self._backend

    def __enter__(self) -> "Slide":
        return self

    def __exit__(self, exc_type, exc_value, exc_tb) -> bool:
        self.close()
        return False

    @property
    def mpp(self) -> Any:
        if hasattr(self.backend, "mpp"):
            return self.backend.mpp

        properties = getattr(self.backend, "properties", {})
        if "openslide.mpp-x" in properties and "openslide.mpp-y" in properties:
            return (
                float(properties["openslide.mpp-x"])
                + float(properties["openslide.mpp-y"])
            ) / 2
        if "openslide.mpp-x" in properties:
            return float(properties["openslide.mpp-x"])

        raise AttributeError(f"{self.backend.__class__.__name__} does not provide mpp")

    @property
    def magnification(self) -> Any:
        return getattr(self.backend, "magnification", None)

    @property
    def level_count(self) -> int:
        return self.backend.level_count

    @property
    def dimensions(self) -> Any:
        return self.backend.dimensions

    @property
    def level_dimensions(self) -> Any:
        return self.backend.level_dimensions

    @property
    def level_downsamples(self) -> Any:
        return self.backend.level_downsamples

    @property
    def properties(self) -> Any:
        return self.backend.properties

    @property
    def associated_images(self) -> Any:
        backend_images = getattr(self.backend, "associated_images", {})
        thumbnail_factory = None
        if self.slide_family == "brightfield":
            thumbnail_factory = getattr(self.backend, "get_thumbnail", None)
        return AssociatedImagesView(backend_images, thumbnail_factory)

    def label_image(self, save_path: str | None = None) -> Any:
        if hasattr(self.backend, "label_image"):
            try:
                return self.backend.label_image()
            except TypeError:
                return self.backend.label_image(save_path)

        if hasattr(self.backend, "saveLabelImg"):
            if save_path is None:
                raise ValueError("save_path is required for this backend")
            return self.backend.saveLabelImg(save_path)

        associated_images = self.associated_images
        if callable(associated_images):
            return associated_images("label")
        return associated_images.get("label")

    def get_best_level_for_downsample(self, downsample: float) -> int:
        return self.backend.get_best_level_for_downsample(downsample)

    def get_thumbnail(self, size: tuple[int, int]) -> Any:
        if self.slide_family != "brightfield":
            raise UnsupportedOperationError(
                "Multiplex slides do not support generic thumbnails; use a display biomarker-aware path instead"
            )
        return self.backend.get_thumbnail(size)

    def list_biomarkers(self) -> list[str]:
        if self.slide_family != "multiplex":
            raise UnsupportedOperationError(
                f"Biomarker operations are not supported for {self.slide_family} slides"
            )
        return self.backend.list_biomarkers()

    def get_default_display_biomarker(self) -> str:
        if self.slide_family != "multiplex":
            raise UnsupportedOperationError(
                f"Biomarker operations are not supported for {self.slide_family} slides"
            )
        try:
            return self.backend.get_default_display_biomarker()
        except MissingDefaultBiomarkerError:
            raise
        except Exception as exc:
            raise MissingDefaultBiomarkerError(str(exc)) from exc

    def read_biomarker_region(
        self,
        location: tuple[int, int],
        level: int,
        size: tuple[int, int],
        biomarker: str,
    ) -> Any:
        if self.slide_family != "multiplex":
            raise UnsupportedOperationError(
                f"Biomarker operations are not supported for {self.slide_family} slides"
            )
        image = self.backend.read_biomarker_region(location, level, size, biomarker)
        if hasattr(image, "mode") and image.mode != "RGBA":
            return image.convert("RGBA")
        return image

    def read_region(
        self,
        location: tuple[int, int],
        level: int,
        size: tuple[int, int],
    ) -> Any:
        if self.slide_family != "brightfield":
            raise UnsupportedOperationError(
                "Multiplex slides require an explicit biomarker; use read_biomarker_region()"
            )
        image = self.backend.read_region(location, level, size)
        if hasattr(image, "mode") and image.mode != "RGBA":
            return image.convert("RGBA")
        return image

    def read_fixed_region(
        self,
        location: tuple[int, int],
        level: int,
        size: tuple[int, int],
    ) -> Any:
        if self.slide_family != "brightfield":
            raise UnsupportedOperationError(
                "Multiplex slides do not support generic fixed-region reads"
            )
        image = self.backend.read_fixed_region(location, level, size)
        if hasattr(image, "mode") and image.mode != "RGBA":
            return image.convert("RGBA")
        return image

    def close(self) -> None:
        self.backend.close()

    def apply_color_correction(self, apply: bool = True, style: str = "Real") -> None:
        if not hasattr(self.backend, "apply_color_correction"):
            raise NotImplementedError(
                f"Color correction not supported for {self.registry_entry.format_id}"
            )
        self.backend.apply_color_correction(apply, style)
