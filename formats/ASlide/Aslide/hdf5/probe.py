from __future__ import annotations

from pathlib import Path

import h5py


_HDF5_EXTENSIONS = {".h5", ".hdf5", ".h5ad"}
_MARKER_ATTRIBUTE_NAMES = ("markers", "marker_names", "channel_names", "channels")


def is_hdf5_multiplex_candidate(path: str) -> bool:
    file_path = Path(path)
    if file_path.suffix.lower() not in _HDF5_EXTENSIONS:
        return False

    try:
        with h5py.File(path, "r") as handle:
            if _looks_like_anndata(handle):
                return False

            for dataset in _iter_datasets(handle):
                if _is_multiplex_dataset(dataset):
                    return True
    except Exception:
        return False

    return False


def _looks_like_anndata(handle: h5py.File) -> bool:
    encoding_type = _decode_scalar(handle.attrs.get("encoding-type"))
    if str(encoding_type).lower() == "anndata":
        return True
    return "obs" in handle and "var" in handle


def _iter_datasets(handle: h5py.File):
    datasets: list[h5py.Dataset] = []

    def visitor(name: str, obj: h5py.Dataset) -> None:
        if isinstance(obj, h5py.Dataset):
            datasets.append(obj)

    handle.visititems(visitor)
    return datasets


def _is_multiplex_dataset(dataset: h5py.Dataset) -> bool:
    if len(dataset.shape) != 3:
        return False

    channel_count = int(dataset.shape[0])
    if channel_count <= 1:
        return False

    markers = _extract_markers(dataset)
    return markers is not None and len(markers) == channel_count


def _extract_markers(dataset: h5py.Dataset) -> list[str] | None:
    for attribute_name in _MARKER_ATTRIBUTE_NAMES:
        if attribute_name not in dataset.attrs:
            continue
        markers = _normalize_marker_values(dataset.attrs[attribute_name])
        if markers:
            return markers
    return None


def _normalize_marker_values(raw_value: object) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, (bytes, str)):
        values = [raw_value]
    else:
        try:
            values = list(raw_value)
        except TypeError:
            values = [raw_value]

    normalized: list[str] = []
    for value in values:
        decoded = _decode_scalar(value)
        text = str(decoded).strip()
        if text:
            normalized.append(text)
    return normalized


def _decode_scalar(value: object) -> object:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if hasattr(value, "decode") and not isinstance(value, str):
        try:
            return value.decode("utf-8")
        except Exception:
            return value
    return value
