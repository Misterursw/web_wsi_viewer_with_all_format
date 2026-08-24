# Supported Formats

ASlide resolves formats through `Aslide.registry.build_default_registry()`. Some entries are selected purely by extension, while others use probes to distinguish multiplex containers from generic formats.

## Capability Matrix

| Format ID | Extensions | Slide family | Backend/dependency | DeepZoom | Biomarkers | Associated images | Label image | Color correction | Bootstrap/native libs |
|---|---|---|---|---|---|---|---|---|---|
| `czi` | `.czi` | runtime-classified | `pylibCZIrw`, Bio-Formats, or `czifile` | Backend-dependent | Runtime-dependent | No static support | No | No | Optional reader extra |
| `ome_tiff` | `.tif`, `.tiff` | multiplex | `tifffile` probe-selected OME-like TIFF | Yes | Yes | No | No | No | No |
| `mcd` | `.mcd` | multiplex | `readimc` | No | Yes | No | No | No | No |
| `hdf5` | `.h5`, `.hdf5`, `.h5ad` | multiplex | `h5py`, image-backed raster probe | No | Yes | No | No | No | No |
| `ims` | `.ims` | multiplex | `h5py`, IMS probe | Yes | Yes | No | No | No | No |
| `qptiff` | `.qptiff` | runtime-classified | `qptifffile` | Yes | Yes for multiplex | No | No | No | No |
| `kfb` | `.kfb` | brightfield | bundled KFB native SDK | Yes | No | Yes | Yes | Yes | Yes |
| `tmap` | `.tmap` | brightfield | bundled TMAP native SDK | Yes | No | Yes | Yes | Yes | Yes |
| `sdpc` | `.sdpc`, `.dyqx` | brightfield | bundled SDPC native SDK | Yes | No | Yes | Yes | Yes | Yes |
| `vsi` | `.vsi` | brightfield | Bio-Formats and Java | Backend-dependent | No | Backend-dependent | No | No | Bio-Formats extra |
| `mds` | `.mds`, `.mdsx` | brightfield | native MDS reader | Yes | No | Yes | Backend-dependent | Yes | No |
| `tron` | `.tron` | brightfield | bundled TRON native SDK | Yes | No | Yes | No | No | Yes |
| `isyntax` | `.isyntax` | brightfield | `pyisyntax` | Yes | No | Yes | No | No | No |
| `dyj` | `.dyj` | brightfield | native DYJ reader | Yes | No | Backend-dependent | No | Yes | No |
| `ibl` | `.ibl` | brightfield | native iBL reader | Yes | No | Backend-dependent | No | No | No |
| `zyp` | `.zyp` | brightfield | native ZYP reader | Yes | No | Backend-dependent | No | No | No |
| `bif` | `.bif` | brightfield | BIF/OpenSlide-compatible reader | Yes | No | Backend-dependent | No | No | No |
| `openslide` | `.svs`, `.svslide`, `.ndpi`, `.vms`, `.vmu`, `.scn`, `.mrxs` | brightfield | OpenSlide | Yes | No | Yes | Backend-dependent | No | OpenSlide libraries |
| `generic_tiff` | `.tif`, `.tiff` | brightfield | generic TIFF reader | No | No | No | No | No | No |

## Extension and Probe Notes

`.tif` and `.tiff` are shared by `ome_tiff` and `generic_tiff`. ASlide probes for an OME-like multiplex TIFF first. If the probe does not match, the file falls back to generic TIFF behavior.

`.h5`, `.hdf5`, and `.h5ad` are only supported when the container exposes image-backed channel data. Table-only AnnData files are not reconstructed into slide images.

`.sdpc` and `.dyqx` share the SDPC backend.

## Runtime-Classified Formats

QPTIFF and CZI are resolved by extension but classified semantically after opening. A brightfield file supports `read_region()`. A multiplex file supports `list_biomarkers()` and `read_biomarker_region()`.

## Optional Dependencies

VSI and the Bio-Formats CZI path require `python-bioformats`, `python-javabridge`, and a working Java runtime. The lightweight CZI path uses the `czi` extra. Native SDK formats may require `setup_runtime_environment()` when shared libraries are not found automatically.
