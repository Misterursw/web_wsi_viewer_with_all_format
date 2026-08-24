from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class NormalizedCziMetadata:
    channel_count: int
    pixel_type: str | None = None
    illumination_types: tuple[str, ...] = ()
    fluorophore_names: tuple[str, ...] = ()
    excitation_wavelengths: tuple[float, ...] = ()
    emission_wavelengths: tuple[float, ...] = ()
    channel_names: tuple[str, ...] = ()
    physical_pixel_sizes: tuple[float, ...] = ()


def normalize_czi_metadata(raw: Mapping[str, Any]) -> NormalizedCziMetadata:
    return NormalizedCziMetadata(
        channel_count=int(raw.get("channel_count", 0)),
        pixel_type=raw.get("pixel_type"),
        illumination_types=tuple(raw.get("illumination_types", ())),
        fluorophore_names=tuple(raw.get("fluorophore_names", ())),
        excitation_wavelengths=tuple(raw.get("excitation_wavelengths", ())),
        emission_wavelengths=tuple(raw.get("emission_wavelengths", ())),
        channel_names=tuple(raw.get("channel_names", ())),
        physical_pixel_sizes=tuple(raw.get("physical_pixel_sizes", ())),
    )


def classify_czi_family(metadata: NormalizedCziMetadata) -> str:
    brightfield = _has_brightfield_evidence(metadata)
    multiplex = _has_multiplex_evidence(metadata)

    if brightfield and multiplex:
        raise ValueError("conflicting CZI metadata prevents classification")
    if brightfield:
        return "brightfield"
    if multiplex:
        return "multiplex"
    raise LookupError("insufficient evidence to classify CZI slide family")


def _has_brightfield_evidence(metadata: NormalizedCziMetadata) -> bool:
    illumination = {item.strip().lower() for item in metadata.illumination_types}
    if "transmitted" in illumination or "transmitted light" in illumination:
        return True

    pixel_type = (metadata.pixel_type or "").strip().lower()
    if pixel_type in {"bgr24", "rgb24"} and metadata.channel_count <= 3:
        return True

    return False


def _has_multiplex_evidence(metadata: NormalizedCziMetadata) -> bool:
    illumination = {item.strip().lower() for item in metadata.illumination_types}
    if any("fluores" in item for item in illumination):
        return True

    if metadata.fluorophore_names:
        return True

    if metadata.excitation_wavelengths or metadata.emission_wavelengths:
        return True

    return False
