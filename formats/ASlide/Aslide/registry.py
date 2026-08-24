from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import inspect
from pathlib import Path
from typing import Any, Callable, Final

from openslide import OpenSlide
from openslide.deepzoom import DeepZoomGenerator as OpenSlideDeepZoomGenerator

from .capabilities import BackendCapabilities


BackendFactory = Callable[[], type[Any]] | type[Any]
AvailabilityCheck = Callable[[], bool]
ProbeCheck = Callable[[str], bool]

_OPENSLIDE_TIFF_EXTENSIONS: Final = (".tif", ".tiff")


def _load_attr(module_name: str, attribute_name: str) -> type[Any]:
    module = importlib.import_module(module_name)
    return getattr(module, attribute_name)


def _module_available(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
    except Exception:
        return False
    return True


def _is_openslide_candidate(path: str) -> bool:
    extension = Path(path).suffix.lower()
    if extension not in _OPENSLIDE_TIFF_EXTENSIONS:
        return True
    return OpenSlide.detect_format(path) is not None


@dataclass(frozen=True)
class FormatEntry:
    format_id: str
    extensions: tuple[str, ...]
    slide_backend: BackendFactory
    slide_family: str = "brightfield"
    deepzoom_backend: BackendFactory | None = None
    availability_check: AvailabilityCheck = lambda: True
    probe: ProbeCheck | None = None
    capabilities: BackendCapabilities = field(default_factory=BackendCapabilities)

    def is_available(self) -> bool:
        return self.availability_check()

    def load_slide_backend(self) -> type[Any]:
        backend = self.slide_backend
        if isinstance(backend, type):
            return backend
        return backend()

    def load_deepzoom_backend(self) -> type[Any] | None:
        backend = self.deepzoom_backend
        if backend is None:
            return None
        if isinstance(backend, type):
            return backend
        return backend()

    def create_slide(self, path: str, **kwargs: Any) -> Any:
        backend_cls = self.load_slide_backend()
        signature = inspect.signature(backend_cls)
        supported_kwargs = {
            key: value for key, value in kwargs.items() if key in signature.parameters
        }
        return backend_cls(path, **supported_kwargs)

    def matches_path(self, path: str) -> bool:
        extension = Path(path).suffix.lower()
        if extension not in self.extensions:
            return False
        if self.probe is None:
            return True
        try:
            return bool(self.probe(path))
        except Exception:
            return False


class FormatRegistry:
    def __init__(self) -> None:
        self._entries: list[FormatEntry] = []

    def register(self, entry: FormatEntry) -> None:
        self._entries = [
            existing
            for existing in self._entries
            if existing.format_id != entry.format_id
        ]
        self._entries.append(entry)

    def get(self, format_id: str) -> FormatEntry:
        for entry in self._entries:
            if entry.format_id == format_id:
                return entry
        raise LookupError(f"Unknown format id: {format_id}")

    def entries(self) -> tuple[FormatEntry, ...]:
        return tuple(self._entries)

    def resolve_path(self, path: str) -> FormatEntry:
        extension = Path(path).suffix.lower()
        fallback_entry: FormatEntry | None = None
        for entry in self._entries:
            if entry.matches_path(path):
                if entry.is_available():
                    return entry
                raise LookupError(
                    f"Format '{entry.format_id}' is unavailable in this environment"
                )
            if entry.probe is not None:
                continue
            if extension in entry.extensions and fallback_entry is None:
                fallback_entry = entry

        if fallback_entry is not None:
            if fallback_entry.is_available():
                return fallback_entry
            raise LookupError(
                f"Format '{fallback_entry.format_id}' is unavailable in this environment"
            )
        raise LookupError(f"Unsupported file extension: {extension or '<none>'}")


def build_default_registry() -> FormatRegistry:
    new_registry = FormatRegistry()

    new_registry.register(
        FormatEntry(
            format_id="czi",
            extensions=(".czi",),
            slide_backend=lambda: _load_attr("Aslide.czi.czi_slide", "CziSlide"),
            slide_family="czi",
            availability_check=lambda: (
                _module_available("pylibCZIrw")
                or _module_available("pylibCZIrw.czi")
                or
                (_module_available("bioformats") and _module_available("javabridge"))
                or _module_available("czifile")
            ),
            capabilities=BackendCapabilities(
                has_associated_images=False,
                supports_biomarkers=False,
                requires_explicit_channel_read=False,
            ),
        )
    )
    new_registry.register(
        FormatEntry(
            format_id="ome_tiff",
            extensions=(".tif", ".tiff"),
            slide_backend=lambda: _load_attr(
                "Aslide.ome_tiff.ome_tiff_slide", "OmeTiffSlide"
            ),
            slide_family="multiplex",
            deepzoom_backend=lambda: _load_attr(
                "Aslide.ome_tiff.ome_tiff_deepzoom", "OmeTiffDeepZoomGenerator"
            ),
            availability_check=lambda: _module_available("tifffile"),
            probe=lambda path: _load_attr(
                "Aslide.ome_tiff.probe", "is_ome_tiff_candidate"
            )(path),
            capabilities=BackendCapabilities(
                has_associated_images=False,
                supports_biomarkers=True,
                requires_explicit_channel_read=True,
            ),
        )
    )
    new_registry.register(
        FormatEntry(
            format_id="mcd",
            extensions=(".mcd",),
            slide_backend=lambda: _load_attr("Aslide.mcd.mcd_slide", "McdSlide"),
            slide_family="multiplex",
            availability_check=lambda: _module_available("readimc"),
            capabilities=BackendCapabilities(
                has_associated_images=False,
                supports_biomarkers=True,
                requires_explicit_channel_read=True,
            ),
        )
    )
    new_registry.register(
        FormatEntry(
            format_id="hdf5",
            extensions=(".h5", ".hdf5", ".h5ad"),
            slide_backend=lambda: _load_attr("Aslide.hdf5_family", "Hdf5Slide"),
            slide_family="multiplex",
            availability_check=lambda: _module_available("h5py"),
            probe=lambda path: _load_attr(
                "Aslide.hdf5_family", "is_hdf5_multiplex_candidate"
            )(path),
            capabilities=BackendCapabilities(
                has_associated_images=False,
                supports_biomarkers=True,
                requires_explicit_channel_read=True,
            ),
        )
    )
    new_registry.register(
        FormatEntry(
            format_id="ims",
            extensions=(".ims",),
            slide_backend=lambda: _load_attr("Aslide.ims.ims_slide", "ImsSlide"),
            slide_family="multiplex",
            deepzoom_backend=lambda: _load_attr(
                "Aslide.ims.ims_deepzoom", "ImsDeepZoomGenerator"
            ),
            availability_check=lambda: _module_available("h5py"),
            probe=lambda path: _load_attr("Aslide.ims.ims_slide", "is_ims_candidate")(
                path
            ),
            capabilities=BackendCapabilities(
                has_associated_images=False,
                has_deepzoom=True,
                supports_biomarkers=True,
                requires_explicit_channel_read=True,
            ),
        )
    )
    new_registry.register(
        FormatEntry(
            format_id="qptiff",
            extensions=(".qptiff",),
            slide_backend=lambda: _load_attr(
                "Aslide.qptiff.qptiff_slide", "QptiffSlide"
            ),
            slide_family="qptiff",
            deepzoom_backend=lambda: _load_attr(
                "Aslide.qptiff.qptiff_deepzoom", "QptiffDeepZoomGenerator"
            ),
            availability_check=lambda: _module_available("qptifffile"),
            capabilities=BackendCapabilities(
                has_associated_images=False,
                has_deepzoom=True,
                supports_biomarkers=True,
                requires_explicit_channel_read=True,
                default_display_biomarker="DAPI",
            ),
        )
    )
    new_registry.register(
        FormatEntry(
            format_id="kfb",
            extensions=(".kfb",),
            slide_backend=lambda: _load_attr("Aslide.kfb.kfb_slide", "KfbSlide"),
            deepzoom_backend=lambda: _load_attr(
                "Aslide.kfb.kfb_deepzoom", "DeepZoomGenerator"
            ),
            capabilities=BackendCapabilities(
                has_label_image=True,
                has_color_correction=True,
                has_associated_images=True,
                has_deepzoom=True,
                requires_bootstrap=True,
            ),
        )
    )
    new_registry.register(
        FormatEntry(
            format_id="tmap",
            extensions=(".tmap",),
            slide_backend=lambda: _load_attr("Aslide.tmap.tmap_slide", "TmapSlide"),
            deepzoom_backend=lambda: _load_attr(
                "Aslide.tmap.tmap_deepzoom", "DeepZoomGenerator"
            ),
            capabilities=BackendCapabilities(
                has_label_image=True,
                has_color_correction=True,
                has_associated_images=True,
                has_deepzoom=True,
                requires_bootstrap=True,
            ),
        )
    )
    new_registry.register(
        FormatEntry(
            format_id="sdpc",
            extensions=(".sdpc", ".dyqx"),
            slide_backend=lambda: _load_attr("Aslide.sdpc.sdpc_slide", "SdpcSlide"),
            deepzoom_backend=lambda: _load_attr(
                "Aslide.sdpc.sdpc_deepzoom", "DeepZoomGenerator"
            ),
            capabilities=BackendCapabilities(
                has_label_image=True,
                has_color_correction=True,
                has_associated_images=True,
                has_deepzoom=True,
                requires_bootstrap=True,
            ),
        )
    )
    new_registry.register(
        FormatEntry(
            format_id="vsi",
            extensions=(".vsi",),
            slide_backend=lambda: _load_attr("Aslide.vsi.vsi_slide", "VsiSlide"),
            availability_check=lambda: (
                _module_available("bioformats") and _module_available("javabridge")
            ),
            capabilities=BackendCapabilities(
                has_associated_images=False,
                supports_biomarkers=True,
                requires_explicit_channel_read=True,
            ),
        )
    )
    new_registry.register(
        FormatEntry(
            format_id="mds",
            extensions=(".mds", ".mdsx"),
            slide_backend=lambda: _load_attr("Aslide.mds.mds_slide", "MdsSlide"),
            deepzoom_backend=lambda: _load_attr(
                "Aslide.mds.mds_deepzoom", "DeepZoomGenerator"
            ),
            capabilities=BackendCapabilities(
                has_color_correction=True, has_associated_images=True, has_deepzoom=True
            ),
        )
    )
    new_registry.register(
        FormatEntry(
            format_id="tron",
            extensions=(".tron",),
            slide_backend=lambda: _load_attr("Aslide.tron.slide", "TronSlide"),
            deepzoom_backend=lambda: _load_attr(
                "Aslide.tron.deepzoom", "TronDeepZoomGenerator"
            ),
            capabilities=BackendCapabilities(
                has_associated_images=True, has_deepzoom=True, requires_bootstrap=True
            ),
        )
    )
    new_registry.register(
        FormatEntry(
            format_id="isyntax",
            extensions=(".isyntax",),
            slide_backend=lambda: _load_attr(
                "Aslide.isyntax.isyntax_slide", "IsyntaxSlide"
            ),
            deepzoom_backend=lambda: _load_attr(
                "Aslide.isyntax.isyntax_deepzoom", "IsyntaxDeepZoomGenerator"
            ),
            availability_check=lambda: _module_available("isyntax"),
            capabilities=BackendCapabilities(
                has_associated_images=True, has_deepzoom=True
            ),
        )
    )
    new_registry.register(
        FormatEntry(
            format_id="dyj",
            extensions=(".dyj",),
            slide_backend=lambda: _load_attr("Aslide.dyj.dyj_slide", "DyjSlide"),
            deepzoom_backend=lambda: _load_attr(
                "Aslide.dyj.dyj_deepzoom", "DeepZoomGenerator"
            ),
            capabilities=BackendCapabilities(
                has_color_correction=True, has_deepzoom=True
            ),
        )
    )
    new_registry.register(
        FormatEntry(
            format_id="ibl",
            extensions=(".ibl",),
            slide_backend=lambda: _load_attr("Aslide.ibl.ibl_slide", "IblSlide"),
            deepzoom_backend=lambda: _load_attr(
                "Aslide.ibl.ibl_deepzoom", "DeepZoomGenerator"
            ),
            capabilities=BackendCapabilities(has_deepzoom=True),
        )
    )
    new_registry.register(
        FormatEntry(
            format_id="zyp",
            extensions=(".zyp",),
            slide_backend=lambda: _load_attr("Aslide.zyp.zyp_slide", "ZypSlide"),
            deepzoom_backend=lambda: _load_attr(
                "Aslide.zyp.zyp_deepzoom", "DeepZoomGenerator"
            ),
            capabilities=BackendCapabilities(has_deepzoom=True),
        )
    )
    new_registry.register(
        FormatEntry(
            format_id="bif",
            extensions=(".bif",),
            slide_backend=lambda: _load_attr("Aslide.bif.bif_slide", "BifSlide"),
            deepzoom_backend=lambda: _load_attr(
                "Aslide.bif.bif_deepzoom", "DeepZoomGenerator"
            ),
            capabilities=BackendCapabilities(has_deepzoom=True),
        )
    )
    new_registry.register(
        FormatEntry(
            format_id="openslide",
            extensions=(
                ".svs",
                ".svslide",
                ".tif",
                ".tiff",
                ".ndpi",
                ".vms",
                ".vmu",
                ".scn",
                ".mrxs",
            ),
            slide_backend=OpenSlide,
            deepzoom_backend=OpenSlideDeepZoomGenerator,
            probe=_is_openslide_candidate,
            capabilities=BackendCapabilities(
                has_associated_images=True, has_deepzoom=True
            ),
        )
    )
    new_registry.register(
        FormatEntry(
            format_id="generic_tiff",
            extensions=(".tif", ".tiff"),
            slide_backend=lambda: _load_attr(
                "Aslide.generic_tiff.generic_tiff_slide", "GenericTiffSlide"
            ),
            capabilities=BackendCapabilities(has_associated_images=False),
        )
    )
    return new_registry


registry = build_default_registry()
