'use strict';
/* MagicSlides — editor. O formato do projeto é o mesmo do backend (core.py). */

const $ = (id) => document.getElementById(id);
const TOKEN = document.querySelector('meta[name="ms-token"]').content;
const CANVAS_H = 56.25;
const FONTS = ['Segoe UI', 'Segoe UI Semibold', 'Calibri', 'Arial', 'Verdana', 'Tahoma', 'Trebuchet MS', 'Georgia', 'Times New Roman', 'Garamond', 'Consolas'];
const AUTOSAVE_KEY = 'magicslides.autosave.v1';

let data = null;
let slideIndex = 0;
let selectedId = null;
let editingId = null;
let themes = [];
let settings = {};
let undoStack = [];
let redoStack = [];
let imageTarget = null; // null = inserir; id = substituir
let genTheme = 'aurora';
let currentJob = null;

const uid = (p) => `${p}_${(crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(16).slice(2) + Date.now().toString(16)).replaceAll('-', '').slice(0, 10)}`;
const clone = (v) => JSON.parse(JSON.stringify(v));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const escapeHtml = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* ------------------------------------------------------------ API ---- */
async function api(path, body, { raw = false } = {}) {
  const opts = { headers: { 'X-MagicSlides-Token': TOKEN } };
  if (body !== undefined) {
    opts.method = 'POST';
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ errors: [`Erro ${res.status}`] }));
    throw new Error((err.errors || ['Falha desconhecida']).join('\n'));
  }
  return raw ? res.blob() : res.json();
}

/* ------------------------------------------------------ utilidades ---- */
function toast(msg, kind = '', ms = 4200) {
  const t = document.createElement('div');
  t.className = `toast ${kind}`;
  t.textContent = msg;
  $('toasts').appendChild(t);
  setTimeout(() => t.remove(), ms);
}
function setStatus(t) {
  $('status').textContent = t;
  clearTimeout(setStatus._t);
  setStatus._t = setTimeout(() => ($('status').textContent = 'Pronto'), 2200);
}
function safeName(s) {
  return (s || 'MagicSlides').replace(/[^\p{L}\p{N}_ -]+/gu, '-').trim().replace(/\s+/g, '-').slice(0, 80) || 'MagicSlides';
}
async function saveBlob(blob, name) {
  const desktop = window.pywebview && window.pywebview.api && window.pywebview.api.save_file;
  if (desktop) {
    const b64 = await new Promise((ok) => {
      const r = new FileReader();
      r.onload = () => ok(String(r.result).split(',')[1]);
      r.readAsDataURL(blob);
    });
    const res = await window.pywebview.api.save_file(name, b64);
    if (res && res.ok) toast(`Salvo em ${res.path}`);
    return !!(res && res.ok);
  }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
  return true;
}
function readFile(file, as = 'dataURL') {
  return new Promise((ok, fail) => {
    const r = new FileReader();
    r.onload = () => ok(r.result);
    r.onerror = fail;
    as === 'text' ? r.readAsText(file) : r.readAsDataURL(file);
  });
}

/* ---------------------------------------------------- tema / cores ---- */
function roleColor(theme, role, fallback) {
  const map = {
    title: theme.foreground, body: theme.foreground, muted: theme.muted, accent: theme.accent,
    'on-accent': theme.accentText, 'accent-fill': theme.accent, 'surface-fill': theme.surface,
    'on-image': '#FFFFFF', overlay: '#000000',
  };
  return map[role] || fallback;
}
function applyTheme(next) {
  const old = data.theme;
  next = { ...old, ...next };
  data.slides.forEach((s) => {
    if (s.bgRole === 'accent') s.background = next.accent;
    else if (s.background && s.background.toLowerCase() === (old.background || '').toLowerCase()) s.background = null;
    s.elements.forEach((el) => {
      if (el.type === 'text') {
        if (el.role) el.color = roleColor(next, el.role, el.color);
        if (el.font && el.font === old.headingFont) el.font = next.headingFont;
        else if (el.font && el.font === old.font) el.font = next.font;
      } else if (el.type === 'shape' && el.role) {
        el.fill = roleColor(next, el.role, el.fill);
      }
    });
  });
  data.theme = next;
}

/* ----------------------------------------------------- histórico ---- */
function commit() {
  undoStack.push(JSON.stringify(data));
  if (undoStack.length > 80) undoStack.shift();
  redoStack = [];
  updateUndoButtons();
}
function undo() {
  if (!undoStack.length) return;
  redoStack.push(JSON.stringify(data));
  data = JSON.parse(undoStack.pop());
  slideIndex = clamp(slideIndex, 0, data.slides.length - 1);
  selectedId = null;
  render();
  setStatus('Desfeito');
}
function redo() {
  if (!redoStack.length) return;
  undoStack.push(JSON.stringify(data));
  data = JSON.parse(redoStack.pop());
  slideIndex = clamp(slideIndex, 0, data.slides.length - 1);
  selectedId = null;
  render();
  setStatus('Refeito');
}
function updateUndoButtons() {
  $('undoBtn').disabled = !undoStack.length;
  $('redoBtn').disabled = !redoStack.length;
}

/* ------------------------------------------------------- modelo ---- */
function defaultSlide(name = 'Novo slide') {
  const t = data ? data.theme : { foreground: '#17181C', muted: '#5B5F6B', font: 'Segoe UI', headingFont: 'Segoe UI Semibold' };
  return {
    id: uid('slide'), name, layout: 'blank', background: null, notes: '', elements: [
      { id: uid('text'), type: 'text', role: 'title', x: 6, y: 5, w: 88, h: 11, text: name, fontSize: 36, bold: true, italic: false, color: t.foreground, align: 'left', valign: 'top', font: t.headingFont, bullets: false },
      { id: uid('text'), type: 'text', role: 'body', x: 6, y: 20, w: 88, h: 30, text: 'Primeiro tópico\nSegundo tópico\nTerceiro tópico', fontSize: 24, bold: false, italic: false, color: t.foreground, align: 'left', valign: 'top', font: t.font, bullets: true },
    ],
  };
}
const currentSlide = () => data.slides[slideIndex];
const selected = () => (currentSlide() ? currentSlide().elements.find((e) => e.id === selectedId) || null : null);

/* ---------------------------------------------------- renderização ---- */
function renderElement(el, theme) {
  const node = document.createElement('div');
  node.className = 'el';
  node.dataset.id = el.id;
  node.style.left = `${el.x}%`;
  node.style.top = `${(el.y / CANVAS_H) * 100}%`;
  node.style.width = `${el.w}%`;
  node.style.height = `${(el.h / CANVAS_H) * 100}%`;
  if (el.type === 'text') {
    node.classList.add('txt');
    if (el.bullets) node.classList.add('bul');
    node.style.setProperty('--fs', el.fontSize || 20);
    node.style.fontWeight = el.bold ? '700' : '400';
    node.style.fontStyle = el.italic ? 'italic' : 'normal';
    node.style.color = el.color || theme.foreground;
    node.style.textAlign = el.align || 'left';
    node.style.justifyContent = { middle: 'center', bottom: 'flex-end' }[el.valign] || 'flex-start';
    node.style.fontFamily = `'${el.font || theme.font || 'Segoe UI'}', system-ui, sans-serif`;
    setTextLines(node, el.text);
  } else if (el.type === 'shape') {
    node.style.background = el.fill || theme.accent;
    node.style.opacity = el.opacity ?? 1;
    node.style.borderRadius = el.shape === 'ellipse' ? '50%' : `${el.radius || 0}cqw`;
    if (el.stroke) node.style.border = `2px solid ${el.stroke}`;
  } else if (el.type === 'image') {
    node.classList.add('img');
    if (el.src) {
      const img = document.createElement('img');
      img.src = el.src;
      img.alt = el.alt || '';
      img.draggable = false;
      node.appendChild(img);
    } else {
      node.classList.add('missing');
      node.textContent = 'sem imagem';
    }
  }
  return node;
}
function setTextLines(node, text) {
  node.replaceChildren();
  String(text ?? '').split('\n').forEach((line) => {
    const d = document.createElement('div');
    d.textContent = line;
    if (!line) d.appendChild(document.createElement('br'));
    node.appendChild(d);
  });
}
function renderSlideInto(target, slide, { withHandles = false } = {}) {
  target.replaceChildren();
  target.style.background = slide.background || data.theme.background;
  slide.elements.forEach((el) => {
    const node = renderElement(el, data.theme);
    if (withHandles) {
      if (el.id === selectedId) {
        node.classList.add('selected');
        const h = document.createElement('div');
        h.className = 'handle';
        h.addEventListener('pointerdown', (e) => startResize(e, el));
        node.appendChild(h);
      }
      node.addEventListener('pointerdown', (e) => startDrag(e, el));
      node.addEventListener('dblclick', (e) => startEditing(e, el, node));
    }
    target.appendChild(node);
  });
}

function render() {
  $('projectTitle').value = data.meta.title || '';
  document.title = `${data.meta.title || 'Apresentação'} — MagicSlides`;
  renderSlides();
  renderStage();
  renderInspector();
  renderSlidePanel();
  renderThemePanel();
  updateUndoButtons();
  scheduleAutosave();
}
function renderStage() {
  if (editingId) return;
  renderSlideInto($('stage'), currentSlide(), { withHandles: true });
}
function renderSlides() {
  const list = $('slideList');
  list.replaceChildren();
  $('slideCount').textContent = `${data.slides.length}`;
  data.slides.forEach((s, i) => {
    const item = document.createElement('div');
    item.className = `slide-thumb${i === slideIndex ? ' active' : ''}`;
    item.draggable = true;
    const num = document.createElement('div');
    num.className = 'thumb-num';
    num.textContent = i + 1;
    const thumb = document.createElement('div');
    thumb.className = 'thumb slide-surface';
    renderSlideInto(thumb, s);
    item.append(num, thumb);
    item.onclick = () => { finishEditing(); slideIndex = i; selectedId = null; render(); };
    item.ondragstart = (e) => e.dataTransfer.setData('application/x-slide', String(i));
    item.ondragover = (e) => { if (e.dataTransfer.types.includes('application/x-slide')) { e.preventDefault(); item.classList.add('drop-target'); } };
    item.ondragleave = () => item.classList.remove('drop-target');
    item.ondrop = (e) => {
      e.preventDefault();
      item.classList.remove('drop-target');
      const from = Number(e.dataTransfer.getData('application/x-slide'));
      if (Number.isNaN(from) || from === i) return;
      commit();
      const [m] = data.slides.splice(from, 1);
      data.slides.splice(i, 0, m);
      slideIndex = i;
      render();
      setStatus('Slides reordenados');
    };
    list.appendChild(item);
  });
  const active = list.querySelector('.active');
  if (active) active.scrollIntoView({ block: 'nearest' });
}
function refreshCurrentThumb() {
  const thumbs = $('slideList').querySelectorAll('.thumb');
  if (thumbs[slideIndex]) renderSlideInto(thumbs[slideIndex], currentSlide());
  scheduleAutosave();
}

/* ------------------------------------------------ arrastar/redimensionar ---- */
let drag = null;
function startDrag(e, el) {
  if (editingId === el.id || e.button !== 0) return;
  e.stopPropagation();
  if (editingId) finishEditing();
  if (selectedId !== el.id) {
    selectedId = el.id;
    renderStage();
    renderInspector();
  }
  const r = $('stage').getBoundingClientRect();
  drag = { mode: 'move', id: el.id, sx: e.clientX, sy: e.clientY, ox: el.x, oy: el.y, sw: r.width, sh: r.height, moved: false };
  window.addEventListener('pointermove', onDragMove);
  window.addEventListener('pointerup', endDrag, { once: true });
}
function startResize(e, el) {
  e.stopPropagation();
  e.preventDefault();
  const r = $('stage').getBoundingClientRect();
  drag = { mode: 'resize', id: el.id, sx: e.clientX, sy: e.clientY, ow: el.w, oh: el.h, sw: r.width, sh: r.height, moved: false };
  window.addEventListener('pointermove', onDragMove);
  window.addEventListener('pointerup', endDrag, { once: true });
}
function onDragMove(e) {
  if (!drag) return;
  const el = currentSlide().elements.find((x) => x.id === drag.id);
  if (!el) return;
  const dx = ((e.clientX - drag.sx) / drag.sw) * 100;
  const dy = ((e.clientY - drag.sy) / drag.sh) * CANVAS_H;
  if (!drag.moved) {
    if (Math.abs(e.clientX - drag.sx) + Math.abs(e.clientY - drag.sy) < 3) return;
    commit();
    drag.moved = true;
  }
  if (drag.mode === 'move') {
    el.x = Math.round(clamp(drag.ox + dx, -el.w + 2, 98) * 10) / 10;
    el.y = Math.round(clamp(drag.oy + dy, -el.h + 2, CANVAS_H - 2) * 10) / 10;
  } else {
    el.w = Math.round(clamp(drag.ow + dx, 1, 200) * 10) / 10;
    el.h = Math.round(clamp(drag.oh + dy, 1, 120) * 10) / 10;
  }
  const node = $('stage').querySelector(`[data-id="${el.id}"]`);
  if (node) {
    node.style.left = `${el.x}%`;
    node.style.top = `${(el.y / CANVAS_H) * 100}%`;
    node.style.width = `${el.w}%`;
    node.style.height = `${(el.h / CANVAS_H) * 100}%`;
  }
  syncPositionFields(el);
}
function endDrag() {
  window.removeEventListener('pointermove', onDragMove);
  if (drag && drag.moved) {
    refreshCurrentThumb();
    setStatus(drag.mode === 'move' ? 'Elemento movido' : 'Elemento redimensionado');
  }
  drag = null;
}

/* ----------------------------------------------- edição no slide ---- */
function startEditing(e, el, node) {
  if (el.type !== 'text') {
    if (el.type === 'image' || el.placeholderQuery !== undefined) openImageDialog(el.id);
    return;
  }
  e.stopPropagation();
  commit();
  editingId = el.id;
  node.classList.add('editing');
  node.querySelector('.handle')?.remove();
  node.contentEditable = 'true';
  node.focus();
  const range = document.createRange();
  range.selectNodeContents(node);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  node.addEventListener('blur', finishEditing, { once: true });
  node.addEventListener('input', () => {
    el.text = readEditedText(node);
    $('propText').value = el.text;
  });
  node.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape') { ev.preventDefault(); node.blur(); }
    ev.stopPropagation();
  });
  node.addEventListener('paste', (ev) => {
    ev.preventDefault();
    document.execCommand('insertText', false, ev.clipboardData.getData('text/plain'));
  });
}
function readEditedText(node) {
  // Linhas são <div>s; <br> também quebra linha. Funciona com o que o
  // navegador cria ao apertar Enter, colar ou apagar tudo.
  let out = '';
  const walk = (n) => {
    n.childNodes.forEach((c) => {
      if (c.nodeType === Node.TEXT_NODE) out += c.textContent;
      else if (c.nodeName === 'BR') out += '\n';
      else if (c.nodeType === Node.ELEMENT_NODE && !c.classList.contains('handle')) {
        if (out && !out.endsWith('\n')) out += '\n';
        walk(c);
      }
    });
  };
  walk(node);
  return out.replace(/\n$/, '');
}
function finishEditing() {
  if (!editingId) return;
  const node = $('stage').querySelector(`[data-id="${editingId}"]`);
  const el = currentSlide().elements.find((x) => x.id === editingId);
  if (node && el) el.text = readEditedText(node);
  editingId = null;
  renderStage();
  renderInspector();
  refreshCurrentThumb();
}

/* ------------------------------------------------------- inspetor ---- */
function syncPositionFields(el) {
  if (el.id !== selectedId) return;
  $('propX').value = el.x; $('propY').value = el.y; $('propW').value = el.w; $('propH').value = el.h;
}
function renderInspector() {
  const el = selected();
  $('noSelection').hidden = !!el;
  $('inspectorForm').hidden = !el;
  if (!el) return;
  $('textProps').hidden = el.type !== 'text';
  $('shapeProps').hidden = el.type !== 'shape';
  $('imageProps').hidden = el.type !== 'image';
  syncPositionFields(el);
  if (el.type === 'text') {
    if (document.activeElement !== $('propText')) $('propText').value = el.text;
    $('propFontSize').value = el.fontSize;
    $('propColor').value = el.color || data.theme.foreground;
    $('propFont').value = FONTS.includes(el.font) ? el.font : (data.theme.font || 'Segoe UI');
    $('propBold').checked = !!el.bold;
    $('propItalic').checked = !!el.italic;
    $('propBullets').checked = !!el.bullets;
    $('propAlign').value = el.align || 'left';
    $('propValign').value = el.valign || 'top';
  } else if (el.type === 'shape') {
    $('propFill').value = el.fill || data.theme.accent;
    $('propShape').value = el.shape || 'rect';
    $('propOpacity').value = el.opacity ?? 1;
    $('propRadius').value = el.radius || 0;
    $('propStroke').value = el.stroke || '#333333';
    $('propStrokeOn').checked = !!el.stroke;
    $('shapeToImageBtn').hidden = el.placeholderQuery === undefined;
  } else if (el.type === 'image') {
    $('propImagePreview').src = el.src || '';
    $('propAlt').value = el.alt || '';
    const c = $('propCredit');
    c.textContent = el.credit ? `Crédito: ${el.credit}` : '';
  }
}
function bindInspector() {
  const onFocusCommit = (id) => $(id).addEventListener('focus', commit);
  const numeric = { propX: 'x', propY: 'y', propW: 'w', propH: 'h', propFontSize: 'fontSize', propRadius: 'radius' };
  Object.entries(numeric).forEach(([id, key]) => {
    onFocusCommit(id);
    $(id).addEventListener('input', () => {
      const el = selected();
      const v = Number($(id).value);
      if (!el || Number.isNaN(v)) return;
      el[key] = v;
      renderStage(); refreshCurrentThumb();
    });
  });
  const simple = {
    propText: ['text', 'value'], propColor: ['color', 'value'], propFont: ['font', 'value'], propAlign: ['align', 'value'],
    propValign: ['valign', 'value'], propBold: ['bold', 'checked'], propItalic: ['italic', 'checked'], propBullets: ['bullets', 'checked'],
    propFill: ['fill', 'value'], propShape: ['shape', 'value'], propAlt: ['alt', 'value'],
  };
  Object.entries(simple).forEach(([id, [key, prop]]) => {
    onFocusCommit(id);
    const evt = prop === 'checked' || $(id).tagName === 'SELECT' ? 'change' : 'input';
    $(id).addEventListener(evt, () => {
      const el = selected();
      if (!el) return;
      el[key] = $(id)[prop];
      if (key === 'color' || key === 'fill') delete el.role; // cor manual: não recolorir com o tema
      renderStage(); refreshCurrentThumb();
      if (key === 'text') renderSlides();
    });
  });
  onFocusCommit('propOpacity');
  $('propOpacity').addEventListener('input', () => { const el = selected(); if (el) { el.opacity = Number($('propOpacity').value); renderStage(); refreshCurrentThumb(); } });
  onFocusCommit('propStroke');
  $('propStroke').addEventListener('input', () => { const el = selected(); if (el) { el.stroke = $('propStroke').value; $('propStrokeOn').checked = true; renderStage(); refreshCurrentThumb(); } });
  $('propStrokeOn').addEventListener('change', () => { const el = selected(); if (el) { commit(); el.stroke = $('propStrokeOn').checked ? $('propStroke').value : null; renderStage(); refreshCurrentThumb(); } });
  $('deleteElementBtn').onclick = deleteElement;
  $('dupElementBtn').onclick = duplicateElement;
  $('frontBtn').onclick = () => reorderElement(1);
  $('backBtn').onclick = () => reorderElement(-1);
  $('shapeToImageBtn').onclick = () => openImageDialog(selectedId);
  $('replaceWebImageBtn').onclick = () => openImageDialog(selectedId);
  $('replaceLocalImageBtn').onclick = () => { imageTarget = selectedId; $('imageInput').click(); };
}

/* ------------------------------------------------ painel do slide ---- */
function renderSlidePanel() {
  const s = currentSlide();
  $('slideBg').value = s.background || data.theme.background;
  if (document.activeElement !== $('slideNotes')) $('slideNotes').value = s.notes || '';
  $('slideLayoutInfo').textContent = s.layout && s.layout !== 'blank' ? `Layout: ${s.layout}` : '';
}
function bindSlidePanel() {
  $('slideBg').addEventListener('focus', commit);
  $('slideBg').addEventListener('input', () => { currentSlide().background = $('slideBg').value; currentSlide().bgRole = null; renderStage(); refreshCurrentThumb(); });
  $('slideBgReset').onclick = () => { commit(); currentSlide().background = null; currentSlide().bgRole = null; render(); };
  $('slideNotes').addEventListener('focus', commit);
  $('slideNotes').addEventListener('input', () => { currentSlide().notes = $('slideNotes').value; scheduleAutosave(); });
}

/* ----------------------------------------------------- painel tema ---- */
function themeCard(t, active, onPick) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = `theme-card${active ? ' active' : ''}`;
  b.innerHTML = `<div class="tc-prev" style="background:${t.background}"><div class="tc-title" style="color:${t.foreground};font-family:'${escapeHtml(t.headingFont)}',system-ui,sans-serif">Aa Título</div><div class="tc-bar" style="background:${t.accent}"></div><div class="tc-line" style="background:${t.muted}"></div></div><span class="tc-name">${escapeHtml(t.name)}</span>`;
  b.onclick = onPick;
  return b;
}
function renderThemePanel() {
  const grid = $('themeGrid');
  grid.replaceChildren();
  themes.forEach((t) => grid.appendChild(themeCard(t, data.theme.id === t.id, () => {
    commit();
    applyTheme(clone(t));
    render();
    setStatus(`Tema ${t.name} aplicado`);
  })));
  const th = data.theme;
  $('themeBg').value = th.background; $('themeFg').value = th.foreground; $('themeMuted').value = th.muted || th.foreground;
  $('themeAccent').value = th.accent; $('themeSurface').value = th.surface || th.background;
  $('themeFont').value = th.font || 'Segoe UI'; $('themeHeadingFont').value = th.headingFont || th.font || 'Segoe UI';
}
function bindThemePanel() {
  const map = { themeBg: 'background', themeFg: 'foreground', themeMuted: 'muted', themeAccent: 'accent', themeSurface: 'surface', themeFont: 'font', themeHeadingFont: 'headingFont' };
  Object.entries(map).forEach(([id, key]) => {
    $(id).addEventListener('focus', commit);
    $(id).addEventListener($(id).tagName === 'SELECT' ? 'change' : 'input', () => {
      const next = { ...data.theme, [key]: $(id).value, id: 'custom', name: 'Personalizado' };
      if (key === 'accent') next.accentText = contrastText($(id).value);
      applyTheme(next);
      renderStage(); renderSlides(); renderInspector();
      scheduleAutosave();
    });
  });
}
function contrastText(hex) {
  const n = parseInt(hex.slice(1), 16);
  const l = (0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
  return l > 0.6 ? '#111111' : '#FFFFFF';
}

/* ---------------------------------------------------- operações ---- */
function addText() {
  commit();
  const t = data.theme;
  const el = { id: uid('text'), type: 'text', role: 'body', x: 20, y: 20, w: 50, h: 10, text: 'Novo texto', fontSize: 24, bold: false, italic: false, color: t.foreground, align: 'left', valign: 'top', font: t.font, bullets: false };
  currentSlide().elements.push(el);
  selectedId = el.id;
  render();
}
function addShape() {
  commit();
  const el = { id: uid('shape'), type: 'shape', role: 'accent-fill', shape: 'rect', x: 30, y: 18, w: 30, h: 16, fill: data.theme.accent, stroke: null, opacity: 1, radius: 1.5 };
  currentSlide().elements.push(el);
  selectedId = el.id;
  render();
}
function insertImage(src, meta = {}) {
  commit();
  const target = imageTarget && currentSlide().elements.find((e) => e.id === imageTarget);
  if (target && target.type === 'image') {
    Object.assign(target, { src, alt: meta.alt || target.alt, credit: meta.credit || '', page: meta.page || '', source: meta.source || '' });
    selectedId = target.id;
  } else if (target && target.type === 'shape' && target.placeholderQuery !== undefined) {
    const el = { id: uid('image'), type: 'image', x: target.x, y: target.y, w: target.w, h: target.h, src, alt: meta.alt || '', credit: meta.credit || '', fit: 'cover' };
    const els = currentSlide().elements;
    els.splice(els.indexOf(target), 1, el);
    selectedId = el.id;
  } else {
    let w = 40, h = 40 * 0.66;
    if (meta.width && meta.height) h = clamp((w * meta.height) / meta.width, 8, 50);
    const el = { id: uid('image'), type: 'image', x: 30, y: 12, w, h, src, alt: meta.alt || '', credit: meta.credit || '', page: meta.page || '', source: meta.source || '', fit: 'cover' };
    currentSlide().elements.push(el);
    selectedId = el.id;
  }
  imageTarget = null;
  render();
  setStatus('Imagem inserida');
}
async function insertLocalFile(file) {
  if (!file || !file.type.startsWith('image/')) return toast('Escolha um arquivo de imagem.', 'warn');
  try {
    setStatus('Processando imagem…');
    const res = await api('/api/images/encode', { dataUrl: await readFile(file) });
    insertImage(res.src, { alt: file.name.replace(/\.[^.]+$/, ''), width: res.width, height: res.height });
  } catch (e) { toast(e.message, 'error'); }
}
function deleteElement() {
  if (!selectedId) return;
  commit();
  currentSlide().elements = currentSlide().elements.filter((e) => e.id !== selectedId);
  selectedId = null;
  render();
}
function duplicateElement() {
  const el = selected();
  if (!el) return;
  commit();
  const c = { ...clone(el), id: uid(el.type), x: el.x + 2, y: el.y + 2 };
  currentSlide().elements.push(c);
  selectedId = c.id;
  render();
}
function reorderElement(dir) {
  const els = currentSlide().elements;
  const i = els.findIndex((e) => e.id === selectedId);
  if (i < 0) return;
  commit();
  const [m] = els.splice(i, 1);
  els.splice(dir > 0 ? els.length : 0, 0, m);
  render();
}
function addSlide() {
  commit();
  data.slides.splice(slideIndex + 1, 0, defaultSlide(`Slide ${data.slides.length + 1}`));
  slideIndex++;
  selectedId = null;
  render();
}
function duplicateSlide() {
  commit();
  const c = clone(currentSlide());
  c.id = uid('slide');
  c.elements.forEach((e) => (e.id = uid(e.type)));
  data.slides.splice(slideIndex + 1, 0, c);
  slideIndex++;
  selectedId = null;
  render();
}
function deleteSlide() {
  if (data.slides.length === 1) return toast('A apresentação precisa ter ao menos um slide.', 'warn');
  commit();
  data.slides.splice(slideIndex, 1);
  slideIndex = Math.max(0, slideIndex - 1);
  selectedId = null;
  render();
}

/* ---------------------------------------------- abrir/salvar/exportar ---- */
async function newPresentation() {
  if (!confirm('Criar uma nova apresentação em branco? (Você pode desfazer com Ctrl+Z)')) return;
  commit();
  data = await api('/api/default');
  slideIndex = 0; selectedId = null;
  render();
}
async function openProject(file) {
  try {
    const obj = JSON.parse(await readFile(file, 'text'));
    const res = await api('/api/validate', obj);
    commit();
    data = res.presentation;
    slideIndex = 0; selectedId = null;
    render();
    toast(`Projeto aberto (${res.slides} slides)`);
  } catch (e) {
    toast(`Não foi possível abrir: ${e.message}`, 'error', 7000);
  }
}
async function exportAs(kind) {
  finishEditing();
  $('exportMenu').hidden = true;
  const name = safeName(data.meta.title);
  try {
    if (kind === 'json') {
      await saveBlob(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }), `${name}.magicslides.json`);
      return setStatus('Projeto salvo');
    }
    setStatus(kind === 'pptx' ? 'Gerando PowerPoint…' : 'Gerando HTML…');
    const blob = await api(`/api/export/${kind}`, data, { raw: true });
    await saveBlob(blob, `${name}.${kind}`);
    setStatus(kind === 'pptx' ? 'PowerPoint exportado' : 'HTML exportado');
  } catch (e) {
    toast(e.message, 'error', 7000);
  }
}

let autosaveTimer = null;
function scheduleAutosave() {
  clearTimeout(autosaveTimer);
  autosaveTimer = setTimeout(() => {
    try { localStorage.setItem(AUTOSAVE_KEY, JSON.stringify(data)); } catch (e) { /* armazenamento cheio ou indisponível */ }
  }, 800);
}
function loadAutosave() {
  try {
    const raw = localStorage.getItem(AUTOSAVE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) { return null; }
}

/* --------------------------------------------------- gerar com IA ---- */
function providerText() {
  if (settings.provider === 'anthropic') {
    return settings.has_anthropic_api_key
      ? { cls: '', html: `Usando <b>Claude</b> (${escapeHtml(settings.anthropic_model)}). <a data-open-settings>Alterar</a>` }
      : { cls: 'warn', html: 'Claude selecionado, mas falta a chave de API. <a data-open-settings>Configurar</a>' };
  }
  if (settings.provider === 'openai') {
    return { cls: '', html: `Usando <b>${escapeHtml(settings.openai_model)}</b> em ${escapeHtml(settings.openai_base_url)}. <a data-open-settings>Alterar</a>` };
  }
  return { cls: 'warn', html: '<b>Modo offline (sem IA):</b> cole um texto ou tópicos e ele vira slides; um tema curto gera um rascunho para você completar. Para a IA escrever o conteúdo, <a data-open-settings>configure Claude ou Ollama</a>.' };
}
function openGenerateDialog() {
  const p = providerText();
  const line = $('genProvider');
  line.className = `provider-line ${p.cls}`;
  line.innerHTML = p.html;
  line.querySelectorAll('[data-open-settings]').forEach((a) => (a.onclick = () => { $('generateDialog').close(); openSettings(true); }));
  $('genLanguage').value = settings.language || 'Português do Brasil';
  const grid = $('genThemeGrid');
  grid.replaceChildren();
  themes.forEach((t) => grid.appendChild(themeCard(t, genTheme === t.id, () => { genTheme = t.id; openGenerateDialog(); })));
  if (!$('generateDialog').open) $('generateDialog').showModal();
  $('genPrompt').focus();
}
async function submitGenerate() {
  const prompt = $('genPrompt').value.trim();
  if (!prompt) { toast('Descreva o tema ou cole um texto.', 'warn'); return; }
  const req = {
    prompt, slides: Number($('genSlides').value) || 8, language: $('genLanguage').value, tone: $('genTone').value,
    theme: genTheme, images: $('genImages').checked, credits: $('genCredits').checked,
  };
  $('generateDialog').close();
  showProgress('Iniciando…', 0.03);
  try {
    const { job } = await api('/api/generate', req);
    currentJob = job;
    pollJob(job);
  } catch (e) {
    hideProgress();
    toast(e.message, 'error', 8000);
  }
}
async function pollJob(job) {
  if (currentJob !== job) return;
  let st;
  try { st = await api(`/api/jobs/${job}`); } catch (e) { hideProgress(); return toast(e.message, 'error'); }
  if (currentJob !== job) return;
  if (st.state === 'running') {
    showProgress(st.message, st.progress);
    return setTimeout(() => pollJob(job), 700);
  }
  hideProgress();
  currentJob = null;
  if (st.state === 'error') return toast(st.message, 'error', 10000);
  commit();
  data = st.result;
  slideIndex = 0; selectedId = null;
  render();
  toast(`Apresentação criada com ${data.slides.length} slides — ${st.provider}`);
  (st.warnings || []).slice(0, 3).forEach((w) => toast(w, 'warn', 8000));
}
function showProgress(msg, p) {
  $('progressOverlay').hidden = false;
  $('progressMessage').textContent = msg;
  $('progressBar').style.width = `${Math.round(clamp(p || 0.03, 0.03, 1) * 100)}%`;
}
function hideProgress() { $('progressOverlay').hidden = true; }

/* -------------------------------------------------- busca de imagens ---- */
function openImageDialog(targetId = null) {
  imageTarget = targetId;
  const el = targetId && currentSlide().elements.find((e) => e.id === targetId);
  $('imageDialogTitle').textContent = el ? 'Trocar imagem' : 'Imagem da internet';
  const src = $('imgSource');
  src.replaceChildren(new Option('Automático', 'auto'));
  Object.entries(settings.image_source_labels || {}).forEach(([k, v]) => src.add(new Option(v, k)));
  const q = (el && (el.query || el.placeholderQuery || el.alt)) || '';
  if (q) $('imgQuery').value = q;
  if (!$('imageDialog').open) $('imageDialog').showModal();
  $('imgQuery').focus();
  if ($('imgQuery').value) searchImages();
  else $('imgResults').innerHTML = '<div class="empty">Digite um termo e clique em Buscar.</div>';
}
async function searchImages() {
  const query = $('imgQuery').value.trim();
  if (!query) return;
  const box = $('imgResults');
  box.innerHTML = '<div class="empty">Buscando…</div>';
  try {
    const res = await api('/api/images/search', { query, source: $('imgSource').value });
    box.replaceChildren();
    if (!res.results.length) box.innerHTML = `<div class="empty">Nenhuma imagem encontrada.${res.warnings.length ? '<br>' + res.warnings.map(escapeHtml).join('<br>') : ''}</div>`;
    res.results.forEach((item) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'img-result';
      b.title = `${item.title || ''}\n${item.author ? 'por ' + item.author : ''} ${item.license || ''}`;
      const img = document.createElement('img');
      img.loading = 'lazy';
      img.referrerPolicy = 'no-referrer';
      img.src = item.thumb;
      img.onerror = () => b.remove();
      const cap = document.createElement('span');
      cap.textContent = `${item.source} · ${item.author || item.license || ''}`;
      b.append(img, cap);
      b.onclick = () => pickImage(item, b);
      box.appendChild(b);
    });
    if (res.results.length) res.warnings.forEach((w) => toast(w, 'warn'));
  } catch (e) {
    box.innerHTML = `<div class="empty">${escapeHtml(e.message)}</div>`;
  }
}
async function pickImage(item, btn) {
  btn.disabled = true;
  btn.style.opacity = 0.5;
  try {
    const res = await api('/api/images/fetch', { item });
    $('imageDialog').close();
    insertImage(res.src, { alt: item.title, credit: res.credit, page: item.page, source: item.source, width: res.width, height: res.height });
  } catch (e) {
    toast(e.message, 'error');
    btn.disabled = false;
    btn.style.opacity = 1;
  }
}

/* ------------------------------------------------------ configurações ---- */
function openSettings(focusProvider = false) {
  const s = settings;
  document.querySelectorAll('input[name=provider]').forEach((r) => (r.checked = r.value === s.provider));
  const mask = (has, env) => (has ? (env ? '•••• (variável de ambiente)' : '•••• salva — digite para trocar') : '');
  $('setAnthropicKey').value = ''; $('setAnthropicKey').placeholder = mask(s.has_anthropic_api_key, s.anthropic_api_key_from_env) || 'sk-ant-…';
  $('setAnthropicModel').value = s.anthropic_model || 'claude-opus-5';
  $('setAnthropicEffort').value = s.anthropic_effort || 'medium';
  $('setOpenaiUrl').value = s.openai_base_url || '';
  $('setOpenaiModel').value = s.openai_model || '';
  $('setOpenaiKey').value = ''; $('setOpenaiKey').placeholder = mask(s.has_openai_api_key, s.openai_api_key_from_env);
  document.querySelectorAll('input[name=imgsrc]').forEach((c) => (c.checked = (s.image_sources || []).includes(c.value)));
  $('setPexels').value = ''; $('setPexels').placeholder = mask(s.has_pexels_api_key, s.pexels_api_key_from_env) || 'pexels.com/api';
  $('setUnsplash').value = ''; $('setUnsplash').placeholder = mask(s.has_unsplash_access_key, s.unsplash_access_key_from_env) || 'unsplash.com/developers';
  $('setPixabay').value = ''; $('setPixabay').placeholder = mask(s.has_pixabay_api_key, s.pixabay_api_key_from_env) || 'pixabay.com/api/docs';
  $('setLanguage').value = s.language || 'Português do Brasil';
  $('setAuthor').value = s.author || '';
  $('configPath').textContent = `Arquivo de configuração: ${s.config_path || ''}`;
  toggleProviderFields();
  $('settingsDialog').showModal();
  if (focusProvider) document.querySelector('input[name=provider]:checked')?.focus();
}
function toggleProviderFields() {
  const p = document.querySelector('input[name=provider]:checked')?.value;
  document.querySelectorAll('fieldset[data-provider]').forEach((f) => (f.hidden = f.dataset.provider !== p));
}
async function saveSettings() {
  const body = {
    provider: document.querySelector('input[name=provider]:checked')?.value || 'offline',
    anthropic_api_key: $('setAnthropicKey').value, anthropic_model: $('setAnthropicModel').value.trim() || 'claude-opus-5',
    anthropic_effort: $('setAnthropicEffort').value,
    openai_base_url: $('setOpenaiUrl').value.trim(), openai_model: $('setOpenaiModel').value.trim(), openai_api_key: $('setOpenaiKey').value,
    image_sources: [...document.querySelectorAll('input[name=imgsrc]:checked')].map((c) => c.value),
    pexels_api_key: $('setPexels').value, unsplash_access_key: $('setUnsplash').value, pixabay_api_key: $('setPixabay').value,
    language: $('setLanguage').value, author: $('setAuthor').value.trim(),
  };
  try {
    settings = await api('/api/settings', body);
    toast('Configurações salvas');
  } catch (e) { toast(e.message, 'error'); }
}

/* --------------------------------------------------------- apresentar ---- */
let presentIndex = 0;
function startPresenting() {
  finishEditing();
  presentIndex = slideIndex;
  $('presenter').hidden = false;
  showPresentSlide();
  document.documentElement.requestFullscreen?.().catch(() => {});
}
function showPresentSlide() {
  renderSlideInto($('presenterSlide'), data.slides[presentIndex]);
  $('presenterCount').textContent = `${presentIndex + 1} / ${data.slides.length}`;
}
function stopPresenting() {
  $('presenter').hidden = true;
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  slideIndex = presentIndex;
  render();
}
function presenterKey(e) {
  if (['ArrowRight', 'PageDown', ' ', 'Enter'].includes(e.key)) presentIndex = Math.min(data.slides.length - 1, presentIndex + 1);
  else if (['ArrowLeft', 'PageUp', 'Backspace'].includes(e.key)) presentIndex = Math.max(0, presentIndex - 1);
  else if (e.key === 'Home') presentIndex = 0;
  else if (e.key === 'End') presentIndex = data.slides.length - 1;
  else if (e.key === 'Escape') return stopPresenting();
  else return;
  e.preventDefault();
  showPresentSlide();
}

/* ------------------------------------------------------------ teclado ---- */
function isTyping(e) {
  const t = e.target;
  return t && (t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName));
}
function onKey(e) {
  if (!$('presenter').hidden) return presenterKey(e);
  if (document.querySelector('dialog[open]')) return;
  const mod = e.ctrlKey || e.metaKey;
  if (mod && e.key.toLowerCase() === 's') { e.preventDefault(); return exportAs('json'); }
  if (mod && e.key.toLowerCase() === 'o') { e.preventDefault(); return $('fileInput').click(); }
  if (mod && e.key.toLowerCase() === 'g') { e.preventDefault(); return openGenerateDialog(); }
  if (e.key === 'F5') { e.preventDefault(); return startPresenting(); }
  if (isTyping(e)) return;
  if (mod && e.key.toLowerCase() === 'z' && !e.shiftKey) { e.preventDefault(); return undo(); }
  if (mod && (e.key.toLowerCase() === 'y' || (e.key.toLowerCase() === 'z' && e.shiftKey))) { e.preventDefault(); return redo(); }
  if (mod && e.key.toLowerCase() === 'd') { e.preventDefault(); return selected() ? duplicateElement() : duplicateSlide(); }
  const el = selected();
  if (el && (e.key === 'Delete' || e.key === 'Backspace')) { e.preventDefault(); return deleteElement(); }
  if (el && e.key.startsWith('Arrow')) {
    e.preventDefault();
    if (!e.repeat) commit();
    const step = e.shiftKey ? 2 : 0.5;
    if (e.key === 'ArrowLeft') el.x -= step;
    if (e.key === 'ArrowRight') el.x += step;
    if (e.key === 'ArrowUp') el.y -= step;
    if (e.key === 'ArrowDown') el.y += step;
    renderStage(); syncPositionFields(el); refreshCurrentThumb();
    return;
  }
  if (!el && (e.key === 'ArrowDown' || e.key === 'PageDown') && slideIndex < data.slides.length - 1) { slideIndex++; render(); }
  if (!el && (e.key === 'ArrowUp' || e.key === 'PageUp') && slideIndex > 0) { slideIndex--; render(); }
  if (e.key === 'Escape' && el) { selectedId = null; render(); }
}

/* ------------------------------------------------------------- início ---- */
function bindUi() {
  ['propFont', 'themeFont', 'themeHeadingFont'].forEach((id) => FONTS.forEach((f) => $(id).add(new Option(f, f))));
  $('generateBtn').onclick = openGenerateDialog;
  $('generateForm').addEventListener('submit', (e) => {
    if (e.submitter && e.submitter.value === 'cancel') return;
    e.preventDefault();
    submitGenerate();
  });
  $('newBtn').onclick = newPresentation;
  $('openBtn').onclick = () => $('fileInput').click();
  $('fileInput').onchange = (e) => { if (e.target.files[0]) openProject(e.target.files[0]); e.target.value = ''; };
  $('saveBtn').onclick = () => exportAs('json');
  $('presentBtn').onclick = startPresenting;
  $('exportBtn').onclick = (e) => { e.stopPropagation(); $('exportMenu').hidden = !$('exportMenu').hidden; };
  document.querySelectorAll('[data-export]').forEach((b) => (b.onclick = () => exportAs(b.dataset.export)));
  document.addEventListener('click', () => ($('exportMenu').hidden = true));
  $('settingsBtn').onclick = () => openSettings();
  $('settingsForm').addEventListener('submit', (e) => { if (e.submitter && e.submitter.value === 'cancel') return; saveSettings(); });
  document.querySelectorAll('input[name=provider]').forEach((r) => (r.onchange = toggleProviderFields));
  document.querySelectorAll('#openaiPresets button').forEach((b) => (b.onclick = () => { $('setOpenaiUrl').value = b.dataset.url; if (b.dataset.model) $('setOpenaiModel').value = b.dataset.model; }));
  $('addSlideBtn').onclick = addSlide;
  $('duplicateBtn').onclick = duplicateSlide;
  $('deleteSlideBtn').onclick = deleteSlide;
  $('addTextBtn').onclick = addText;
  $('addShapeBtn').onclick = addShape;
  $('addWebImageBtn').onclick = () => openImageDialog(null);
  $('addImageBtn').onclick = () => { imageTarget = null; $('imageInput').click(); };
  $('imageInput').onchange = (e) => { if (e.target.files[0]) insertLocalFile(e.target.files[0]); e.target.value = ''; };
  $('imgFromPcBtn').onclick = () => { $('imageDialog').close(); $('imageInput').click(); };
  $('imageSearchForm').addEventListener('submit', (e) => { if (e.submitter && e.submitter.value === 'cancel') { imageTarget = null; return; } e.preventDefault(); searchImages(); });
  $('undoBtn').onclick = undo;
  $('redoBtn').onclick = redo;
  $('projectTitle').addEventListener('focus', commit);
  $('projectTitle').oninput = () => { data.meta.title = $('projectTitle').value; scheduleAutosave(); };
  $('progressCancel').onclick = () => { currentJob = null; hideProgress(); toast('Geração cancelada.'); };
  $('presenter').onclick = () => { presentIndex = Math.min(data.slides.length - 1, presentIndex + 1); showPresentSlide(); };
  document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement && !$('presenter').hidden) stopPresenting(); });
  document.querySelectorAll('.tab').forEach((t) => (t.onclick = () => {
    document.querySelectorAll('.tab').forEach((x) => x.classList.toggle('active', x === t));
    document.querySelectorAll('.tab-panel').forEach((p) => (p.hidden = p.dataset.panel !== t.dataset.tab));
  }));
  $('stageWrap').addEventListener('pointerdown', (e) => {
    if (e.target.closest('.el')) return;
    if (editingId) finishEditing();
    if (selectedId) { selectedId = null; renderStage(); renderInspector(); }
  });
  const stage = $('stageWrap');
  stage.addEventListener('dragover', (e) => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); $('stage').classList.add('drag-over'); } });
  stage.addEventListener('dragleave', () => $('stage').classList.remove('drag-over'));
  stage.addEventListener('drop', (e) => {
    $('stage').classList.remove('drag-over');
    const f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (!f) return;
    e.preventDefault();
    imageTarget = null;
    insertLocalFile(f);
  });
  window.addEventListener('keydown', onKey);
  bindInspector();
  bindSlidePanel();
  bindThemePanel();
}

async function init() {
  bindUi();
  try {
    const [th, st, health] = await Promise.all([api('/api/themes'), api('/api/settings'), api('/api/health')]);
    themes = th.themes;
    settings = st;
    $('versionLabel').textContent = `versão ${health.version}`;
  } catch (e) {
    toast(`Falha ao iniciar: ${e.message}`, 'error', 10000);
  }
  const saved = loadAutosave();
  if (saved && saved.slides && saved.slides.length) {
    try {
      data = (await api('/api/validate', saved)).presentation;
    } catch (e) { data = null; }
  }
  const firstRun = !data;
  if (!data) data = await api('/api/default');
  genTheme = (data.theme && themes.some((t) => t.id === data.theme.id) && data.theme.id) || 'aurora';
  render();
  if (firstRun) openGenerateDialog();
}

init();
