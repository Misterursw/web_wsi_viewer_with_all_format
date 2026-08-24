/**
 * WSI Viewer — 前端主逻辑
 * 依赖：OpenSeadragon (全局 OpenSeadragon)
 */

// ── 状态 ──────────────────────────────────────────────────────────────────────
const MAX_PANELS = 4;
const state = {
  layout: 1,         // 当前宫格数 (1/2/4)
  syncEnabled: true, // 同步联动
  activePanelIdx: 0, // 当前活跃面板
  annotating: false, // 是否在画框模式
  panels: Array.from({ length: MAX_PANELS }, () => ({
    viewer: null,     // OpenSeadragon 实例
    path: null,       // 当前加载的 WSI 路径
    annotations: [],  // 标注列表 [{x,y,w,h,note}]
    annCanvas: null,  // 标注 canvas 元素
    annCtx: null,     // canvas 2D context
  })),
  currentCtxPath: null,  // 右键菜单对应的路径
};
let isSyncing = false; // 防止同步循环

// ── DOM 引用 ─────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const fileTree    = $('file-tree');
const stainFilter = $('stain-filter');
const casePanel   = $('case-panel');
const caseIdLabel = $('case-id-label');
const caseSlidesEl= $('case-slides-list');
const thumbImg    = $('thumb-img');
const thumbEmpty  = $('thumb-empty');
const viewerGrid  = $('viewer-grid');
const infoModal   = $('info-modal');
const infoBody    = $('info-modal-body');
const ctxMenu     = $('ctx-menu');
const btnAnnRect  = $('btn-ann-rect');
const annStatus   = $('ann-status');

// ── 布局切换 ─────────────────────────────────────────────────────────────────
function setLayout(n) {
  state.layout = n;
  viewerGrid.className = `grid-${n}`;
  for (let i = 0; i < MAX_PANELS; i++) {
    const cell = $(`cell-${i}`);
    if (i < n) cell.classList.remove('hidden');
    else cell.classList.add('hidden');
  }
  // 更新布局按钮高亮
  [1, 2, 4].forEach(x => {
    $(`btn-layout-${x}`).classList.toggle('active', x === n);
  });
  // 延迟通知 OSD 容器尺寸变化
  setTimeout(() => {
    state.panels.forEach(p => p.viewer && p.viewer.viewport && p.viewer.forceRedraw());
  }, 50);
}

$('btn-layout-1').addEventListener('click', () => setLayout(1));
$('btn-layout-2').addEventListener('click', () => setLayout(2));
$('btn-layout-4').addEventListener('click', () => setLayout(4));
$('btn-clear-all').addEventListener('click', clearAllPanels);
$('chk-sync').addEventListener('change', e => { state.syncEnabled = e.target.checked; });

// ── 文件浏览器 ───────────────────────────────────────────────────────────────
async function fetchDir(relPath) {
  const res = await fetch(`api/ls?path=${encodeURIComponent(relPath)}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function matchesStainFilter(filename) {
  const q = stainFilter.value.trim().toUpperCase();
  if (!q) return true;
  return filename.toUpperCase().includes(q);
}

function buildDirNode(dir, parentRel) {
  const rel = parentRel ? `${parentRel}/${dir.name}` : dir.name;
  const node = document.createElement('div');
  node.className = 'tree-node';

  const row = document.createElement('div');
  row.className = 'tree-row dir-row';
  row.innerHTML = `<span class="expand-arrow">▶</span><span class="icon">📁</span><span class="label">${escHtml(dir.name)}</span>`;
  row.dataset.rel = rel;
  node.appendChild(row);

  const children = document.createElement('div');
  children.className = 'tree-children';
  node.appendChild(children);

  let loaded = false;
  row.addEventListener('click', async () => {
    const arrow = row.querySelector('.expand-arrow');
    if (!children.classList.contains('open')) {
      if (!loaded) {
        loaded = true;
        children.innerHTML = '<div class="tree-row"><span class="label" style="color:#506070">加载中…</span></div>';
        try {
          const data = await fetchDir(rel);
          children.innerHTML = '';
          data.dirs.forEach(d => children.appendChild(buildDirNode(d, rel)));
          data.files.forEach(f => {
            if (matchesStainFilter(f.name)) children.appendChild(buildFileNode(f, rel));
          });
          if (!children.children.length) children.innerHTML = '<div class="tree-row"><span class="label" style="color:#506070">（空）</span></div>';
        } catch (e) {
          children.innerHTML = `<div class="tree-row"><span class="label" style="color:#ff7070">错误：${e.message}</span></div>`;
        }
      }
      children.classList.add('open');
      arrow.classList.add('open');
    } else {
      children.classList.remove('open');
      arrow.classList.remove('open');
    }
  });

  return node;
}

function buildFileNode(file, parentRel) {
  const rel = `${parentRel}/${file.name}`;
  const node = document.createElement('div');
  node.className = 'tree-node';

  const row = document.createElement('div');
  row.className = 'tree-row wsi-file';
  row.innerHTML = `<span class="icon">🔬</span><span class="label" title="${escHtml(file.name)}">${escHtml(file.name)}</span>`;
  row.dataset.rel = rel;
  node.appendChild(row);

  // 单击：加载到活跃面板 + 查询同病例 + 缩略图
  row.addEventListener('click', e => {
    e.stopPropagation();  // 阻止冒泡到父级 dir-row
    openInPanel(rel, state.activePanelIdx);
    fetchCaseSlides(rel);
    loadThumbnail(rel);
    // 高亮选中
    document.querySelectorAll('.tree-row.selected').forEach(r => r.classList.remove('selected'));
    row.classList.add('selected');
  });

  // 双击：在面板 0 打开（快捷方式）
  row.addEventListener('dblclick', e => { e.stopPropagation(); openInPanel(rel, 0); });

  // 右键：弹出面板选择菜单
  row.addEventListener('contextmenu', e => {
    e.preventDefault();
    state.currentCtxPath = rel;
    showCtxMenu(e.clientX, e.clientY);
  });

  return node;
}

async function loadRootTree() {
  fileTree.innerHTML = '<div class="tree-row"><span class="label" style="color:#506070">加载中…</span></div>';
  try {
    const data = await fetchDir('');
    fileTree.innerHTML = '';
    data.dirs.forEach(d => fileTree.appendChild(buildDirNode(d, '')));
    data.files.forEach(f => {
      if (matchesStainFilter(f.name)) fileTree.appendChild(buildFileNode(f, ''));
    });
    if (!fileTree.children.length) {
      fileTree.innerHTML = '<div class="tree-row"><span class="label" style="color:#506070">（无文件）</span></div>';
    }
  } catch (e) {
    fileTree.innerHTML = `<div class="tree-row"><span class="label" style="color:#ff7070">加载失败：${e.message}</span></div>`;
  }
}

// 染色过滤（重新加载整棵树）
let filterTimer = null;
stainFilter.addEventListener('input', () => {
  clearTimeout(filterTimer);
  filterTimer = setTimeout(loadRootTree, 400);
});

// ── 同病例切片 ───────────────────────────────────────────────────────────────
async function fetchCaseSlides(rel) {
  try {
    const res = await fetch(`api/case_slides?path=${encodeURIComponent(rel)}`);
    const data = await res.json();
    if (!data.slides || data.slides.length <= 1) {
      casePanel.classList.add('hidden');
      return;
    }
    caseIdLabel.textContent = data.case_id;
    caseSlidesEl.innerHTML = '';
    data.slides.forEach(s => {
      const item = document.createElement('div');
      item.className = 'case-slide-item';
      item.innerHTML = `<span class="case-slide-stain">${escHtml(s.stain)}</span><span class="case-slide-name" title="${escHtml(s.name)}">${escHtml(s.name)}</span>`;
      item.addEventListener('click', () => openInPanel(s.path, state.activePanelIdx));
      caseSlidesEl.appendChild(item);
    });
    casePanel.classList.remove('hidden');
  } catch (_) {
    casePanel.classList.add('hidden');
  }
}

// ── 缩略图 ───────────────────────────────────────────────────────────────────
function loadThumbnail(rel) {
  thumbImg.style.display = 'none';
  thumbEmpty.style.display = 'block';
  const url = `api/thumbnail?path=${encodeURIComponent(rel)}&size=240`;
  const img = new Image();
  img.onload = () => {
    thumbImg.src = url;
    thumbImg.style.display = 'block';
    thumbEmpty.style.display = 'none';
  };
  img.onerror = () => { thumbEmpty.textContent = '缩略图加载失败'; };
  img.src = url;
}

// ── 右键菜单 ─────────────────────────────────────────────────────────────────
function showCtxMenu(x, y) {
  ctxMenu.classList.remove('hidden');
  ctxMenu.style.left = `${Math.min(x, window.innerWidth - 180)}px`;
  ctxMenu.style.top  = `${Math.min(y, window.innerHeight - 160)}px`;
}
function hideCtxMenu() { ctxMenu.classList.add('hidden'); }

for (let i = 0; i < MAX_PANELS; i++) {
  $(`ctx-open-${i}`).addEventListener('click', () => {
    if (state.currentCtxPath) openInPanel(state.currentCtxPath, i);
    hideCtxMenu();
  });
}
document.addEventListener('click', hideCtxMenu);
document.addEventListener('keydown', e => { if (e.key === 'Escape') hideCtxMenu(); });

// ── OpenSeadragon 面板管理 ───────────────────────────────────────────────────
function initViewer(idx) {
  const p = state.panels[idx];
  if (p.viewer) { p.viewer.destroy(); p.viewer = null; }

  const container = $(`osd-${idx}`);
  container.innerHTML = ''; // 清空旧内容

  p.viewer = OpenSeadragon({
    element: container,
    prefixUrl: 'https://cdn.jsdelivr.net/npm/openseadragon@4.1/build/openseadragon/images/',
    showNavigationControl: true,
    navigationControlAnchor: OpenSeadragon.ControlAnchor.TOP_RIGHT,
    zoomInButton: null, zoomOutButton: null, homeButton: null, fullPageButton: null,
    showNavigator: false,
    minZoomLevel: 0.1,
    maxZoomLevel: 100,
    visibilityRatio: 0.5,
    animationTime: 0.3,
    gestureSettingsMouse: { clickToZoom: false, dblClickToZoom: true },
    gestureSettingsTouch: { clickToZoom: false, dblClickToZoom: true },
  });

  // 同步联动
  p.viewer.addHandler('viewport-change', () => {
    if (!state.syncEnabled || isSyncing) return;
    isSyncing = true;
    const vp = p.viewer.viewport;
    const center = vp.getCenter();
    const zoom   = vp.getZoom();
    state.panels.forEach((other, j) => {
      if (j !== idx && other.viewer && !$(`cell-${j}`).classList.contains('hidden')) {
        other.viewer.viewport.zoomTo(zoom, null, true);
        other.viewer.viewport.panTo(center, true);
      }
    });
    isSyncing = false;
  });

  // 激活面板
  container.addEventListener('click', () => { state.activePanelIdx = idx; });

  // 标注 canvas
  setupAnnCanvas(idx);
}

function openInPanel(rel, idx) {
  const p = state.panels[idx];

  // 如果需要，先初始化 viewer
  if (!p.viewer) initViewer(idx);

  p.path = rel;
  p.annotations = [];

  // 显示加载动画
  const osdEl = $(`osd-${idx}`);
  let spinner = osdEl.querySelector('.loading-spinner');
  if (!spinner) {
    spinner = document.createElement('div');
    spinner.className = 'loading-spinner';
    spinner.innerHTML = '<div class="spinner"></div>';
    osdEl.appendChild(spinner);
  }
  spinner.style.display = 'flex';

  // 隐藏 placeholder
  const cell = $(`cell-${idx}`);
  const placeholder = cell.querySelector('.cell-placeholder');
  if (placeholder) placeholder.style.display = 'none';

  // 更新标题
  const title = cell.querySelector('.cell-title');
  const filename = rel.split('/').pop();
  title.textContent = filename;
  title.classList.add('loaded');

  // 先 fetch DZI XML，再手动初始化 TileSource
  fetchAndOpenDzi(rel, idx);
}

async function fetchAndOpenDzi(rel, idx) {
  const p = state.panels[idx];
  const osdEl = $(`osd-${idx}`);

  try {
    const res = await fetch(`api/dzi?path=${encodeURIComponent(rel)}`);
    const xmlText = await res.text();
    const parser = new DOMParser();
    const xml = parser.parseFromString(xmlText, 'application/xml');
    const imgEl = xml.querySelector('Image');
    const sizeEl = xml.querySelector('Size');

    const tileSize = parseInt(imgEl.getAttribute('TileSize'));
    const overlap  = parseInt(imgEl.getAttribute('Overlap'));
    const format   = imgEl.getAttribute('Format');
    const width    = parseInt(sizeEl.getAttribute('Width'));
    const height   = parseInt(sizeEl.getAttribute('Height'));

    // 计算 DZI 层级数
    const maxLevel = Math.ceil(Math.log2(Math.max(width, height)));

    // 构造自定义 TileSource
    const tileSource = {
      width,
      height,
      tileSize,
      tileOverlap: overlap,
      minLevel: 0,
      maxLevel,
      getTileUrl(level, x, y) {
        return `api/tile/${level}/${x}/${y}?path=${encodeURIComponent(rel)}`;
      },
      // 告诉 OSD 如何分配层级
      getLevelScale(level) {
        return Math.pow(0.5, maxLevel - level);
      },
    };

    p.viewer.open(tileSource);

    p.viewer.addOnceHandler('open', () => {
      // 移除加载动画
      const spinner = osdEl.querySelector('.loading-spinner');
      if (spinner) spinner.style.display = 'none';
      // 加载已有标注
      loadAnnotations(idx);
    });
  } catch (e) {
    const spinner = osdEl.querySelector('.loading-spinner');
    if (spinner) spinner.style.display = 'none';
    console.error('DZI 加载失败:', e);
  }
}

function closePanelContent(idx) {
  const p = state.panels[idx];
  if (p.viewer) p.viewer.close();
  p.path = null;
  p.annotations = [];
  clearAnnCanvas(idx);

  const cell = $(`cell-${idx}`);
  cell.querySelector('.cell-title').textContent = '— 未加载 —';
  cell.querySelector('.cell-title').classList.remove('loaded');
  const placeholder = cell.querySelector('.cell-placeholder');
  if (placeholder) placeholder.style.display = '';
}

// 关闭按钮
for (let i = 0; i < MAX_PANELS; i++) {
  const cell = $(`cell-${i}`);
  cell.querySelector('.cell-close-btn').addEventListener('click', () => closePanelContent(i));
  cell.querySelector('.cell-info-btn').addEventListener('click', () => showSlideInfo(i));
}

function clearAllPanels() {
  for (let i = 0; i < MAX_PANELS; i++) closePanelContent(i);
}

// ── 切片信息弹窗 ─────────────────────────────────────────────────────────────
async function showSlideInfo(idx) {
  const p = state.panels[idx];
  if (!p.path) return;
  try {
    const res = await fetch(`api/slide_info?path=${encodeURIComponent(p.path)}`);
    const info = await res.json();
    infoBody.innerHTML = '';

    const rows = [
      ['文件路径', info.path],
      ['图像尺寸', `${info.dimensions[0]} × ${info.dimensions[1]} px`],
      ['层级数', info.level_count],
      ['DZ 层级数', info.dz_level_count],
      ['MPP (X)', info.properties['openslide.mpp-x'] || '—'],
      ['MPP (Y)', info.properties['openslide.mpp-y'] || '—'],
      ['目镜倍率', info.properties['openslide.objective-power'] || '—'],
      ['扫描时间', info.properties['hamamatsu.Created'] || '—'],
    ];
    rows.forEach(([k, v]) => {
      const row = document.createElement('div');
      row.className = 'info-row';
      row.innerHTML = `<span class="info-key">${escHtml(String(k))}</span><span class="info-val">${escHtml(String(v))}</span>`;
      infoBody.appendChild(row);
    });

    infoModal.classList.remove('hidden');
  } catch (e) {
    alert('获取信息失败：' + e.message);
  }
}

$('info-modal-close').addEventListener('click', () => infoModal.classList.add('hidden'));
infoModal.addEventListener('click', e => { if (e.target === infoModal) infoModal.classList.add('hidden'); });

// ── 标注功能 ─────────────────────────────────────────────────────────────────
function setupAnnCanvas(idx) {
  const osdEl = $(`osd-${idx}`);
  let canvas = osdEl.querySelector('.ann-canvas');
  if (!canvas) {
    canvas = document.createElement('canvas');
    canvas.className = 'ann-canvas';
    osdEl.appendChild(canvas);
  }
  const ctx = canvas.getContext('2d');
  const p = state.panels[idx];
  p.annCanvas = canvas;
  p.annCtx = ctx;

  // 跟随容器尺寸
  const ro = new ResizeObserver(() => resizeAnnCanvas(idx));
  ro.observe(osdEl);

  // 画框交互
  let drawing = false;
  let startX, startY;

  canvas.addEventListener('mousedown', e => {
    if (!state.annotating) return;
    drawing = true;
    const rect = canvas.getBoundingClientRect();
    startX = e.clientX - rect.left;
    startY = e.clientY - rect.top;
  });

  canvas.addEventListener('mousemove', e => {
    if (!drawing) return;
    const rect = canvas.getBoundingClientRect();
    const curX = e.clientX - rect.left;
    const curY = e.clientY - rect.top;
    renderAnnotations(idx);
    // 临时框
    ctx.save();
    ctx.strokeStyle = '#ff9900';
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 4]);
    ctx.strokeRect(startX, startY, curX - startX, curY - startY);
    ctx.restore();
  });

  canvas.addEventListener('mouseup', e => {
    if (!drawing) return;
    drawing = false;
    const rect = canvas.getBoundingClientRect();
    const endX = e.clientX - rect.left;
    const endY = e.clientY - rect.top;
    if (Math.abs(endX - startX) < 5 || Math.abs(endY - startY) < 5) return; // 太小忽略

    // 转为视口坐标存储
    const vp = state.panels[idx].viewer.viewport;
    const p0 = viewportFromCanvas(idx, Math.min(startX, endX), Math.min(startY, endY));
    const p1 = viewportFromCanvas(idx, Math.max(startX, endX), Math.max(startY, endY));
    const note = prompt('标注备注（可留空）', '') || '';
    state.panels[idx].annotations.push({ x: p0.x, y: p0.y, w: p1.x - p0.x, h: p1.y - p0.y, note });
    renderAnnotations(idx);
  });
}

function resizeAnnCanvas(idx) {
  const p = state.panels[idx];
  if (!p.annCanvas) return;
  const osdEl = $(`osd-${idx}`);
  p.annCanvas.width  = osdEl.clientWidth;
  p.annCanvas.height = osdEl.clientHeight;
  renderAnnotations(idx);
}

function viewportFromCanvas(idx, cx, cy) {
  const p = state.panels[idx];
  const osdEl = $(`osd-${idx}`);
  const vp = p.viewer.viewport;
  const pt = vp.windowToViewportCoordinates(new OpenSeadragon.Point(cx, cy));
  return pt;
}

function renderAnnotations(idx) {
  const p = state.panels[idx];
  if (!p.annCanvas || !p.viewer || !p.viewer.viewport) return;
  const ctx = p.annCtx;
  const vp = p.viewer.viewport;
  ctx.clearRect(0, 0, p.annCanvas.width, p.annCanvas.height);

  p.annotations.forEach((ann, i) => {
    // 将视口坐标转回窗口坐标
    const tl = vp.viewportToWindowCoordinates(new OpenSeadragon.Point(ann.x, ann.y));
    const br = vp.viewportToWindowCoordinates(new OpenSeadragon.Point(ann.x + ann.w, ann.y + ann.h));

    const osdRect = p.annCanvas.getBoundingClientRect();
    const x = tl.x - osdRect.left;
    const y = tl.y - osdRect.top;
    const w = br.x - tl.x;
    const h = br.y - tl.y;

    ctx.save();
    ctx.strokeStyle = '#ff9900';
    ctx.lineWidth = 2;
    ctx.setLineDash([]);
    ctx.strokeRect(x, y, w, h);
    ctx.fillStyle = 'rgba(255,153,0,0.08)';
    ctx.fillRect(x, y, w, h);

    // 序号标签
    ctx.fillStyle = '#ff9900';
    ctx.font = 'bold 12px sans-serif';
    ctx.fillText(`#${i + 1}${ann.note ? ' ' + ann.note : ''}`, x + 4, y + 14);
    ctx.restore();
  });
}

function clearAnnCanvas(idx) {
  const p = state.panels[idx];
  if (p.annCtx && p.annCanvas) p.annCtx.clearRect(0, 0, p.annCanvas.width, p.annCanvas.height);
  p.annotations = [];
}

// 视口变化时重绘标注
setInterval(() => {
  state.panels.forEach((p, i) => {
    if (p.viewer && p.annotations.length > 0) renderAnnotations(i);
  });
}, 100);

// 标注模式切换
btnAnnRect.addEventListener('click', () => {
  state.annotating = !state.annotating;
  btnAnnRect.classList.toggle('active', state.annotating);
  annStatus.textContent = state.annotating ? '✏ 拖拽画框中……' : '';
  // 切换 pointer-events
  state.panels.forEach((p, i) => {
    if (p.annCanvas) {
      p.annCanvas.classList.toggle('drawing', state.annotating);
      // OSD 鼠标交互开关
      if (p.viewer) {
        p.viewer.setMouseNavEnabled(!state.annotating);
      }
    }
  });
});

$('btn-ann-clear').addEventListener('click', () => {
  const idx = state.activePanelIdx;
  clearAnnCanvas(idx);
  annStatus.textContent = '已清除标注';
  setTimeout(() => { annStatus.textContent = ''; }, 2000);
});

$('btn-ann-save').addEventListener('click', () => saveAnnotations(state.activePanelIdx));
$('btn-ann-load').addEventListener('click', () => loadAnnotations(state.activePanelIdx));

async function saveAnnotations(idx) {
  const p = state.panels[idx];
  if (!p.path) { annStatus.textContent = '无切片，无法保存'; return; }
  try {
    await fetch(`api/annotations?path=${encodeURIComponent(p.path)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(p.annotations),
    });
    annStatus.textContent = `已保存 ${p.annotations.length} 条标注`;
    setTimeout(() => { annStatus.textContent = ''; }, 2000);
  } catch (e) {
    annStatus.textContent = '保存失败：' + e.message;
  }
}

async function loadAnnotations(idx) {
  const p = state.panels[idx];
  if (!p.path) return;
  try {
    const res = await fetch(`api/annotations?path=${encodeURIComponent(p.path)}`);
    const data = await res.json();
    p.annotations = Array.isArray(data) ? data : [];
    renderAnnotations(idx);
    if (p.annotations.length > 0) {
      annStatus.textContent = `已加载 ${p.annotations.length} 条标注`;
      setTimeout(() => { annStatus.textContent = ''; }, 2000);
    }
  } catch (_) {}
}

// ── 工具函数 ─────────────────────────────────────────────────────────────────
function escHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── 初始化 ───────────────────────────────────────────────────────────────────
(function init() {
  setLayout(1);
  // 初始化面板 0 的 OSD（先建好实例）
  initViewer(0);
  loadRootTree();
})();
