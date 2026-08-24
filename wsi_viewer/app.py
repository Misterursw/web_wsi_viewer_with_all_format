"""
WSI Viewer - Flask + OpenSeadragon
支持 .ndpi 等 OpenSlide 格式的全切片图像阅片工具
功能：文件浏览、多切片同步对比、实时DZI瓦片渲染、标注画框
"""

import os
import io
import json
import math
import threading
from pathlib import Path
from urllib.parse import unquote
from flask import Flask, request, jsonify, send_file, render_template, abort

import openslide
from openslide import OpenSlide
from openslide.deepzoom import DeepZoomGenerator
from PIL import Image

app = Flask(__name__)


def get_path_arg():
    """从原始 query string 中获取 path 参数。
    解决两个问题：
    1. Werkzeug/parse_qs 会将 + 解释为空格，导致文件名含 + 的路径出错。
       使用 unquote（非 unquote_plus）只做 %xx 解码，保留 + 字符。
    2. nginx proxy_pass 使用 $rest$is_args$args，当 $rest 已含查询串时会重复，
       导致 query_string 形如 "path=xxx?path=xxx"，只取第一段。
    """
    raw = request.query_string.decode("utf-8", errors="replace")
    # 若 query string 因 nginx 重复而含有嵌套的 "?"，只取第一段
    raw = raw.split("?")[0]
    for part in raw.split("&"):
        if part.startswith("path="):
            return unquote(part[5:])
    return ""

# ── 配置 ────────────────────────────────────────────────────────────────────
# 默认扫描根目录，可通过环境变量 WSI_ROOT 覆盖
WSI_ROOT = os.environ.get(
    "WSI_ROOT",
    "/path/to/your/wsi_slides"
)
ANNOTATION_FILE = os.path.join(os.path.dirname(__file__), "annotations.json")
TILE_SIZE = 256
OVERLAP = 1
TILE_FORMAT = "jpeg"
TILE_QUALITY = 75

# 支持的 WSI 扩展名
WSI_EXTENSIONS = {".ndpi", ".svs", ".tiff", ".tif", ".scn", ".mrxs", ".vms", ".vmu"}

# 全局 slide 缓存（避免重复打开）
_slide_cache: dict[str, tuple[OpenSlide, DeepZoomGenerator]] = {}
_cache_lock = threading.Lock()


def _get_slide(path: str):
    """获取已缓存的 OpenSlide + DeepZoomGenerator，不存在则创建"""
    with _cache_lock:
        if path not in _slide_cache:
            # 限制缓存大小
            if len(_slide_cache) > 8:
                oldest = next(iter(_slide_cache))
                _slide_cache[oldest][0].close()
                del _slide_cache[oldest]
            slide = OpenSlide(path)
            dz = DeepZoomGenerator(slide, tile_size=TILE_SIZE, overlap=OVERLAP, limit_bounds=True)
            _slide_cache[path] = (slide, dz)
        return _slide_cache[path]


def _load_annotations():
    if os.path.exists(ANNOTATION_FILE):
        with open(ANNOTATION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_annotations(data):
    with open(ANNOTATION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── 路由：页面 ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── 路由：文件浏览 ────────────────────────────────────────────────────────────

@app.route("/api/ls")
def api_ls():
    """列出目录内容，返回子目录和 WSI 文件"""
    rel = get_path_arg()
    base = Path(WSI_ROOT)
    target = (base / rel).resolve()
    # 安全检查：不允许跳出根目录
    try:
        target.relative_to(base)
    except ValueError:
        abort(403)

    if not target.is_dir():
        abort(404)

    dirs = []
    files = []
    try:
        for entry in sorted(target.iterdir()):
            if entry.name.startswith("$") or entry.name.startswith("."):
                continue
            if entry.is_dir():
                dirs.append({"name": entry.name, "type": "dir"})
            elif entry.suffix.lower() in WSI_EXTENSIONS:
                files.append({"name": entry.name, "type": "wsi"})
    except PermissionError:
        abort(403)

    return jsonify({
        "path": rel,
        "dirs": dirs,
        "files": files,
        "root": str(base)
    })


# ── 路由：切片元信息 ──────────────────────────────────────────────────────────

@app.route("/api/slide_info")
def api_slide_info():
    rel = get_path_arg()
    full_path = str((Path(WSI_ROOT) / rel).resolve())
    try:
        Path(full_path).relative_to(Path(WSI_ROOT))
    except ValueError:
        abort(403)
    if not os.path.exists(full_path):
        abort(404)

    slide, dz = _get_slide(full_path)
    return jsonify({
        "path": rel,
        "dimensions": list(slide.dimensions),
        "level_count": slide.level_count,
        "level_dimensions": [list(d) for d in slide.level_dimensions],
        "level_downsamples": slide.level_downsamples,
        "dz_tile_size": TILE_SIZE,
        "dz_overlap": OVERLAP,
        "dz_level_count": dz.level_count,
        "dz_level_tiles": [list(dz.level_tiles[i]) for i in range(dz.level_count)],
        "properties": {k: v for k, v in slide.properties.items()
                       if k in ("openslide.mpp-x", "openslide.mpp-y",
                                "openslide.objective-power", "hamamatsu.Created",
                                "tiff.ImageDescription")},
    })


# ── 路由：DZI 描述文件 ────────────────────────────────────────────────────────

@app.route("/api/dzi")
def api_dzi():
    rel = get_path_arg()
    full_path = str((Path(WSI_ROOT) / rel).resolve())
    try:
        Path(full_path).relative_to(Path(WSI_ROOT))
    except ValueError:
        abort(403)
    if not os.path.exists(full_path):
        abort(404)

    slide, dz = _get_slide(full_path)
    w, h = slide.dimensions
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<Image xmlns="http://schemas.microsoft.com/deepzoom/2008"'
        f' Format="{TILE_FORMAT}" Overlap="{OVERLAP}" TileSize="{TILE_SIZE}">'
        f'<Size Width="{w}" Height="{h}"/>'
        f'</Image>'
    )
    return app.response_class(xml, mimetype="application/xml")


# ── 路由：DZI 瓦片 ────────────────────────────────────────────────────────────

@app.route("/api/tile/<int:level>/<int:col>/<int:row>")
def api_tile(level, col, row):
    rel = get_path_arg()
    full_path = str((Path(WSI_ROOT) / rel).resolve())
    try:
        Path(full_path).relative_to(Path(WSI_ROOT))
    except ValueError:
        abort(403)
    if not os.path.exists(full_path):
        abort(404)

    try:
        _, dz = _get_slide(full_path)
        tile = dz.get_tile(level, (col, row))
        buf = io.BytesIO()
        tile.save(buf, format="JPEG", quality=TILE_QUALITY)
        buf.seek(0)
        return send_file(buf, mimetype="image/jpeg")
    except Exception:
        # 返回空白白色瓦片
        img = Image.new("RGB", (TILE_SIZE, TILE_SIZE), (255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)
        return send_file(buf, mimetype="image/jpeg")


# ── 路由：缩略图 ──────────────────────────────────────────────────────────────

@app.route("/api/thumbnail")
def api_thumbnail():
    rel = get_path_arg()
    size = int(request.args.get("size", 256))
    size = min(max(size, 32), 1024)
    full_path = str((Path(WSI_ROOT) / rel).resolve())
    try:
        Path(full_path).relative_to(Path(WSI_ROOT))
    except ValueError:
        abort(403)

    slide, _ = _get_slide(full_path)
    thumb = slide.get_thumbnail((size, size))
    buf = io.BytesIO()
    thumb.save(buf, format="JPEG", quality=80)
    buf.seek(0)
    return send_file(buf, mimetype="image/jpeg")


# ── 路由：标注 CRUD ───────────────────────────────────────────────────────────

@app.route("/api/annotations", methods=["GET"])
def get_annotations():
    rel = get_path_arg()
    data = _load_annotations()
    return jsonify(data.get(rel, []))


@app.route("/api/annotations", methods=["POST"])
def save_annotations():
    rel = get_path_arg()
    body = request.get_json(force=True)
    data = _load_annotations()
    data[rel] = body
    _save_annotations(data)
    return jsonify({"status": "ok"})


@app.route("/api/annotations", methods=["DELETE"])
def delete_annotation():
    rel = get_path_arg()
    idx = request.args.get("idx", type=int)
    data = _load_annotations()
    annots = data.get(rel, [])
    if idx is not None and 0 <= idx < len(annots):
        annots.pop(idx)
        data[rel] = annots
        _save_annotations(data)
    return jsonify({"status": "ok"})


# ── 路由：列出同一病例的相关切片 ─────────────────────────────────────────────

@app.route("/api/case_slides")
def api_case_slides():
    """给定一个 ndpi 文件路径，返回同目录下同病例的所有切片"""
    rel = get_path_arg()
    full_path = (Path(WSI_ROOT) / rel).resolve()
    parent = full_path.parent
    try:
        parent.relative_to(Path(WSI_ROOT))
    except ValueError:
        abort(403)

    # 提取病例号（如 K2024-0001）
    stem = full_path.stem
    # 病例号通常是文件名下划线前的部分
    case_id = stem.split("_")[0] if "_" in stem else stem

    siblings = []
    for f in sorted(parent.iterdir()):
        if f.suffix.lower() in WSI_EXTENSIONS and f.stem.startswith(case_id):
            stain = f.stem.replace(case_id + "_", "").split("+-")[0]
            rel_path = str(f.relative_to(Path(WSI_ROOT)))
            siblings.append({"name": f.name, "path": rel_path, "stain": stain})

    return jsonify({"case_id": case_id, "slides": siblings})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="WSI Viewer")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--root", default=WSI_ROOT)
    args = parser.parse_args()
    WSI_ROOT = args.root
    print(f"WSI Root: {WSI_ROOT}")
    print(f"Listening on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, threaded=True)
