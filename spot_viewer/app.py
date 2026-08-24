import io
import json
import os
import threading
from pathlib import Path
from urllib.parse import unquote

import numpy as np
import openslide
import pandas as pd
from flask import Flask, abort, jsonify, render_template, request, send_file
from openslide import OpenSlide
from openslide.deepzoom import DeepZoomGenerator
from PIL import Image


APP_DIR = Path(__file__).resolve().parent
DEFAULT_RESULTS_ROOT = Path("/path/to/your/st_results")
TILE_SIZE = 256
OVERLAP = 1
TILE_FORMAT = "jpeg"
TILE_QUALITY = 75

app = Flask(__name__, template_folder=str(APP_DIR / "templates"), static_folder=str(APP_DIR / "static"))

RESULTS_ROOT = Path(os.environ.get("VISUAL_ST_RESULTS_ROOT", DEFAULT_RESULTS_ROOT)).resolve()
_slide_cache: dict[str, tuple[OpenSlide, DeepZoomGenerator]] = {}
_cache_lock = threading.Lock()


def get_query_arg(name: str) -> str:
    raw = request.query_string.decode("utf-8", errors="replace").split("?")[0]
    prefix = f"{name}="
    for part in raw.split("&"):
        if part.startswith(prefix):
            return unquote(part[len(prefix):])
    return ""


def _safe_result_dir(slide_name: str) -> Path:
    slide_name = unquote(slide_name or "")
    if not slide_name or "/" in slide_name or "\\" in slide_name or slide_name in {".", ".."}:
        abort(400, "invalid slide")
    slide_dir = (RESULTS_ROOT / slide_name).resolve()
    try:
        slide_dir.relative_to(RESULTS_ROOT)
    except ValueError:
        abort(403)
    if not slide_dir.is_dir():
        abort(404, "slide result not found")
    return slide_dir


def _load_done(slide_dir: Path) -> dict:
    done_path = slide_dir / "done.json"
    if not done_path.exists():
        abort(404, "done.json not found")
    with done_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _source_path(slide_name: str) -> Path:
    slide_dir = _safe_result_dir(slide_name)
    done = _load_done(slide_dir)
    source = Path(done.get("source_path", ""))
    if not source.exists():
        abort(404, f"source WSI not found: {source}")
    return source


def _get_slide(path: Path):
    key = str(path)
    with _cache_lock:
        if key not in _slide_cache:
            if len(_slide_cache) > 8:
                oldest = next(iter(_slide_cache))
                _slide_cache[oldest][0].close()
                del _slide_cache[oldest]
            slide = OpenSlide(key)
            dz = DeepZoomGenerator(slide, tile_size=TILE_SIZE, overlap=OVERLAP, limit_bounds=True)
            _slide_cache[key] = (slide, dz)
        return _slide_cache[key]


def _np_scalar(value):
    if isinstance(value, np.generic):
        return value.item()
    return value


def _normalize(values: np.ndarray):
    values = values.astype(np.float32, copy=False)
    finite = np.isfinite(values)
    if not finite.any():
        return np.zeros_like(values, dtype=np.float32), {"lo": 0.0, "hi": 0.0}
    valid = values[finite]
    lo, hi = np.percentile(valid, [2, 98])
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        lo = float(np.nanmin(valid))
        hi = float(np.nanmax(valid))
    if hi <= lo:
        norm = np.zeros_like(values, dtype=np.float32)
    else:
        norm = np.clip((values - lo) / (hi - lo), 0, 1).astype(np.float32)
    norm[~finite] = 0
    return norm, {"lo": float(lo), "hi": float(hi)}


def _reduce_expr(expr: np.ndarray, reducer: str):
    expr = expr.astype(np.float32, copy=False)
    if reducer == "median":
        return np.nanmedian(expr, axis=(1, 2)).astype(np.float32)
    if reducer == "max":
        return np.nanmax(expr, axis=(1, 2)).astype(np.float32)
    return np.nanmean(expr, axis=(1, 2)).astype(np.float32)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/slides")
def api_slides():
    slides = []
    if not RESULTS_ROOT.exists():
        return jsonify(slides)
    for slide_dir in sorted(p for p in RESULTS_ROOT.iterdir() if p.is_dir()):
        done_path = slide_dir / "done.json"
        pred_path = slide_dir / "pred_expr_selected.npz"
        tiles_path = slide_dir / "tiles.csv"
        if not (done_path.exists() and pred_path.exists() and tiles_path.exists()):
            continue
        try:
            with done_path.open("r", encoding="utf-8") as f:
                done = json.load(f)
            if done.get("status") != "done":
                continue
            genes = [str(g) for g in done.get("genes", [])]
            if not genes:
                with np.load(pred_path, allow_pickle=False) as z:
                    genes = [str(g) for g in z["genes"].tolist()]
            source_path = done.get("source_path", "")
            slides.append(
                {
                    "name": slide_dir.name,
                    "genes": genes,
                    "n_tiles": int(done.get("n_tiles", 0)),
                    "source_exists": bool(source_path),
                    "finished_at": done.get("finished_at", ""),
                    "slide_mpp": done.get("slide_mpp"),
                    "target_mpp": done.get("target_mpp"),
                }
            )
        except Exception as exc:
            slides.append({"name": slide_dir.name, "genes": [], "error": str(exc), "source_exists": False})
    return jsonify(slides)


@app.route("/api/slide_info")
def api_slide_info():
    slide_name = get_query_arg("slide")
    source = _source_path(slide_name)
    slide, dz = _get_slide(source)
    done = _load_done(_safe_result_dir(slide_name))
    return jsonify(
        {
            "slide": slide_name,
            "dimensions": list(slide.dimensions),
            "level_count": slide.level_count,
            "level_dimensions": [list(x) for x in slide.level_dimensions],
            "level_downsamples": list(slide.level_downsamples),
            "dz_tile_size": TILE_SIZE,
            "dz_overlap": OVERLAP,
            "dz_level_count": dz.level_count,
            "dz_level_tiles": [list(dz.level_tiles[i]) for i in range(dz.level_count)],
            "genes": done.get("genes", []),
            "properties": {
                k: v
                for k, v in slide.properties.items()
                if k in ("openslide.mpp-x", "openslide.mpp-y", "openslide.objective-power", "aperio.MPP")
            },
        }
    )


@app.route("/api/dzi")
def api_dzi():
    slide_name = get_query_arg("slide")
    source = _source_path(slide_name)
    slide, _ = _get_slide(source)
    w, h = slide.dimensions
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<Image xmlns="http://schemas.microsoft.com/deepzoom/2008"'
        f' Format="{TILE_FORMAT}" Overlap="{OVERLAP}" TileSize="{TILE_SIZE}">'
        f'<Size Width="{w}" Height="{h}"/>'
        f"</Image>"
    )
    return app.response_class(xml, mimetype="application/xml")


@app.route("/api/tile/<int:level>/<int:col>/<int:row>")
def api_tile(level, col, row):
    slide_name = get_query_arg("slide")
    source = _source_path(slide_name)
    try:
        _, dz = _get_slide(source)
        tile = dz.get_tile(level, (col, row))
        buf = io.BytesIO()
        tile.save(buf, format="JPEG", quality=TILE_QUALITY)
        buf.seek(0)
        return send_file(buf, mimetype="image/jpeg")
    except Exception:
        img = Image.new("RGB", (TILE_SIZE, TILE_SIZE), (255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)
        return send_file(buf, mimetype="image/jpeg")


@app.route("/api/thumbnail")
def api_thumbnail():
    slide_name = get_query_arg("slide")
    size = min(max(request.args.get("size", default=240, type=int), 32), 1024)
    source = _source_path(slide_name)
    slide, _ = _get_slide(source)
    thumb = slide.get_thumbnail((size, size))
    buf = io.BytesIO()
    thumb.save(buf, format="JPEG", quality=80)
    buf.seek(0)
    return send_file(buf, mimetype="image/jpeg")


@app.route("/api/spot_data")
def api_spot_data():
    slide_name = get_query_arg("slide")
    gene = get_query_arg("gene")
    reducer = request.args.get("reducer", "mean")
    if reducer not in {"mean", "median", "max"}:
        reducer = "mean"

    slide_dir = _safe_result_dir(slide_name)
    tiles = pd.read_csv(slide_dir / "tiles.csv")
    if "tile_id" in tiles.columns:
        tiles = tiles.sort_values("tile_id").reset_index(drop=True)

    with np.load(slide_dir / "pred_expr_selected.npz", allow_pickle=False) as z:
        genes = [str(g) for g in z["genes"].tolist()]
        if not gene:
            gene = genes[0]
        if gene not in genes:
            abort(404, f"gene not found: {gene}")
        expr = z["pred_expr"][..., genes.index(gene)]

    n = min(len(tiles), expr.shape[0])
    tiles = tiles.iloc[:n].copy()
    values = _reduce_expr(expr[:n], reducer)
    norm, scale = _normalize(values)

    read_size = tiles["read_size"] if "read_size" in tiles.columns else tiles.get("tile_size", 224)
    xs = tiles["x"].astype(float).to_numpy()
    ys = tiles["y"].astype(float).to_numpy()
    rs = pd.Series(read_size).astype(float).to_numpy()
    tissue = tiles["tissue_fraction"].to_numpy() if "tissue_fraction" in tiles.columns else np.full(n, np.nan)

    points = []
    for i in range(n):
        points.append(
            {
                "tile_id": int(_np_scalar(tiles.iloc[i].get("tile_id", i))),
                "x": float(xs[i]),
                "y": float(ys[i]),
                "w": float(rs[i]),
                "h": float(rs[i]),
                "cx": float(xs[i] + rs[i] / 2),
                "cy": float(ys[i] + rs[i] / 2),
                "value": float(values[i]),
                "norm": float(norm[i]),
                "tissue_fraction": None if not np.isfinite(tissue[i]) else float(tissue[i]),
            }
        )

    done = _load_done(slide_dir)
    return jsonify(
        {
            "slide": slide_name,
            "gene": gene,
            "genes": genes,
            "reducer": reducer,
            "n_tiles": int(n),
            "points": points,
            "scale": scale,
            "slide_mpp": done.get("slide_mpp"),
            "target_mpp": done.get("target_mpp"),
        }
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="WSI + spatial spot heatmap viewer")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--results-root", default=str(DEFAULT_RESULTS_ROOT))
    args = parser.parse_args()
    RESULTS_ROOT = Path(args.results_root).resolve()
    print(f"Results root: {RESULTS_ROOT}")
    print(f"Listening on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, threaded=True)
