import os
import importlib

SO_FILES_DIR = os.path.join(os.path.dirname(__file__), "lib")
SO_FILES = [
    os.path.join(SO_FILES_DIR, file_name)
    for file_name in os.listdir(SO_FILES_DIR)
    if file_name.endswith(".so")
]


def __getattr__(name: str):
    if name == "KfbSlide":
        module = importlib.import_module(".kfb_slide", __name__)
        return module.KfbSlide
    if name == "ColorCorrection":
        module = importlib.import_module(".color_correction", __name__)
        return module.ColorCorrection
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["KfbSlide", "ColorCorrection"]
