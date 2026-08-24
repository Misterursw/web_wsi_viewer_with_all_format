# ASlide

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Linux-lightgrey.svg)](https://www.linux.org/)
[![License](https://img.shields.io/badge/license-GPL%203.0-green.svg)](https://www.gnu.org/licenses/gpl-3.0.en.html)

> A unified Python API for reading whole-slide images in digital pathology.

ASlide wraps OpenSlide-backed formats, vendor SDK-backed formats, and multiplex image containers behind one `Slide(path)` interface. It is designed for pathology preprocessing, tile extraction, viewer integration, and research workflows that need to handle multiple WSI vendors without rewriting reader code for every format.

## Highlights

- One `Slide(path)` entry point across supported brightfield and multiplex formats
- Runtime slide-family behavior for formats that can be brightfield or multiplex, such as QPTIFF and CZI
- DeepZoom DZI and tile generation through `DeepZoom`
- Biomarker-aware reads for multiplex containers and channel exports
- Registry-backed backend selection with capability metadata
- Runtime helpers for bundled native SDK libraries

## Quick Install

```bash
pip install git+https://github.com/MrPeterJin/ASlide.git
```

For optional readers:

```bash
pip install 'git+https://github.com/MrPeterJin/ASlide.git#egg=Aslide[bioformats]'
pip install 'git+https://github.com/MrPeterJin/ASlide.git#egg=Aslide[czi]'
```

See [Installation](docs/installation.md) for platform requirements, optional extras, Java/Bio-Formats setup, and native-library runtime setup.

## Minimal Example

```python
from Aslide import Slide

with Slide("sample.svs") as slide:
    print(slide.dimensions)
    region = slide.read_region((0, 0), 0, (512, 512))
```

Multiplex slides use explicit biomarker reads:

```python
from Aslide import Slide

with Slide("sample.qptiff") as slide:
    biomarkers = slide.list_biomarkers()
    region = slide.read_biomarker_region((0, 0), 0, (512, 512), biomarkers[0])
```

## Supported Formats

ASlide supports OpenSlide formats such as SVS, NDPI, SCN, MRXS, VMS, and VMU; vendor/native formats such as KFB, SDPC/DYQX, TMAP, MDS/MDSX, TRON, iSyntax, DYJ, iBL, ZYP, and BIF; and multiplex formats such as QPTIFF, OME-like TIFF, HDF5/H5AD image-backed containers, IMS, MCD, CZI, and VSI.

The complete capability matrix is in [Supported Formats](docs/formats.md).

## Documentation

- [Documentation Home](docs/index.md)
- [Installation](docs/installation.md)
- [Quick Start](docs/quickstart.md)
- [Supported Formats](docs/formats.md)
- [API Reference](docs/api.md)
- [Brightfield Slides](docs/brightfield.md)
- [Multiplex Slides](docs/multiplex.md)
- [DeepZoom](docs/deepzoom.md)
- [Backends and Registry](docs/backends.md)
- [Examples](docs/examples.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Legal Notice and Acknowledgments](docs/legal.md)

## License

ASlide is distributed under the GPL 3.0 License. See [Legal Notice and Acknowledgments](docs/legal.md) and [LICENSE](LICENSE) for details.

## Contact

- Author: MrPeterJin
- Email: petergamsing@gmail.com
- GitHub: [@MrPeterJin](https://github.com/MrPeterJin)
