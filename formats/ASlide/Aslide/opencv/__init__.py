from __future__ import annotations

from ..bootstrap import (
    collect_library_paths,
    preload_shared_libraries,
    setup_runtime_environment,
)


def setup_opencv_environment() -> list[str]:
    lib_paths = [path for path in collect_library_paths() if "/opencv/lib" in path]
    setup_runtime_environment(lib_paths)
    preload_shared_libraries(lib_paths)
    return lib_paths


__all__ = ["setup_opencv_environment"]
