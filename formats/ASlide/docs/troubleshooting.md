# Troubleshooting

## Shared Library Not Found

If importing or opening a slide fails with a shared-library error, verify that bundled library directories exist in the installed package.

```bash
ASLIDE_PATH=/path/to/site-packages/Aslide
ls $ASLIDE_PATH/sdpc/lib
ls $ASLIDE_PATH/kfb/lib
ls $ASLIDE_PATH/tron/lib
```

Then initialize runtime paths before opening slides:

```python
from Aslide.bootstrap import setup_runtime_environment

setup_runtime_environment()
```

## Runtime Environment Not Configured

Some native SDKs may need explicit `LD_LIBRARY_PATH` entries.

```bash
export LD_LIBRARY_PATH=$ASLIDE_PATH/sdpc/lib:$ASLIDE_PATH/tron/lib:$LD_LIBRARY_PATH
```

You can also source the install-generated helper:

```bash
source /path/to/site-packages/Aslide/setup_env.sh
```

## Missing Optional Backend Dependencies

If a format is reported as unavailable, install the matching optional dependencies.

Bio-Formats-backed readers:

```bash
pip install 'git+https://github.com/MrPeterJin/ASlide.git#egg=Aslide[bioformats]'
```

CZI lightweight reader path:

```bash
pip install 'git+https://github.com/MrPeterJin/ASlide.git#egg=Aslide[czi]'
```

## Java or Bio-Formats Unavailable

Bio-Formats requires a working Java runtime.

```bash
java -version
echo $JAVA_HOME
```

If Java is installed but not visible, export `JAVA_HOME` and add it to `PATH`.

## NumPy ABI Issues

ASlide pins `numpy<2` because several compiled readers and scientific dependencies can fail when they are built against a different NumPy ABI. If a compiled dependency fails after upgrading NumPy, reinstall in an environment that keeps `numpy<2`.

## Permission Errors During Installation

Prefer installing into a virtual environment or conda environment. If user-level installation is required:

```bash
python setup.py install --user
```

Avoid `sudo` inside conda or virtual environments unless you intentionally want a system-wide install.

## Reinstall Bundled Libraries

If bundled library files are missing, reinstall from source:

```bash
python setup.py install --force
```

Install `patchelf` before reinstalling when possible so SDPC shared libraries can be patched to prefer local dependencies.
