from __future__ import division
import ctypes
from ctypes import *
from itertools import count
import PIL.Image
import platform
import io
import os
import numpy as np
from openslide import lowlevel
from openslide.lowlevel import OpenSlideError, OpenSlideUnsupportedFormatError
from openslide._version import __version__
# import kfbHeaderInfo

dirname, _ = os.path.split(os.path.abspath(__file__))
LIB_DIR = os.path.join(dirname, "lib")


def _bundled_library_path(lib_name: str) -> str:
    lib_path = os.path.join(LIB_DIR, lib_name)
    if not os.path.exists(lib_path):
        raise OSError(f"Bundled library not found: {lib_path}")
    return lib_path


def _load_bundled_library(lib_name: str, mode: int = RTLD_GLOBAL) -> ctypes.CDLL:
    return ctypes.CDLL(_bundled_library_path(lib_name), mode=mode)


try:
    _libjpeg = _load_bundled_library("libjpeg.so.9")
    _lib = _load_bundled_library("libkfbslide.so")
    _libOp = _load_bundled_library("libImageOperationLib.so")
except OSError as exc:
    raise OSError(
        "Failed to load bundled KFB shared libraries. "
        f"Expected them under {LIB_DIR}. Original error: {exc}"
    ) from exc

if _libOp is not None:
    DeleteImageDataFunc = _libOp.DeleteImageDataFunc
    DeleteImageDataFunc.argtypes = [c_void_p]
    DeleteImageDataFunc.restype = c_int
else:
    # Define a dummy function to prevent crash on import, but this will leak or crash on use.
    # Better to fail loudly? Or just warn?
    # Given the user context, better to fail if we depend on it.
    print("Warning: libImageOperationLib.so not found. Memory leak may occur.")

    def DeleteImageDataFunc(ptr):
        pass


class KFBSlideError(Exception):
    """docstring for KFBSlideError"""


class _KfbSlide(object):
    def __init__(self, ptr):
        self._as_parameter_ = ptr
        self._valid = True
        self._close = kfbslide_close

    def __del__(self):
        if self._valid:
            self._close(self)

    def invalidate(self):
        self._valid = False

    @classmethod
    def from_param(cls, obj):
        if obj.__class__ != cls:
            raise ValueError("Not an KfbSlide reference")
        if not obj._as_parameter_:
            raise ValueError("Passing undefined slide object")
        if not obj._valid:
            raise ValueError("Passing closed kfbSlide object")
        return obj


# check for errors opening an image file and wrap the resulting handle
def _check_open(result, _func, _args):
    if result is None:
        raise lowlevel.OpenSlideUnsupportedFormatError(
            "Unsupported or missing image file"
        )
    slide = _KfbSlide(c_void_p(result))
    # err = get_error(slide)
    # if err is not None:
    #     raise lowlevel.OpenSlideError(err)
    return slide


# prevent further operations on slide handle after it is closed
def _check_close(_result, _func, args):
    args[0].invalidate()


# check if the library got into an error state after each library call
def _check_error(result, func, args):
    # err = get_error(args[0])
    # if err is not None:
    #     raise lowlevel.OpenSlideError(err)
    return lowlevel._check_string(result, func, args)


# Convert returned NULL-terminated char** into a list of strings
def _check_name_list(result, func, args):
    _check_error(result, func, args)
    names = []
    for i in count():
        name = result[i]
        if not name:
            break
        names.append(name.decode("UTF-8", "replace"))
    return names


# resolve and return an OpenSlide function with the specified properties
def _func(name, restype, argtypes, errcheck=_check_error):
    func = getattr(_lib, name)
    func.argtypes = argtypes
    func.restype = restype
    if errcheck is not None:
        func.errcheck = errcheck
    return func


detect_vendor = _func(
    "kfbslide_detect_vendor", c_char_p, [lowlevel._utf8_p], lowlevel._check_string
)

_kfbslide_open = _func("kfbslide_open", c_void_p, [lowlevel._utf8_p], _check_open)

# _kfbslide_set_attrs = _func("kfbslide_set_attrs", None, [_KfbSlide, c_int, c_int, c_int, c_float, c_double, c_float, c_int])


def kfbslide_open(name):
    osr = _kfbslide_open(name)
    # height, width, scale, spendTime, scanTime, imgCapRes, blkSize = kfbHeaderInfo.GetHeaderInfo(name)
    # _kfbslide_set_attrs(osr, height, width, scale, spendTime, scanTime, imgCapRes, blkSize)
    return osr


kfbslide_close = _func("kfbslide_close", None, [_KfbSlide], lowlevel._check_close)

kfbslide_get_level_count = _func("kfbslide_get_level_count", c_int32, [_KfbSlide])

_kfbslide_get_level_dimensions = _func(
    "kfbslide_get_level_dimensions",
    None,
    [_KfbSlide, c_int32, POINTER(c_int64), POINTER(c_int64)],
)


def kfbslide_get_level_dimensions(osr, level):
    w, h = c_int64(), c_int64()
    _kfbslide_get_level_dimensions(osr, level, byref(w), byref(h))
    return (w.value, h.value)


kfbslide_get_level_downsample = _func(
    "kfbslide_get_level_downsample", c_double, [_KfbSlide, c_int32]
)

kfbslide_get_best_level_for_downsample = _func(
    "kfbslide_get_best_level_for_downsample", c_int32, [_KfbSlide, c_double]
)

_kfbslide_read_region = _func(
    "kfbslide_read_region",
    c_bool,
    [_KfbSlide, c_int32, c_int64, c_int64, POINTER(c_int), POINTER(POINTER(c_ubyte))],
)

_kfbslide_read_roi_region = _func(
    "kfbslide_get_image_roi_stream",
    c_bool,
    [
        _KfbSlide,
        c_int32,
        c_int64,
        c_int64,
        c_int64,
        c_int64,
        POINTER(c_int),
        POINTER(POINTER(c_ubyte)),
    ],
)


def kfbslide_read_region(osr, level, pos_x, pos_y):
    data_length = c_int()
    pixel = POINTER(c_ubyte)()
    if not _kfbslide_read_region(
        osr, level, pos_x, pos_y, byref(data_length), byref(pixel)
    ):
        raise ValueError("Fail to read region")
    # import numpy as np
    # return np.ctypeslib.as_array(pixel, shape=(data_length.value,))

    # Copy data to Python-managed memory
    arr = np.ctypeslib.as_array(pixel, shape=(data_length.value,)).copy()

    # Free C memory
    DeleteImageDataFunc(pixel)

    return PIL.Image.open(io.BytesIO(arr)).convert("RGBA")


def kfbslide_read_roi_region(osr, level, pos_x, pos_y, width, height):
    data_length = c_int()
    pixel = POINTER(c_ubyte)()
    if not _kfbslide_read_roi_region(
        osr, level, pos_x, pos_y, width, height, byref(data_length), byref(pixel)
    ):
        raise ValueError("Fail to read roi region")
    # img = PIL.Image.frombuffer('RGBA', (width, height), pixel, 'raw', 'RGBA', 0, 1)

    # import numpy as np
    # return np.ctypeslib.as_array(pixel, shape=(data_length.value,))

    # Copy data to Python-managed memory
    arr = np.ctypeslib.as_array(pixel, shape=(data_length.value,)).copy()

    # Free C memory
    DeleteImageDataFunc(pixel)

    return PIL.Image.open(io.BytesIO(arr)).convert("RGBA")


kfbslide_property_names = _func(
    "kfbslide_get_property_names", POINTER(c_char_p), [_KfbSlide], _check_name_list
)

kfbslide_property_value = _func(
    "kfbslide_get_property_value", c_char_p, [_KfbSlide, lowlevel._utf8_p]
)

_kfbslide_get_associated_image_names = _func(
    "kfbslide_get_associated_image_names",
    POINTER(c_char_p),
    [_KfbSlide],
    _check_name_list,
)


def kfbslide_get_associated_image_names(osr):
    names = _kfbslide_get_associated_image_names(osr)
    rtn = []
    for name in names:
        if name is None:
            break
        rtn.append(name)
    return rtn


_kfbslide_get_associated_image_dimensions = _func(
    "kfbslide_get_associated_image_dimensions",
    c_void_p,
    [_KfbSlide, lowlevel._utf8_p, POINTER(c_int64), POINTER(c_int64), POINTER(c_int)],
)


def kfbslide_get_associated_image_dimensions(osr, name):
    w, h = c_int64(), c_int64()
    data_length = c_int()
    _kfbslide_get_associated_image_dimensions(
        osr, name, byref(w), byref(h), byref(data_length)
    )
    return (w.value, h.value), data_length.value


_kfbslide_read_associated_image = _func(
    "kfbslide_read_associated_image",
    c_void_p,
    [_KfbSlide, lowlevel._utf8_p, POINTER(POINTER(c_ubyte))],
)


def kfbslide_read_associated_image(osr, name):
    data_length = kfbslide_get_associated_image_dimensions(osr, name)[1]
    pixel = POINTER(c_ubyte)()
    _kfbslide_read_associated_image(osr, name, byref(pixel))
    import numpy as np

    narray = np.ctypeslib.as_array(pixel, shape=(data_length,)).copy()
    DeleteImageDataFunc(pixel)

    from io import BytesIO

    buf = BytesIO(narray)
    from PIL import Image

    return Image.open(buf)


def main():
    kfb_file_path = "/path/to/kfb/file"
    osr = kfbslide_open(kfb_file_path)
    names = kfbslide_get_associated_image_names(osr)
    print(names)
    level_cnt = kfbslide_get_level_count(osr)
    print("Level count : ", level_cnt)
    width = c_int64()
    height = c_int64()
    for level in range(level_cnt):
        _kfbslide_get_level_dimensions(osr, c_int32(level), byref(width), byref(height))
        print("Level {0} : {1}, {2}".format(level, width, height))

        downsample = kfbslide_get_level_downsample(osr, level)
        print("Level {0} downsample : {1}".format(level, downsample))
        print(
            "Level {0} best downsample : {1}".format(
                level, kfbslide_get_best_level_for_downsample(osr, downsample - 1)
            )
        )
    prop_names = kfbslide_property_names(osr)
    print(prop_names)
    for name in prop_names:
        print(name, "  --->  ", kfbslide_property_value(osr, name))

    asso_img_names = kfbslide_get_associated_image_names(osr)
    print("Associate Imagae Names : ", asso_img_names)
    for name in asso_img_names:
        if name is None:
            break
        ksize, datalength = kfbslide_get_associated_image_dimensions(osr, name)
        width, height = ksize
        print(
            name,
            " ---> width : ",
            width,
            ", height : ",
            height,
            ", datalength : ",
            datalength,
        )
        img = kfbslide_read_associated_image(osr, name)
        file_name = "./output/" + name + ".jpg"
        img.save(file_name)
    # '''
    x_mid = int((int(width) // 256 // 2) * 256)
    y_mid = int((int(height) // 256 // 2) * 256)
    data_length = c_int()
    pixel = POINTER(c_ubyte)()
    _kfbslide_read_region(osr, 5, x_mid, y_mid, byref(data_length), byref(pixel))
    import numpy as np

    nparr = np.ctypeslib.as_array(pixel, shape=(data_length.value,))
    with open("./output/img_test.jpg", "wb") as file:
        file.write(nparr)

    # '''
    kfbslide_close(osr)


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print("Error happens : ", err)
