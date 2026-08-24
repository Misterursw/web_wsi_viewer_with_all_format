# 🔬 web_wsi_viewer_with_all_format

## 一个浏览器,看遍所有病理切片与空间组学

> **WSI 阅片 + 20+ 格式统一引擎 + 空间转录组/蛋白热图,全部在服务器端跑,浏览器里看。**
> 不用再为一个打不开的文件格式装第 N 个厂商软件,也不用把 10GB 的切片拷到本地。

---

## 😤 病理数据的三座大山

1. **格式地狱** — `.ndpi .svs .mrxs .kfb .sdpc .qptiff .czi .isyntax ...` 每家扫描仪一个私有格式,
   每个格式一个付费/绑 Windows 的查看器
2. **文件巨兽** — 一张全切片几个 GB,同事要看一眼?拷半小时。服务器上的数据,本地干着急
3. **空间组学没处看** — 好不容易跑出空间转录组/蛋白预测结果,只能在 notebook 里画静态散点,
   没法和 H&E 原图叠着放大缩小看

**三件套,一次解决。**

## 📦 三件套

### 1️⃣ WSI Viewer — 服务器端实时阅片

浏览器里的"数字显微镜":文件树浏览、**单图/双图/四图布局、多切片同步联动缩放**、
实时 DeepZoom 瓦片渲染、标注画框、同病例多染色切片一键关联。

- 数据不出服务器,笔记本/平板打开网页就能看
- 基于 OpenSlide + OpenSeadragon,流式取瓦片,再大的图也不卡

```bash
pip install flask openslide-python pillow
export WSI_ROOT=/path/to/your/wsi_slides
python3 wsi_viewer/app.py --port 5000
# 打开 http://<服务器IP>:5000
```

### 2️⃣ Format Engine — 20+ 格式,一个 `Slide(path)`

`formats/ASlide/` 是一个统一的 WSI 读取引擎(基于开源项目 [ASlide](https://github.com/MrPeterJin/ASlide),
GPL 3.0),把 OpenSlide 格式、厂商 SDK 私有格式、多重成像容器全部收进一个 API:

```python
from Aslide import Slide

with Slide("/path/to/slide.kfb") as slide:     # 换成 .svs/.qptiff/.mcd/.czi 都行,代码不变
    print(slide.dimensions)
    region = slide.read_region((0, 0), 0, (512, 512))
```

| 家族 | 格式 |
|---|---|
| 明场(OpenSlide) | SVS · NDPI · SCN · MRXS · VMS · VMU · TIFF |
| 厂商私有(内置 SDK,Linux 直接跑) | **KFB · SDPC/DYQX · TMAP · MDS/MDSX · TRON · iSyntax · DYJ · iBL · ZYP · BIF** |
| 多重成像/空间蛋白(按 biomarker 逐通道读) | **QPTIFF · OME-TIFF · MCD · IMS · CZI · VSI · HDF5/H5AD** |

- 注册表 + 能力元数据自动选后端;DeepZoom DZI/瓦片生成开箱即用
- 已打包厂商原生 `.so`(SDPC、KFB、OpenCV 等),Linux x86_64 免装厂商软件
- 详见 `formats/ASlide/README.md` 与 `formats/ASlide/docs/`

### 3️⃣ Spot Studio — 空间转录组 × 原图联动热图

给**空间转录组 / 空间蛋白预测结果**的服务器端查看器:左边是 H&E 全切片(可无限缩放),
右边把每个 spot/tile 的基因表达或蛋白强度以热图形式**叠在原图上**,透明度可调,
基因下拉即换,mean/median/max 聚合任选。

- 输入约定:每个 slide 一个结果目录,含 `done.json`(元信息)、`tiles.csv`(spot 坐标)、
  `pred_expr_selected.npz`(表达矩阵),由你的推理管线生成
- 蛋白数据同样适用——把通道强度当作"基因"放进 npz 即可

```bash
pip install flask openslide-python pillow numpy pandas
export VISUAL_ST_RESULTS_ROOT=/path/to/your/st_results
python3 spot_viewer/app.py --port 8787
# 打开 http://<服务器IP>:8787
```

## 🎯 适合谁

| 人群 | 拿走哪件 |
|---|---|
| 🏥 病理科/数字病理团队 | WSI Viewer 内网部署,全科室浏览器阅片 |
| 🧪 空间组学研究者 | Spot Studio 看空转/空蛋结果,和形态学对照 |
| 🛠️ 病理 AI 工程师 | Format Engine 做预处理/切 tile 的统一读取层,再也不用为每个格式写 reader |
| 🖥️ 平台运维 | 三个都是纯 Flask 单文件应用,挂 nginx 即可上线 |

## 📁 结构

```
web_wsi_viewer_with_all_format/
├── wsi_viewer/          # 通用 WSI 阅片(OpenSlide 格式族)
├── spot_viewer/         # 空间组学 spot 热图查看器
└── formats/ASlide/      # 统一格式引擎(含 docs/ 与原生 SDK)
```

三个组件相互独立,可按需单独部署。

## License

- `wsi_viewer/`、`spot_viewer/`:MIT
- `formats/ASlide/`:GPL 3.0(上游 [ASlide](https://github.com/MrPeterJin/ASlide),保留原作者声明与 LICENSE)
