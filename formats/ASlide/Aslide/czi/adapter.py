from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import re
from typing import Any, Iterable, cast
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image

from .metadata import (
    NormalizedCziMetadata,
    classify_czi_family,
    normalize_czi_metadata,
)

try:
    import czifile as czifile  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    czifile = None


_BIOFORMATS_METADATA_CACHE: dict[
    str, tuple[dict[str, Any], tuple[int, int], int, tuple["_BioformatsScene", ...]]
] = {}


@dataclass(frozen=True)
class _BioformatsScene:
    index: int
    offset: tuple[int, int]
    size: tuple[int, int]


@dataclass(frozen=True)
class _PylibCziScene:
    index: int | None
    rect: tuple[int, int, int, int]


@dataclass
class CziAdapter:
    metadata: NormalizedCziMetadata
    dimensions: tuple[int, int] = (0, 0)
    level_count: int = 1
    level_dimensions: tuple[tuple[int, int], ...] = ((0, 0),)
    level_downsamples: tuple[float, ...] = (1.0,)
    properties: dict[str, str] = field(default_factory=dict)
    _reader: Any | None = None
    _backend: str = "metadata"
    _javabridge: Any | None = None
    _owns_vm: bool = False
    _bioformats_series: int = 0
    _bioformats_scenes: tuple[_BioformatsScene, ...] = ()
    _pylibczirw_scene: _PylibCziScene | None = None
    _pylibczirw_context: Any | None = None

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any]) -> "CziAdapter":
        normalized = normalize_czi_metadata(metadata)
        return cls(
            metadata=normalized,
            dimensions=(0, 0),
            level_count=1,
            level_dimensions=((0, 0),),
            level_downsamples=(1.0,),
            properties={
                "aslide.czi.adapter": "metadata",
                **_metadata_properties(normalized),
            },
        )

    @classmethod
    def from_bioformats(cls, path: str) -> "CziAdapter":
        try:
            bioformats = importlib.import_module("bioformats")
            javabridge = importlib.import_module("javabridge")
        except ImportError as exc:
            raise ImportError(
                "CZI support requires optional dependencies: python-bioformats and javabridge"
            ) from exc

        owns_vm = False
        if not javabridge.get_env():
            javabridge.start_vm(class_path=bioformats.JARS)
            owns_vm = True

        try:
            cached = _BIOFORMATS_METADATA_CACHE.get(path)
            if cached is None:
                ome_metadata = bioformats.get_omexml_metadata(path)
                ome = bioformats.OMEXML(ome_metadata)
                image_index = _select_largest_bioformats_image_index(ome)
                scene_canvas, scenes = _extract_bioformats_scene_layout(ome, path)
                dimensions = scene_canvas or _extract_dimensions(ome, image_index)
                cached = (
                    _extract_normalized_metadata(ome, ome_metadata, image_index),
                    dimensions,
                    image_index,
                    scenes,
                )
                _BIOFORMATS_METADATA_CACHE[path] = cached
            image_reader = bioformats.ImageReader(path)
        except Exception as exc:
            if owns_vm and javabridge.get_env():
                javabridge.kill_vm()
            raise RuntimeError(
                f"Failed to initialize Bio-Formats CZI adapter: {exc}"
            ) from exc

        normalized_raw, dimensions, image_index, scenes = cached
        normalized = normalize_czi_metadata(normalized_raw)
        return cls(
            metadata=normalized,
            dimensions=dimensions,
            level_count=1,
            level_dimensions=(dimensions,),
            level_downsamples=(1.0,),
            properties={
                "openslide.vendor": "Zeiss",
                "aslide.czi.backend": "bioformats",
                **_metadata_properties(normalized),
            },
            _reader=image_reader,
            _backend="bioformats",
            _javabridge=javabridge,
            _owns_vm=owns_vm,
            _bioformats_series=image_index,
            _bioformats_scenes=scenes,
        )

    @classmethod
    def from_pylibczirw(cls, path: str) -> "CziAdapter":
        try:
            pyczi = importlib.import_module("pylibCZIrw.czi")
        except ImportError as exc:
            raise ImportError(
                "CZI support requires optional dependency: pylibCZIrw"
            ) from exc

        czi_context: Any | None = None
        try:
            czi_context = pyczi.open_czi(path)
            czi_document = (
                czi_context.__enter__()
                if czi_context is not None and hasattr(czi_context, "__enter__")
                else czi_context
            )
            metadata = _extract_pylibczirw_metadata(czi_document)
            scene = _select_pylibczirw_scene(czi_document)
        except Exception as exc:
            if czi_context is not None and hasattr(czi_context, "__exit__"):
                czi_context.__exit__(type(exc), exc, exc.__traceback__)
            raise RuntimeError(
                f"Failed to initialize pylibCZIrw CZI adapter: {exc}"
            ) from exc

        normalized = normalize_czi_metadata(metadata)
        dimensions = (scene.rect[2], scene.rect[3])
        properties = {
            "openslide.vendor": "Zeiss",
            "aslide.czi.backend": "pylibczirw",
            "aslide.czi.scene_origin": f"{scene.rect[0]},{scene.rect[1]}",
            **_metadata_properties(normalized),
        }
        if scene.index is not None:
            properties["aslide.czi.scene_index"] = str(scene.index)
        return cls(
            metadata=normalized,
            dimensions=dimensions,
            level_count=1,
            level_dimensions=(dimensions,),
            level_downsamples=(1.0,),
            properties=properties,
            _reader=czi_document,
            _backend="pylibczirw",
            _pylibczirw_scene=scene,
            _pylibczirw_context=czi_context if hasattr(czi_context, "__exit__") else None,
        )

    @classmethod
    def from_czifile(cls, path: str) -> "CziAdapter":
        if czifile is None:
            raise ImportError("CZI support requires optional dependency: czifile")

        try:
            czi_file = czifile.CziFile(path)
            metadata, dimensions = _extract_czifile_metadata(czi_file)
            return cls(
                metadata=normalize_czi_metadata(metadata),
                dimensions=dimensions,
                level_count=1,
                level_dimensions=(dimensions,),
                level_downsamples=(1.0,),
                properties={
                    "openslide.vendor": "Zeiss",
                    "aslide.czi.backend": "czifile",
                    **_metadata_properties(normalize_czi_metadata(metadata)),
                },
                _reader=czi_file,
                _backend="czifile",
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to initialize czifile CZI adapter: {exc}"
            ) from exc

    def classify_slide_family(self) -> str:
        return classify_czi_family(self.metadata)

    def list_biomarkers(self) -> list[str]:
        names: list[str] = []
        for name in (*self.metadata.fluorophore_names, *self.metadata.channel_names):
            if name and name not in names:
                names.append(name)
        for index in range(self.metadata.channel_count):
            alias = f"channel_{index}"
            if alias not in names:
                names.append(alias)
        return names

    def get_default_display_biomarker(self) -> str:
        biomarkers = self.list_biomarkers()
        if not biomarkers:
            raise LookupError("missing default biomarker")
        return biomarkers[0]

    def read_region(
        self,
        location: tuple[int, int],
        level: int,
        size: tuple[int, int],
    ) -> Image.Image | tuple[tuple[int, int], int, tuple[int, int]]:
        if self._backend == "bioformats" and self._reader is not None:
            if level != 0:
                raise ValueError(
                    "Bio-Formats CZI adapter currently supports only level 0"
                )
            x, y = location
            width, height = size
            image_data = _read_bioformats_canvas_region(
                self._reader,
                (x, y),
                (width, height),
                0,
                self._bioformats_series,
                self._bioformats_scenes,
            )
            if len(image_data.shape) == 2:
                return Image.fromarray(image_data, mode="L")
            return Image.fromarray(image_data)
        if self._backend == "pylibczirw" and self._reader is not None:
            if level != 0:
                raise ValueError("CZI adapter currently supports only level 0")
            return _read_pylibczirw_region(
                self._reader,
                self._pylibczirw_scene,
                location,
                size,
                0,
            )
        return (location, level, size)

    def get_thumbnail(
        self, size: tuple[int, int]
    ) -> Image.Image | tuple[str, tuple[int, int]]:
        if self._backend == "bioformats" and self._reader is not None:
            region = self.read_region((0, 0), 0, self.dimensions)
            if isinstance(region, Image.Image):
                return region.resize(size, Image.Resampling.LANCZOS)
        return ("thumbnail", size)

    def read_biomarker_region(
        self,
        location: tuple[int, int],
        level: int,
        size: tuple[int, int],
        biomarker: str,
    ) -> Image.Image | tuple[tuple[int, int], int, tuple[int, int], str]:
        channel_index = self._biomarker_channel_index(biomarker)
        if channel_index is None:
            raise LookupError(f"Unknown biomarker: {biomarker}")
        if self._backend == "bioformats" and self._reader is not None:
            if level != 0:
                raise ValueError("CZI adapter currently supports only level 0")
            return _read_bioformats_biomarker_region(
                self._reader,
                location,
                size,
                channel_index,
                self._bioformats_series,
                self._bioformats_scenes,
            )
        if self._backend == "pylibczirw" and self._reader is not None:
            if level != 0:
                raise ValueError("CZI adapter currently supports only level 0")
            return _read_pylibczirw_region(
                self._reader,
                self._pylibczirw_scene,
                location,
                size,
                channel_index,
            )
        if self._backend == "czifile" and self._reader is not None:
            if level != 0:
                raise ValueError("CZI adapter currently supports only level 0")
            return _read_czifile_biomarker_region(
                self._reader, location, size, channel_index
            )
        return (location, level, size, biomarker)

    def _biomarker_channel_index(self, biomarker: str) -> int | None:
        fluorophores = list(self.metadata.fluorophore_names)
        if biomarker in fluorophores:
            return fluorophores.index(biomarker)
        channel_names = list(self.metadata.channel_names)
        if biomarker in channel_names:
            return channel_names.index(biomarker)
        match = re.fullmatch(r"channel_(\d+)", biomarker)
        if match:
            index = int(match.group(1))
            if 0 <= index < self.metadata.channel_count:
                return index
        return None

    def get_best_level_for_downsample(self, downsample: float) -> int:
        _ = downsample
        return 0

    def close(self) -> None:
        if self._pylibczirw_context is not None:
            try:
                self._pylibczirw_context.__exit__(None, None, None)
            except Exception:
                pass
            finally:
                self._pylibczirw_context = None
                self._reader = None
            return
        if self._reader is not None:
            try:
                self._reader.close()
            except Exception:
                pass
            finally:
                self._reader = None
        if self._owns_vm and self._javabridge is not None:
            try:
                if self._javabridge.get_env():
                    self._javabridge.kill_vm()
            except Exception:
                pass
            finally:
                self._owns_vm = False


def _select_largest_bioformats_image_index(ome: Any) -> int:
    try:
        image_count = int(getattr(ome, "image_count", 0) or 0)
    except Exception:
        return 0

    best_index = 0
    best_area = -1
    for index in range(image_count):
        width, height = _extract_dimensions(ome, index)
        area = width * height
        if area > best_area:
            best_index = index
            best_area = area
    return best_index


def _extract_bioformats_scene_layout(
    ome: Any, path: str
) -> tuple[tuple[int, int] | None, tuple[_BioformatsScene, ...]]:
    if czifile is None:
        return None, ()

    try:
        with czifile.CziFile(path) as czi_file:
            axes = str(getattr(czi_file, "axes", "") or "")
            shape = getattr(czi_file, "shape", None)
            if not axes or not shape:
                return None, ()
            axis_sizes = {axis.upper(): int(length) for axis, length in zip(axes, shape)}
            scene_count = axis_sizes.get("S", 0)
            canvas = (
                int(axis_sizes.get("X", 0) or 0),
                int(axis_sizes.get("Y", 0) or 0),
            )
            if scene_count <= 1 or canvas[0] <= 0 or canvas[1] <= 0:
                return None, ()

            bounds = _extract_czifile_scene_bounds(czi_file)
    except Exception:
        return None, ()

    if not bounds:
        return None, ()

    try:
        image_count = int(getattr(ome, "image_count", 0) or 0)
    except Exception:
        return None, ()

    scenes: list[_BioformatsScene] = []
    last_image_index = 0
    for scene_index in sorted(bounds):
        width = bounds[scene_index][2] - bounds[scene_index][0]
        height = bounds[scene_index][3] - bounds[scene_index][1]
        if width <= 0 or height <= 0:
            continue
        image_index = _find_matching_bioformats_image_index(
            ome, width, height, last_image_index, image_count
        )
        if image_index is None:
            continue
        last_image_index = image_index + 1
        scenes.append(
            _BioformatsScene(
                index=image_index,
                offset=(int(bounds[scene_index][0]), int(bounds[scene_index][1])),
                size=_extract_dimensions(ome, image_index),
            )
        )

    if len(scenes) <= 1:
        return None, ()

    min_x = min(scene.offset[0] for scene in scenes)
    min_y = min(scene.offset[1] for scene in scenes)
    normalized = tuple(
        _BioformatsScene(
            index=scene.index,
            offset=(scene.offset[0] - min_x, scene.offset[1] - min_y),
            size=scene.size,
        )
        for scene in scenes
    )
    return canvas, normalized


def _extract_czifile_scene_bounds(czi_file: Any) -> dict[int, list[int]]:
    bounds: dict[int, list[int]] = {}
    subblocks: Any = getattr(czi_file, "subblocks", ())
    if callable(subblocks):
        subblocks = subblocks()
    for subblock in cast(Iterable[Any], subblocks):
        dimension_entries = getattr(
            getattr(subblock, "directory_entry", None), "dimension_entries", ()
        )
        entries = {
            getattr(dimension, "dimension", None): (
                int(getattr(dimension, "start", 0)),
                int(getattr(dimension, "size", 0)),
            )
            for dimension in dimension_entries
        }
        x_start, x_size = entries.get("X", (0, 0))
        y_start, y_size = entries.get("Y", (0, 0))
        scene_index = entries.get("S", (0, 1))[0]
        if x_size <= 0 or y_size <= 0:
            continue
        if scene_index not in bounds:
            bounds[scene_index] = [x_start, y_start, x_start + x_size, y_start + y_size]
        else:
            scene_bounds = bounds[scene_index]
            scene_bounds[0] = min(scene_bounds[0], x_start)
            scene_bounds[1] = min(scene_bounds[1], y_start)
            scene_bounds[2] = max(scene_bounds[2], x_start + x_size)
            scene_bounds[3] = max(scene_bounds[3], y_start + y_size)
    return bounds


def _find_matching_bioformats_image_index(
    ome: Any, width: int, height: int, start: int, image_count: int
) -> int | None:
    for index in range(start, image_count):
        image_width, image_height = _extract_dimensions(ome, index)
        if abs(image_width - width) <= 512 and abs(image_height - height) <= 512:
            return index
    return None


def _extract_dimensions(ome: Any, image_index: int = 0) -> tuple[int, int]:
    try:
        if ome.image_count <= 0:
            return (0, 0)
        pixels = ome.image(image_index).Pixels
        return (
            int(getattr(pixels, "SizeX", 0) or 0),
            int(getattr(pixels, "SizeY", 0) or 0),
        )
    except Exception:
        return (0, 0)


def _extract_normalized_metadata(
    ome: Any, ome_xml: str | None = None, image_index: int = 0
) -> dict[str, Any]:
    channel_count = 0
    pixel_type = None
    illumination_types: list[str] = []
    fluorophore_names: list[str] = []
    excitation_wavelengths: list[float] = []
    emission_wavelengths: list[float] = []
    channel_names: list[str] = []
    physical_pixel_sizes: list[float] = []

    try:
        if ome.image_count > 0:
            pixels = ome.image(image_index).Pixels
            channel_count = int(getattr(pixels, "SizeC", 0) or 0)
            pixel_type = getattr(pixels, "PixelType", None)
            for index in range(channel_count):
                channel = pixels.Channel(index)
                name = getattr(channel, "Name", None)
                fluor = getattr(channel, "Fluor", None)
                excitation = getattr(channel, "ExcitationWavelength", None)
                emission = getattr(channel, "EmissionWavelength", None)
                if name:
                    channel_names.append(str(name))
                if fluor:
                    fluorophore_names.append(str(fluor))
                illumination = getattr(channel, "IlluminationType", None)
                if illumination:
                    illumination_types.append(str(illumination))
                if excitation is not None:
                    excitation_wavelengths.append(float(excitation))
                if emission is not None:
                    emission_wavelengths.append(float(emission))
            physical_size_x = getattr(pixels, "PhysicalSizeX", None)
            physical_size_y = getattr(pixels, "PhysicalSizeY", None)
            if physical_size_x is not None:
                physical_pixel_sizes.append(float(physical_size_x))
            if physical_size_y is not None:
                physical_pixel_sizes.append(float(physical_size_y))
    except Exception:
        pass

    # Bio-Formats' OMEXML Python wrapper can drop some channel fields for CZI.
    # Fall back to the raw OME XML so classification still sees fluorescence signals.
    if ome_xml:
        xml_values = _extract_channel_fields_from_ome_xml(ome_xml)
        channel_count = channel_count or xml_values["channel_count"]
        pixel_type = pixel_type or xml_values["pixel_type"]
        if not illumination_types:
            illumination_types = list(xml_values["illumination_types"])
        if not fluorophore_names:
            fluorophore_names = list(xml_values["fluorophore_names"])
        if not excitation_wavelengths:
            excitation_wavelengths = list(xml_values["excitation_wavelengths"])
        if not emission_wavelengths:
            emission_wavelengths = list(xml_values["emission_wavelengths"])
        if not channel_names:
            channel_names = list(xml_values["channel_names"])
        if not physical_pixel_sizes:
            physical_pixel_sizes = list(xml_values["physical_pixel_sizes"])

    return {
        "channel_count": channel_count,
        "pixel_type": pixel_type,
        "illumination_types": tuple(illumination_types),
        "fluorophore_names": tuple(fluorophore_names),
        "excitation_wavelengths": tuple(excitation_wavelengths),
        "emission_wavelengths": tuple(emission_wavelengths),
        "channel_names": tuple(channel_names),
        "physical_pixel_sizes": tuple(physical_pixel_sizes),
    }


def _extract_channel_fields_from_ome_xml(ome_xml: str) -> dict[str, Any]:
    channel_count = 0
    pixel_type = None
    illumination_types: list[str] = []
    fluorophore_names: list[str] = []
    excitation_wavelengths: list[float] = []
    emission_wavelengths: list[float] = []
    channel_names: list[str] = []
    physical_pixel_sizes: list[float] = []

    try:
        root = ET.fromstring(ome_xml)
    except ET.ParseError:
        return {
            "channel_count": channel_count,
            "pixel_type": pixel_type,
            "illumination_types": tuple(illumination_types),
            "fluorophore_names": tuple(fluorophore_names),
            "excitation_wavelengths": tuple(excitation_wavelengths),
            "emission_wavelengths": tuple(emission_wavelengths),
            "channel_names": tuple(channel_names),
            "physical_pixel_sizes": tuple(physical_pixel_sizes),
        }

    namespace = {"ome": "http://www.openmicroscopy.org/Schemas/OME/2016-06"}
    pixels = root.find(".//ome:Image/ome:Pixels", namespace)
    if pixels is None:
        return {
            "channel_count": channel_count,
            "pixel_type": pixel_type,
            "illumination_types": tuple(illumination_types),
            "fluorophore_names": tuple(fluorophore_names),
            "excitation_wavelengths": tuple(excitation_wavelengths),
            "emission_wavelengths": tuple(emission_wavelengths),
            "channel_names": tuple(channel_names),
            "physical_pixel_sizes": tuple(physical_pixel_sizes),
        }

    channel_count = int(pixels.attrib.get("SizeC", 0) or 0)
    pixel_type = pixels.attrib.get("Type")
    physical_size_x = pixels.attrib.get("PhysicalSizeX")
    physical_size_y = pixels.attrib.get("PhysicalSizeY")

    for channel in pixels.findall("ome:Channel", namespace):
        name = channel.attrib.get("Name")
        fluor = channel.attrib.get("Fluor")
        illumination = channel.attrib.get("IlluminationType")
        excitation = channel.attrib.get("ExcitationWavelength")
        emission = channel.attrib.get("EmissionWavelength")

        if name:
            channel_names.append(name)
        if fluor:
            fluorophore_names.append(fluor)
        if illumination:
            illumination_types.append(illumination)
        if excitation is not None:
            excitation_wavelengths.append(float(excitation))
        if emission is not None:
            emission_wavelengths.append(float(emission))

    if physical_size_x is not None:
        physical_pixel_sizes.append(float(physical_size_x))
    if physical_size_y is not None:
        physical_pixel_sizes.append(float(physical_size_y))

    return {
        "channel_count": channel_count,
        "pixel_type": pixel_type,
        "illumination_types": tuple(illumination_types),
        "fluorophore_names": tuple(fluorophore_names),
        "excitation_wavelengths": tuple(excitation_wavelengths),
        "emission_wavelengths": tuple(emission_wavelengths),
        "channel_names": tuple(channel_names),
        "physical_pixel_sizes": tuple(physical_pixel_sizes),
    }


def _metadata_properties(metadata: NormalizedCziMetadata) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    if metadata.pixel_type is not None:
        properties["pixel_type"] = metadata.pixel_type
    if metadata.channel_names:
        properties["channel_names"] = metadata.channel_names
    if metadata.fluorophore_names:
        properties["fluorophore_names"] = metadata.fluorophore_names
    if metadata.illumination_types:
        properties["illumination_types"] = metadata.illumination_types
    if metadata.excitation_wavelengths:
        properties["excitation_wavelengths"] = metadata.excitation_wavelengths
    if metadata.emission_wavelengths:
        properties["emission_wavelengths"] = metadata.emission_wavelengths
    if metadata.physical_pixel_sizes:
        properties["physical_pixel_sizes"] = metadata.physical_pixel_sizes
    return properties


def _extract_czifile_metadata(czi_file: Any) -> tuple[dict[str, Any], tuple[int, int]]:
    ome_xml = _extract_czi_xml(czi_file)
    metadata = {
        "channel_count": 0,
        "pixel_type": None,
        "illumination_types": (),
        "fluorophore_names": (),
        "excitation_wavelengths": (),
        "emission_wavelengths": (),
        "channel_names": (),
        "physical_pixel_sizes": (),
    }
    if ome_xml:
        extracted = _extract_channel_fields_from_ome_xml(ome_xml)
        if not any(extracted.values()):
            extracted = _extract_channel_fields_from_image_document_xml(
                ome_xml, czi_file
            )
        metadata.update(extracted)

    dimensions = (0, 0)
    size = getattr(czi_file, "shape", None)
    axes = str(getattr(czi_file, "axes", "") or "")
    if size and axes:
        axis_sizes = {axis.upper(): int(length) for axis, length in zip(axes, size)}
        dimensions = (
            int(axis_sizes.get("X", 0) or 0),
            int(axis_sizes.get("Y", 0) or 0),
        )
    elif size and len(size) >= 2:
        dimensions = (int(size[-1]), int(size[-2]))
    return metadata, dimensions


def _extract_pylibczirw_metadata(czi_document: Any) -> dict[str, Any]:
    channel_count = 0
    total_bounding_box = getattr(czi_document, "total_bounding_box", {}) or {}
    channel_bounds = total_bounding_box.get("C") if isinstance(total_bounding_box, dict) else None
    if channel_bounds is not None and len(channel_bounds) >= 2:
        channel_count = int(channel_bounds[1]) - int(channel_bounds[0])

    pixel_type = None
    pixel_types = getattr(czi_document, "pixel_types", None)
    if isinstance(pixel_types, dict) and pixel_types:
        pixel_type = str(next(iter(pixel_types.values())))
    elif callable(getattr(czi_document, "get_channel_pixel_type", None)):
        try:
            pixel_type = str(czi_document.get_channel_pixel_type(0))
        except Exception:
            pixel_type = None
    if channel_count <= 0 and isinstance(pixel_types, dict):
        channel_count = len(pixel_types)

    channel_names = tuple(f"channel_{index}" for index in range(max(channel_count, 0)))
    return {
        "channel_count": channel_count,
        "pixel_type": pixel_type,
        "illumination_types": ("Epifluorescence",) if channel_count > 1 else (),
        "fluorophore_names": (),
        "excitation_wavelengths": (),
        "emission_wavelengths": (),
        "channel_names": channel_names,
        "physical_pixel_sizes": (),
    }


def _select_pylibczirw_scene(czi_document: Any) -> _PylibCziScene:
    scenes = getattr(czi_document, "scenes_bounding_rectangle", None) or {}
    if scenes:
        index, rect = max(
            scenes.items(),
            key=lambda item: _pylibczirw_rect_tuple(item[1])[2]
            * _pylibczirw_rect_tuple(item[1])[3],
        )
        return _PylibCziScene(index=int(index), rect=_pylibczirw_rect_tuple(rect))

    rect = getattr(czi_document, "total_bounding_rectangle", None)
    if rect is not None:
        return _PylibCziScene(index=None, rect=_pylibczirw_rect_tuple(rect))

    total_bounding_box = getattr(czi_document, "total_bounding_box", {}) or {}
    x_bounds = total_bounding_box.get("X", (0, 0))
    y_bounds = total_bounding_box.get("Y", (0, 0))
    x0, x1 = int(x_bounds[0]), int(x_bounds[1])
    y0, y1 = int(y_bounds[0]), int(y_bounds[1])
    return _PylibCziScene(index=None, rect=(x0, y0, max(0, x1 - x0), max(0, y1 - y0)))


def _pylibczirw_rect_tuple(rect: Any) -> tuple[int, int, int, int]:
    if all(hasattr(rect, attr) for attr in ("x", "y", "w", "h")):
        return (int(rect.x), int(rect.y), int(rect.w), int(rect.h))
    x, y, width, height = rect
    return (int(x), int(y), int(width), int(height))


def _extract_channel_fields_from_image_document_xml(
    xml_text: str, czi_file: Any
) -> dict[str, Any]:
    channel_count = 0
    pixel_type = None
    illumination_types: list[str] = []
    fluorophore_names: list[str] = []
    excitation_wavelengths: list[float] = []
    emission_wavelengths: list[float] = []
    channel_names: list[str] = []
    physical_pixel_sizes: list[float] = []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {
            "channel_count": channel_count,
            "pixel_type": pixel_type,
            "illumination_types": tuple(illumination_types),
            "fluorophore_names": tuple(fluorophore_names),
            "excitation_wavelengths": tuple(excitation_wavelengths),
            "emission_wavelengths": tuple(emission_wavelengths),
            "channel_names": tuple(channel_names),
            "physical_pixel_sizes": tuple(physical_pixel_sizes),
        }

    if root.tag.lower().endswith("imagedocument"):
        flattened = " ".join(text.strip() for text in root.itertext())
        lowered = flattened.lower()
        if "camera pixel type" in lowered and "uint16" in lowered:
            pixel_type = "uint16"
        if "fluorescencedye" in lowered or "additionaldyeinformation" in lowered:
            illumination_types.append("Epifluorescence")
            for token in ("DAPI", "CD3", "FITC", "TRITC", "Cy3", "Cy5"):
                if token.lower() in lowered and token not in fluorophore_names:
                    fluorophore_names.append(token)
                    channel_names.append(token)
        channel_count = max(channel_count, len(fluorophore_names))
        scaling_x = _extract_image_document_distance(root, "x")
        scaling_y = _extract_image_document_distance(root, "y")
        if scaling_x is not None and scaling_y is not None:
            physical_pixel_sizes = [scaling_x, scaling_y]
        size = getattr(czi_file, "shape", ())
        axes = str(getattr(czi_file, "axes", "") or "")
        if size and axes:
            axis_sizes = {axis.upper(): int(length) for axis, length in zip(axes, size)}
            channel_count = int(axis_sizes.get("C", channel_count) or channel_count)
        if channel_count > 1 and not illumination_types:
            illumination_types.append("Epifluorescence")
        if channel_count > 1 and not fluorophore_names:
            fluorophore_names.extend(
                tuple(f"channel_{index}" for index in range(channel_count))
            )
        if channel_count > 1 and not channel_names:
            channel_names.extend(
                tuple(f"channel_{index}" for index in range(channel_count))
            )
        return {
            "channel_count": channel_count,
            "pixel_type": pixel_type,
            "illumination_types": tuple(illumination_types),
            "fluorophore_names": tuple(fluorophore_names),
            "excitation_wavelengths": tuple(excitation_wavelengths),
            "emission_wavelengths": tuple(emission_wavelengths),
            "channel_names": tuple(channel_names),
            "physical_pixel_sizes": tuple(physical_pixel_sizes),
        }

    return {
        "channel_count": channel_count,
        "pixel_type": pixel_type,
        "illumination_types": tuple(illumination_types),
        "fluorophore_names": tuple(fluorophore_names),
        "excitation_wavelengths": tuple(excitation_wavelengths),
        "emission_wavelengths": tuple(emission_wavelengths),
        "channel_names": tuple(channel_names),
        "physical_pixel_sizes": tuple(physical_pixel_sizes),
    }


def _extract_image_document_distance(root: ET.Element, axis: str) -> float | None:
    axis = axis.lower()
    for element in root.iter():
        attrib = {key.lower(): value for key, value in element.attrib.items()}
        if (
            element.tag.lower().endswith("distance")
            and attrib.get("id", "").lower() == axis
        ):
            value = attrib.get("value")
            if value is None:
                value = element.text
            if value is None:
                first_child = next(iter(element), None)
                value = first_child.text if first_child is not None else None
            if value is None:
                continue
            try:
                return float(value)
            except ValueError:
                return None
    return None


def _extract_czi_xml(czi_file: Any) -> str:
    for attr in ("metadata", "ome_xml", "xml"):
        value = getattr(czi_file, attr, None)
        if callable(value):
            try:
                value = value()
            except TypeError:
                continue
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="ignore")
        if isinstance(value, str):
            return value
    return ""


def _read_czifile_biomarker_region(
    czi_file: Any,
    location: tuple[int, int],
    size: tuple[int, int],
    channel_index: int,
) -> Any:
    x, y = location
    width, height = size
    canvas: np.ndarray | None = None
    subblocks: Any = getattr(czi_file, "subblocks", ())
    if callable(subblocks):
        subblocks = subblocks()
    subblock_list = tuple(cast(Iterable[Any], subblocks))
    origin_x, origin_y = _czifile_coordinate_origin(subblock_list)
    saw_channel = False
    for subblock in subblock_list:
        directory_entry = getattr(subblock, "directory_entry", None)
        if directory_entry is not None:
            for dimension in getattr(directory_entry, "dimension_entries", ()):
                if getattr(dimension, "dimension", None) == "C":
                    if int(getattr(dimension, "start", -1)) == channel_index:
                        saw_channel = True
                        canvas = _copy_czifile_subblock_overlap(
                            canvas,
                            subblock,
                            _subblock_dimension_start(subblock, "X") - origin_x,
                            _subblock_dimension_start(subblock, "Y") - origin_y,
                            x,
                            y,
                            width,
                            height,
                        )
        if int(getattr(subblock, "m_index", -1)) == channel_index:
            saw_channel = True
            canvas = _copy_czifile_subblock_overlap(
                canvas,
                subblock,
                _subblock_dimension_start(subblock, "X") - origin_x,
                _subblock_dimension_start(subblock, "Y") - origin_y,
                x,
                y,
                width,
                height,
            )
    if canvas is not None:
        return Image.fromarray(canvas, mode="L")
    if saw_channel:
        return Image.fromarray(np.zeros((height, width), dtype=np.uint8), mode="L")
    raise LookupError(f"Missing subblock for biomarker channel {channel_index}")


def _czifile_coordinate_origin(subblocks: Iterable[Any]) -> tuple[int, int]:
    min_x: int | None = None
    min_y: int | None = None
    for subblock in subblocks:
        x_start = _subblock_dimension_start(subblock, "X")
        y_start = _subblock_dimension_start(subblock, "Y")
        x_size = _subblock_dimension_size(subblock, "X")
        y_size = _subblock_dimension_size(subblock, "Y")
        if x_size <= 0 or y_size <= 0:
            continue
        min_x = x_start if min_x is None else min(min_x, x_start)
        min_y = y_start if min_y is None else min(min_y, y_start)
    return (min_x or 0, min_y or 0)


def _subblock_dimension_start(subblock: Any, dimension_name: str) -> int:
    starts = getattr(subblock, "dimension_starts", None)
    if isinstance(starts, dict) and dimension_name in starts:
        return int(starts[dimension_name])
    dimension_entries = getattr(
        getattr(subblock, "directory_entry", None), "dimension_entries", ()
    )
    for dimension in dimension_entries:
        if getattr(dimension, "dimension", None) == dimension_name:
            return int(getattr(dimension, "start", 0))
    return 0


def _subblock_dimension_size(subblock: Any, dimension_name: str) -> int:
    dimension_entries = getattr(
        getattr(subblock, "directory_entry", None), "dimension_entries", ()
    )
    for dimension in dimension_entries:
        if getattr(dimension, "dimension", None) == dimension_name:
            return int(getattr(dimension, "size", 0))
    data = getattr(subblock, "_data", None)
    if data is not None and hasattr(data, "shape"):
        shape = getattr(data, "shape", ())
        if len(shape) >= 2:
            return int(shape[-1] if dimension_name == "X" else shape[-2])
    return 0


def _copy_czifile_subblock_overlap(
    canvas: np.ndarray | None,
    subblock: Any,
    start_x: int,
    start_y: int,
    request_x: int,
    request_y: int,
    request_width: int,
    request_height: int,
) -> np.ndarray | None:
    tile_width = _subblock_dimension_size(subblock, "X")
    tile_height = _subblock_dimension_size(subblock, "Y")
    if tile_width <= 0 or tile_height <= 0:
        return canvas
    overlap = _intersect_rect(
        (request_x, request_y, request_x + request_width, request_y + request_height),
        (start_x, start_y, start_x + tile_width, start_y + tile_height),
    )
    if overlap is None:
        return canvas

    data = (
        subblock.data()
        if callable(getattr(subblock, "data", None))
        else getattr(subblock, "_data", subblock)
    )
    tile_array = np.asarray(data).squeeze()
    if tile_array.ndim < 2:
        return canvas
    if tile_array.ndim > 2:
        tile_array = tile_array.reshape((-1, *tile_array.shape[-2:]))[0]

    if canvas is None:
        canvas = np.zeros((request_height, request_width), dtype=tile_array.dtype)

    ox0, oy0, ox1, oy1 = overlap
    canvas[oy0 - request_y : oy1 - request_y, ox0 - request_x : ox1 - request_x] = tile_array[
        oy0 - start_y : oy1 - start_y,
        ox0 - start_x : ox1 - start_x,
    ]
    return canvas


def _read_pylibczirw_region(
    czi_document: Any,
    scene: _PylibCziScene | None,
    location: tuple[int, int],
    size: tuple[int, int],
    channel_index: int,
) -> Image.Image:
    if scene is None:
        scene = _select_pylibczirw_scene(czi_document)
    x, y = location
    width, height = size
    scene_x, scene_y, _, _ = scene.rect
    read_args: dict[str, Any] = {
        "plane": {"C": channel_index},
        "roi": (scene_x + x, scene_y + y, width, height),
    }
    if scene.index is not None:
        read_args["scene"] = scene.index
    data = czi_document.read(**read_args)
    return _pylibczirw_array_to_image(data, width, height)


def _pylibczirw_array_to_image(data: Any, width: int, height: int) -> Image.Image:
    array = np.asarray(data)
    if array.ndim == 3 and array.shape[-1] == 1:
        array = array[:, :, 0]
    if array.ndim > 2:
        return Image.fromarray(array)
    if array.shape != (height, width):
        padded = np.zeros((height, width), dtype=array.dtype)
        copy_height = min(height, array.shape[0]) if array.ndim >= 1 else 0
        copy_width = min(width, array.shape[1]) if array.ndim >= 2 else 0
        if copy_height > 0 and copy_width > 0:
            padded[:copy_height, :copy_width] = array[:copy_height, :copy_width]
        array = padded
    return Image.fromarray(array)


def _read_bioformats_biomarker_region(
    reader: Any,
    location: tuple[int, int],
    size: tuple[int, int],
    channel_index: int,
    series: int = 0,
    scenes: tuple[_BioformatsScene, ...] = (),
) -> Any:
    image_data = _read_bioformats_canvas_region(
        reader, location, size, channel_index, series, scenes
    )
    if isinstance(image_data, list):
        return image_data
    if hasattr(image_data, "shape") and len(image_data.shape) == 2:
        return Image.fromarray(image_data, mode="L")
    return Image.fromarray(image_data)


def _read_bioformats_canvas_region(
    reader: Any,
    location: tuple[int, int],
    size: tuple[int, int],
    channel_index: int,
    series: int = 0,
    scenes: tuple[_BioformatsScene, ...] = (),
) -> Any:
    x, y = location
    width, height = size
    if scenes:
        canvas = np.zeros((height, width), dtype=np.uint8)
        for scene in scenes:
            overlap = _intersect_rect(
                (x, y, x + width, y + height),
                (
                    scene.offset[0],
                    scene.offset[1],
                    scene.offset[0] + scene.size[0],
                    scene.offset[1] + scene.size[1],
                ),
            )
            if overlap is None:
                continue
            ox0, oy0, ox1, oy1 = overlap
            tile = reader.read(
                c=channel_index,
                z=0,
                t=0,
                series=scene.index,
                rescale=False,
                XYWH=(
                    ox0 - scene.offset[0],
                    oy0 - scene.offset[1],
                    ox1 - ox0,
                    oy1 - oy0,
                ),
            )
            tile_array = np.asarray(tile)
            if tile_array.ndim == 3:
                tile_array = tile_array[:, :, 0]
            canvas[oy0 - y : oy1 - y, ox0 - x : ox1 - x] = tile_array[
                : oy1 - oy0, : ox1 - ox0
            ]
        return canvas

    image_data = reader.read(
        c=channel_index,
        z=0,
        t=0,
        series=series,
        rescale=False,
        XYWH=(x, y, width, height),
    )
    return image_data


def _intersect_rect(
    first: tuple[int, int, int, int], second: tuple[int, int, int, int]
) -> tuple[int, int, int, int] | None:
    x0 = max(first[0], second[0])
    y0 = max(first[1], second[1])
    x1 = min(first[2], second[2])
    y1 = min(first[3], second[3])
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)
