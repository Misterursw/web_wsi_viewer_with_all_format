const $ = id => document.getElementById(id);

const state = {
  slides: [],
  filteredSlides: [],
  activeSlide: null,
  activeGene: null,
  spotData: null,
  viewer: null,
};

const slideList = $('slide-list');
const slideFilter = $('slide-filter');
const geneSelect = $('gene-select');
const reducerSelect = $('reducer-select');
const opacityInput = $('opacity');
const overlay = $('spot-overlay');
const ctx = overlay.getContext('2d');
const statusEl = $('status');
const titleEl = $('viewer-title');
const infoEl = $('spot-info');
const thumbImg = $('thumb-img');
const thumbEmpty = $('thumb-empty');

function escHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function color(t, a) {
  t = Math.max(0, Math.min(1, t));
  const stops = [
    [0.00, 29, 42, 109],
    [0.30, 14, 116, 144],
    [0.55, 34, 160, 107],
    [0.78, 240, 180, 41],
    [1.00, 194, 65, 12],
  ];
  let s0 = stops[0], s1 = stops[stops.length - 1];
  for (let i = 1; i < stops.length; i++) {
    if (t <= stops[i][0]) { s0 = stops[i - 1]; s1 = stops[i]; break; }
  }
  const f = (t - s0[0]) / Math.max(1e-6, s1[0] - s0[0]);
  const r = Math.round(s0[1] + f * (s1[1] - s0[1]));
  const g = Math.round(s0[2] + f * (s1[2] - s0[2]));
  const b = Math.round(s0[3] + f * (s1[3] - s0[3]));
  return `rgba(${r},${g},${b},${a})`;
}

function initViewer() {
  state.viewer = OpenSeadragon({
    element: $('osd'),
    prefixUrl: 'https://cdn.jsdelivr.net/npm/openseadragon@4.1/build/openseadragon/images/',
    showNavigationControl: true,
    navigationControlAnchor: OpenSeadragon.ControlAnchor.TOP_RIGHT,
    showNavigator: true,
    navigatorPosition: 'BOTTOM_RIGHT',
    minZoomLevel: 0.05,
    maxZoomLevel: 100,
    visibilityRatio: 0.3,
    animationTime: 0.25,
    gestureSettingsMouse: { clickToZoom: false, dblClickToZoom: true },
    gestureSettingsTouch: { clickToZoom: false, dblClickToZoom: true },
  });

  ['open', 'animation', 'resize', 'pan', 'zoom'].forEach(evt => {
    state.viewer.addHandler(evt, renderSpots);
  });
}

function resizeOverlay() {
  const rect = overlay.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const w = Math.max(1, Math.round(rect.width * dpr));
  const h = Math.max(1, Math.round(rect.height * dpr));
  if (overlay.width !== w || overlay.height !== h) {
    overlay.width = w;
    overlay.height = h;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function renderSpots() {
  resizeOverlay();
  const rect = overlay.getBoundingClientRect();
  ctx.clearRect(0, 0, rect.width, rect.height);
  if (!state.viewer || !state.viewer.viewport || !state.spotData || !state.spotData.points) return;
  const alpha = Number(opacityInput.value);
  const osdRect = $('osd').getBoundingClientRect();
  const overlayRect = overlay.getBoundingClientRect();
  const dx = osdRect.left - overlayRect.left;
  const dy = osdRect.top - overlayRect.top;

  for (const p of state.spotData.points) {
    const tlVp = state.viewer.viewport.imageToViewportCoordinates(p.x, p.y);
    const brVp = state.viewer.viewport.imageToViewportCoordinates(p.x + p.w, p.y + p.h);
    const tl = state.viewer.viewport.viewportToViewerElementCoordinates(tlVp);
    const br = state.viewer.viewport.viewportToViewerElementCoordinates(brVp);
    const x = tl.x + dx;
    const y = tl.y + dy;
    const w = br.x - tl.x;
    const h = br.y - tl.y;
    if (x > rect.width || y > rect.height || x + w < 0 || y + h < 0) continue;
    ctx.fillStyle = color(p.norm, alpha);
    ctx.fillRect(x, y, Math.max(1, w), Math.max(1, h));
  }
}

function renderSlideList() {
  slideList.innerHTML = '';
  if (!Array.isArray(state.filteredSlides)) {
    slideList.innerHTML = '<div class="error">/api/slides did not return an array</div>';
    return;
  }
  if (!state.filteredSlides.length) {
    slideList.innerHTML = '<div class="loading">没有可显示的 slide</div>';
    return;
  }
  for (const s of state.filteredSlides) {
    const row = document.createElement('div');
    row.className = `slide-row${s.name === state.activeSlide ? ' active' : ''}${s.source_exists ? '' : ' missing'}`;
    row.innerHTML = `<span class="name" title="${escHtml(s.name)}">${escHtml(s.name)}</span><span class="count">${s.n_tiles || 0}</span>`;
    row.onclick = () => openSlide(s.name);
    slideList.appendChild(row);
  }
}

function filterSlides() {
  const q = slideFilter.value.trim().toLowerCase();
  state.filteredSlides = q ? state.slides.filter(s => s.name.toLowerCase().includes(q)) : state.slides.slice();
  renderSlideList();
}

async function loadSlides() {
  statusEl.textContent = 'loading slides';
  const res = await fetch('api/slides');
  const data = await res.json();
  if (!Array.isArray(data)) throw new Error(`/api/slides returned ${JSON.stringify(data).slice(0, 120)}`);
  state.slides = data.filter(s => s.source_exists && Array.isArray(s.genes) && s.genes.length);
  state.filteredSlides = state.slides.slice();
  renderSlideList();
  statusEl.textContent = `${state.slides.length} slides`;
  if (state.slides.length) await openSlide(state.slides[0].name);
}

function updateGeneSelect(slide) {
  const item = state.slides.find(s => s.name === slide);
  geneSelect.innerHTML = '';
  for (const g of (item?.genes || [])) {
    const opt = document.createElement('option');
    opt.value = g;
    opt.textContent = g;
    geneSelect.appendChild(opt);
  }
  state.activeGene = geneSelect.value || null;
}

async function fetchAndOpenDzi(slide) {
  const res = await fetch(`api/dzi?slide=${encodeURIComponent(slide)}`);
  if (!res.ok) throw new Error(`DZI HTTP ${res.status}`);
  const xmlText = await res.text();
  const xml = new DOMParser().parseFromString(xmlText, 'application/xml');
  const imgEl = xml.querySelector('Image');
  const sizeEl = xml.querySelector('Size');
  const tileSize = parseInt(imgEl.getAttribute('TileSize'), 10);
  const overlap = parseInt(imgEl.getAttribute('Overlap'), 10);
  const width = parseInt(sizeEl.getAttribute('Width'), 10);
  const height = parseInt(sizeEl.getAttribute('Height'), 10);
  const maxLevel = Math.ceil(Math.log2(Math.max(width, height)));
  const tileSource = {
    width,
    height,
    tileSize,
    tileOverlap: overlap,
    minLevel: 0,
    maxLevel,
    getTileUrl(level, x, y) {
      return `api/tile/${level}/${x}/${y}?slide=${encodeURIComponent(slide)}`;
    },
    getLevelScale(level) {
      return Math.pow(0.5, maxLevel - level);
    },
  };
  state.viewer.open(tileSource);
}

async function loadSpotData() {
  if (!state.activeSlide || !state.activeGene) return;
  statusEl.textContent = 'loading spots';
  const url = `api/spot_data?slide=${encodeURIComponent(state.activeSlide)}&gene=${encodeURIComponent(state.activeGene)}&reducer=${encodeURIComponent(reducerSelect.value)}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`spot data HTTP ${res.status}: ${await res.text()}`);
  state.spotData = await res.json();
  $('legend-lo').textContent = state.spotData.scale.lo.toPrecision(4);
  $('legend-hi').textContent = state.spotData.scale.hi.toPrecision(4);
  infoEl.innerHTML = `
    <div><b>Slide:</b> ${escHtml(state.spotData.slide)}</div>
    <div><b>Gene:</b> ${escHtml(state.spotData.gene)}</div>
    <div><b>Spots:</b> ${state.spotData.n_tiles}</div>
    <div><b>MPP:</b> ${state.spotData.slide_mpp ?? 'NA'} → ${state.spotData.target_mpp ?? 'NA'}</div>

  `;
  statusEl.textContent = `${state.spotData.n_tiles} spots`;
  renderSpots();
}

function loadThumbnail(slide) {
  thumbImg.style.display = 'none';
  thumbEmpty.style.display = 'block';
  const url = `api/thumbnail?slide=${encodeURIComponent(slide)}&size=260`;
  const img = new Image();
  img.onload = () => {
    thumbImg.src = url;
    thumbImg.style.display = 'block';
    thumbEmpty.style.display = 'none';
  };
  img.onerror = () => { thumbEmpty.textContent = '缩略图加载失败'; };
  img.src = url;
}

async function openSlide(slide) {
  try {
    state.activeSlide = slide;
    state.spotData = null;
    updateGeneSelect(slide);
    titleEl.textContent = slide;
    renderSlideList();
    loadThumbnail(slide);
    statusEl.textContent = 'opening WSI';
    await fetchAndOpenDzi(slide);
    await loadSpotData();
  } catch (e) {
    console.error(e);
    statusEl.textContent = e.message;
  }
}

geneSelect.onchange = () => {
  state.activeGene = geneSelect.value;
  loadSpotData().catch(e => { statusEl.textContent = e.message; });
};
reducerSelect.onchange = () => loadSpotData().catch(e => { statusEl.textContent = e.message; });
opacityInput.oninput = renderSpots;
slideFilter.oninput = filterSlides;
$('btn-home').onclick = () => state.viewer && state.viewer.viewport.goHome();
window.addEventListener('resize', renderSpots);

initViewer();
loadSlides().catch(e => {
  console.error(e);
  statusEl.textContent = e.message;
  slideList.innerHTML = `<div class="error">${escHtml(e.message)}</div>`;
});
