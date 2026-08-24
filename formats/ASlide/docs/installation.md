# Installation

ASlide targets Linux and Python 3.10 or newer. The package bundles several native SDK libraries and uses optional Python extras for readers that are harder to install everywhere.

## Prerequisites

- Linux, tested on Ubuntu 22.04/24.04, Red Hat 9.6, and similar distributions
- Python 3.10 or newer
- OpenSlide support through `openslide-bin` and `openslide-python`
- `patchelf` is recommended when reinstalling bundled SDPC libraries so runtime paths stay local to the package

The base install pins `numpy<2` because several compiled scientific dependencies are still sensitive to NumPy ABI changes.

## Install from GitHub

```bash
pip install git+https://github.com/MrPeterJin/ASlide.git
```

Source installation is also supported:

```bash
git clone https://github.com/MrPeterJin/ASlide.git
cd ASlide
python setup.py install
```

The install step copies bundled OpenCV, KFB, TRON, and SDPC shared libraries into the installed package and creates optional runtime helper scripts.

## Optional Bio-Formats Support

Use the `bioformats` extra for readers that require Java-backed Bio-Formats, including VSI and the Bio-Formats CZI fallback path.

```bash
pip install 'git+https://github.com/MrPeterJin/ASlide.git#egg=Aslide[bioformats]'
```

Bio-Formats support requires:

- `python-bioformats`
- `python-javabridge`
- Java 11 or newer available on `PATH`, or exposed through `JAVA_HOME`

Example Java setup:

```bash
export JAVA_HOME=/path/to/your/jdk
export PATH="$JAVA_HOME/bin:$PATH"
```

## Optional CZI Support

Use the `czi` extra when you need the lightweight Zeiss CZI path without forcing a full Java/Bio-Formats environment.

```bash
pip install 'git+https://github.com/MrPeterJin/ASlide.git#egg=Aslide[czi]'
```

For environments already pinned to `numpy<2`, install the CZI reader dependencies without letting pip re-resolve NumPy:

```bash
python -m pip install pylibCZIrw xmltodict --no-deps
```

## Runtime Library Setup

Most bundled backends work after installation. If a backend still needs explicit runtime library hints, configure the process before opening slides.

Recommended Python setup:

```python
from Aslide.bootstrap import setup_runtime_environment

setup_runtime_environment()
from Aslide import Slide
```

Manual shell setup:

```bash
ASLIDE_PATH=/path/to/site-packages/Aslide
export LD_LIBRARY_PATH=$ASLIDE_PATH/sdpc/lib:$ASLIDE_PATH/tron/lib:$LD_LIBRARY_PATH
```

Generated helper script:

```bash
source /path/to/site-packages/Aslide/setup_env.sh
```

## Base Dependencies

The base package installs `numpy<2`, `Pillow`, `h5py`, `openslide-bin`, `openslide-python`, `qptifffile`, `tifffile`, `readimc`, `imageio`, `pandas`, `pyisyntax`, and `olefile`.
