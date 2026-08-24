from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path
from typing import Iterable


PACKAGE_ROOT = Path(__file__).resolve().parent


def collect_library_paths(package_root: Path | None = None) -> list[str]:
    root = package_root or PACKAGE_ROOT
    lib_paths: list[str] = []
    seen: set[str] = set()

    for relative_dir in (
        Path("opencv/lib"),
        Path("sdpc/lib"),
        Path("kfb/lib"),
        Path("tron/lib"),
    ):
        candidate = root / relative_dir
        if not candidate.is_dir():
            continue

        candidate_str = str(candidate)
        if candidate_str not in seen:
            seen.add(candidate_str)
            lib_paths.append(candidate_str)

        for nested_root, _, files in os.walk(candidate):
            if any(
                file_name.endswith(".so") or ".so." in file_name for file_name in files
            ):
                nested_str = str(Path(nested_root))
                if nested_str not in seen:
                    seen.add(nested_str)
                    lib_paths.append(nested_str)

    return lib_paths


def setup_runtime_environment(lib_paths: Iterable[str] | None = None) -> list[str]:
    paths = list(lib_paths or collect_library_paths())
    current_ld_path = os.environ.get("LD_LIBRARY_PATH", "")

    ld_entries: list[str] = []
    if current_ld_path:
        ld_entries.extend(entry for entry in current_ld_path.split(":") if entry)

    for path in paths:
        if path not in ld_entries:
            ld_entries.insert(0, path)

        if path not in sys.path:
            sys.path.append(path)

    os.environ["LD_LIBRARY_PATH"] = ":".join(ld_entries)
    return paths


def preload_shared_libraries(lib_paths: Iterable[str] | None = None) -> list[str]:
    loaded: list[str] = []

    for lib_path in lib_paths or collect_library_paths():
        path_obj = Path(lib_path)
        if not path_obj.is_dir():
            continue

        for file_path in sorted(path_obj.iterdir()):
            if not file_path.is_file():
                continue
            if not (file_path.name.endswith(".so") or ".so." in file_path.name):
                continue

            try:
                ctypes.CDLL(str(file_path), mode=ctypes.RTLD_GLOBAL)
                loaded.append(str(file_path))
            except OSError:
                continue

    return loaded
