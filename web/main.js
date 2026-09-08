import './style.css';
import { createViewer } from './viewer.js';

const $ = id => document.getElementById(id);
const colors = { P: '#ef5959', T: '#459cff', A: '#41ca8b', B: '#f2d454', LS: '#f79b42', Drain: '#b08bea' };
const faces = { top: '顶面 +Z', bottom: '底面 −Z', front: '前面 −Y', back: '后面 +Y', left: '左面 −X', right: '右面 +X' };
const kindNames = { cavity: '插装孔', port: '外部油口', drilling: '内部钻孔' };
let state, draft, report, model, selection = 'block', dirty = false, busy = false, externalChange = false;
let viewer;
try { viewer = createViewer($('viewport'), select); } catch (e) { notice('WebGL 初始化失败：' + e.message, true); }

function element(tag, text, cls) { const e = document.createElement(tag); if (text != null) e.textContent = text; if (cls) e.className = cls; return e; }
function notice(message, error = false) { $('notice').textContent = message; $('notice').className = error ? 'error' : ''; }
async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail || response.status)); }
  return response.json();
}
function artifact(name) { return `/api/artifacts/${state.build.build_id}/${name}`; }
function markDirty() { dirty = true; renderHeader(); notice('草稿已修改。模型仍为上次构建；点击“重建与校验”保存并更新。'); }
function renderHeader() {
  $('project-name').textContent = draft.name;
  const b = draft.block; $('dimensions').textContent = `${b.length} × ${b.width} × ${b.height} mm`;
  $('revision').textContent = 'SHA ' + state.revision.slice(0, 8);
  const status = dirty ? 'DRAFT' : externalChange || state.stale ? 'STALE' : state.build?.status || 'UNBUILT';
  $('status').textContent = status; $('status').className = 'badge ' + (status === 'FAIL' ? 'fail' : status === 'PASS' ? '' : 'warning');
  const allowed = status === 'PASS' && !busy;
  $('step-download').classList.toggle('disabled', !allowed);
  if (allowed) $('step-download').href = artifact('production.step'); else $('step-download').removeAttribute('href');
  for (const [id, name] of [['data-download', 'design.json'], ['report-download', 'validation.md'], ['review-download', 'review.json']]) {
    $(id).classList.toggle('disabled', !state.build || dirty || state.stale || externalChange);
    if (state.build) $(id).href = artifact(name);
  }
  $('build').textContent = busy ? '正在计算实体…' : dirty ? '保存 · 重建与校验' : '重建与校验';
}
function renderTree() {
  $('feature-count').textContent = draft.features.length + ' ITEMS'; $('feature-tree').replaceChildren();
  for (const kind of ['cavity', 'port', 'drilling']) {
    const group = element('div', null, 'tree-group'); const list = draft.features.filter(f => f.kind === kind);
    group.append(element('div', `${kindNames[kind]} / ${list.length}`, 'tree-heading'));
    for (const f of list) {
      const button = element('button', null, 'tree-feature'); button.dataset.feature = f.id;
      const swatch = element('span', null, 'swatch'); swatch.style.background = colors[f.circuit] || '#b4c7da';
      button.append(swatch, element('span', f.id), element('small', f.plugged ? 'PLUG' : f.kind === 'cavity' ? Object.values(f.circuits).join(' / ') : faces[f.face].split(' ')[0]));
      button.onclick = () => select(f.id); group.append(button);
    }
    $('feature-tree').append(group);
  }
}
function field(parent, label, value, onChange, options = null, numeric = false) {
  const wrap = element('label', label, 'field'); const input = document.createElement(options ? 'select' : 'input');
  input.setAttribute('aria-label', label);
  if (options) for (const [key, text] of Object.entries(options)) { const option = element('option', text); option.value = key; input.append(option); }
  else { input.type = numeric ? 'number' : 'text'; if (numeric) { input.step = '.1'; input.min = '0'; input.max = '2000'; } }
  input.value = value;
  input.onchange = () => {
    const next = numeric ? input.valueAsNumber : input.value;
    if (numeric && (!Number.isFinite(next) || next < 0 || next > 2000)) { input.setCustomValidity('请输入 0–2000 的有效数值'); input.reportValidity(); return; }
    input.setCustomValidity(''); onChange(next); markDirty();
  };
  wrap.append(input); parent.append(wrap); return input;
}
function select(id) {
  if (!draft) return;
  selection = draft.features.some(f => f.id === id) ? id : 'block';
  viewer?.select(selection); $('selection-label').textContent = selection === 'block' ? '' : selection;
  for (const btn of document.querySelectorAll('[data-feature]')) btn.classList.toggle('active', btn.dataset.feature === selection);
  $('select-block').classList.toggle('active', selection === 'block');
  const form = $('inspector'); form.replaceChildren(); form.onsubmit = e => e.preventDefault();
  if (selection === 'block') {
    $('selection-kind').textContent = 'STOCK'; form.append(element('div', 'MANIFOLD', 'inspector-title'));
    field(form, '项目名称', draft.name, v => { draft.name = v; });
    for (const [key, label] of [['length', '长度 X'], ['width', '宽度 Y'], ['height', '高度 Z']]) field(form, label + ' / mm', draft.block[key], v => { draft.block[key] = v; }, null, true);
    field(form, '材料', draft.block.material, v => { draft.block.material = v; });
    field(form, '最小壁厚 / mm', draft.rules.minimum_wall, v => { draft.rules.minimum_wall = v; }, null, true);
    form.append(element('div', '原点：左 / 前 / 底角。X=长度，Y=宽度，Z=高度。所有钻孔从所选面沿法线向内加工。', 'inspector-note'));
  } else {
    const f = draft.features.find(f => f.id === selection);
    $('selection-kind').textContent = f.kind.toUpperCase(); form.append(element('div', f.id, 'inspector-title'));
    field(form, '安装 / 钻入面', f.face, v => { f.face = v; select(f.id); }, faces);
    const axes = f.face === 'top' || f.face === 'bottom' ? ['X', 'Y'] : f.face === 'front' || f.face === 'back' ? ['X', 'Z'] : ['Y', 'Z'];
    const row = element('div', null, 'field-row'); form.append(row);
    field(row, `位置 U (${axes[0]})`, f.u, v => { f.u = v; }, null, true); field(row, `位置 V (${axes[1]})`, f.v, v => { f.v = v; }, null, true);
    if (f.kind === 'cavity') {
      field(form, '孔腔定义', f.definition, v => { f.definition = v; const d = draft.library.find(x => x.id === v); f.circuits = Object.fromEntries(d.zones.map(z => [z.id, f.circuits[z.id] || 'P'])); select(f.id); }, Object.fromEntries(draft.library.map(d => [d.id, d.label])));
      for (const key of Object.keys(f.circuits)) field(form, `接口 ${key} / 油路`, f.circuits[key], v => { f.circuits[key] = v; renderTree(); }, Object.fromEntries(Object.keys(colors).map(c => [c, c])));
      const def = draft.library.find(d => d.id === f.definition);
      form.append(element('div', def.stages.map(s => `Ø${s.diameter} · 深度 ${s.start}–${s.end}`).join('\n'), 'property-note'));
      form.append(element('div', def.source + '\n' + def.thread_note, 'inspector-note'));
    } else {
      field(form, '油路', f.circuit, v => { f.circuit = v; renderTree(); }, Object.fromEntries(Object.keys(colors).map(c => [c, c])));
      const dims = element('div', null, 'field-row'); form.append(dims);
      field(dims, '直径 / mm', f.diameter, v => { f.diameter = v; }, null, true); field(dims, '圆柱深度 / mm', f.depth, v => { f.depth = v; }, null, true);
      field(form, '钻尖夹角 / ° (180 = 平底)', f.tip_angle, v => { f.tip_angle = v; }, null, true);
      if (f.kind === 'port') { field(form, '油口类型（几何为直孔）', f.port_type, v => { f.port_type = v; }); field(form, '规格注记', f.size, v => { f.size = v; }); }
      if (f.kind === 'drilling') {
        field(form, '入口封闭', f.plugged ? 'plug' : 'port', v => { f.plugged = v === 'plug'; select(f.id); }, { port: '由同轴外部油口封闭', plug: '安装堵头' });
        if (f.plugged) field(form, '堵头啮合长度 / mm', f.plug_length, v => { f.plug_length = v; }, null, true);
      }
      field(form, '预期直接连接（逗号分隔）', f.connects_to.join(', '), v => { f.connects_to = v.split(',').map(s => s.trim()).filter(Boolean); });
      if (f.plugged || f.kind === 'port') {
        const access = element('div', null, 'field-row'); form.append(access);
        field(access, '工具空间直径', f.clearance_diameter, v => { f.clearance_diameter = v; }, null, true);
        field(access, '工具空间高度', f.clearance_height, v => { f.clearance_height = v; }, null, true);
      }
    }
    const pose = model?.placements[f.id];
    if (pose) form.append(element('div', `已构建原点 [${pose.origin.join(', ')}]\n钻入方向 [${pose.direction.join(', ')}]`, 'property-note inspector-divider'));
    const links = Object.entries(report?.graph || {}).filter(([n]) => n === f.id || n.startsWith(f.id + ':'));
    for (const [n, targets] of links) form.append(element('div', `${n} → ${targets.join(', ') || '未连接'}`, 'property-note'));
  }
  $('feature-results').replaceChildren();
  for (const c of (report?.checks || []).filter(c => c.status !== 'PASS' && c.items.some(i => i.split(':')[0] === selection))) $('feature-results').append(element('div', `${c.status} · ${c.rule}: ${c.actual} / ${c.required} ${c.unit}`, 'feature-check'));
  if ($('report-filter').value === 'selected') renderReport();
}
function renderReport() {
  if (!report) return;
  $('check-counts').textContent = `${report.counts.PASS} PASS / ${report.counts.WARNING} WARNING / ${report.counts.FAIL} FAIL`;
  $('build-time').textContent = new Date(report.generated_at).toLocaleTimeString();
  $('limitations').replaceChildren(...report.limitations.map(s => element('li', s)));
  const filter = $('report-filter').value;
  const checks = report.checks.filter(c => filter === 'all' || (filter === 'issues' ? c.status !== 'PASS' : c.items.some(i => i.split(':')[0] === selection)));
  const container = $('validation-results'); container.replaceChildren();
  if (!checks.length) {
    const message = element('div', null, 'pass-message'); const text = element('div', '✓ 当前构建未发现规则违规');
    text.append(element('small', '几何与连接检查通过。演示孔腔、材料及加工参数仍需工程审核。')); message.append(text); container.append(message); return;
  }
  const table = element('table', null, 'check-table'); const head = element('thead'), hr = element('tr');
  for (const title of ['状态', '检查规则', '相关项', '实际值', '要求值']) hr.append(element('th', title)); head.append(hr); table.append(head);
  const body = element('tbody');
  for (const c of checks) {
    const row = element('tr'); row.title = c.message; row.tabIndex = 0;
    row.append(element('td', c.status, c.status), element('td', c.rule), element('td', c.items.join(' ↔ ')), element('td', `${c.actual} ${c.unit}`), element('td', String(c.required)));
    row.onclick = () => select(c.items[0].split(':')[0]); row.onkeydown = e => { if (e.key === 'Enter') row.click(); }; body.append(row);
  }
  table.append(body); container.append(table);
}
async function load() {
  const next = await api('/api/state');
  let nextReport, nextModel;
  if (next.build) [nextReport, nextModel] = await Promise.all(['validation.json', 'review.json'].map(n => api(`/api/artifacts/${next.build.build_id}/${n}`)));
  state = next; draft = structuredClone(state.design); report = nextReport; model = nextModel; dirty = false; externalChange = false;
  if (model) { viewer?.load(model, state.design.features); $('model-info').textContent = `OCCT BREP · ${(model.volume_mm3 / 1000).toFixed(1)} cm³ · ${model.parts.length} review parts`; }
  renderTree(); renderHeader(); select(selection); renderReport();
  notice(state.stale ? '磁盘设计比模型更新。请点击“重建与校验”。' : '模型与设计数据一致。选择孔腔或钻孔查看尺寸、实际连接和校验结果。');
}
$('select-block').onclick = () => select('block');
$('reload').onclick = async () => { if (dirty && !confirm('重新读取会丢弃未保存的网页草稿，继续？')) return; try { await load(); } catch (e) { notice(e.message, true); } };
$('build').onclick = async () => {
  if (busy || !state) return;
  if (!$('inspector').reportValidity()) return;
  busy = true; document.body.classList.add('busy');
  // Freeze every editor during the snapshot build so late edits cannot be silently discarded.
  for (const e of document.querySelectorAll('button, #inspector input, #inspector select')) e.disabled = true;
  renderHeader(); notice('正在执行实体切削、连接校验和 STEP 往返检查…');
  try {
    await api('/api/build', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-PMC-Request': 'local-console' }, body: JSON.stringify({ expected_revision: state.revision, design: dirty ? draft : null }) });
    await load();
  } catch (e) { notice(e.message, true); }
  finally { busy = false; document.body.classList.remove('busy'); for (const e of document.querySelectorAll('button, #inspector input, #inspector select')) e.disabled = false; renderHeader(); }
};
$('fit').onclick = () => viewer?.fit(); $('iso-view').onclick = () => viewer?.fit('iso'); $('top-view').onclick = () => viewer?.fit('top');
for (const mode of ['review', 'solid']) $(mode + '-mode').onclick = () => { viewer?.mode(mode); $('review-mode').classList.toggle('active', mode === 'review'); $('solid-mode').classList.toggle('active', mode === 'solid'); };
$('opacity').oninput = e => { viewer?.opacity(Number(e.target.value) / 100); $('opacity-value').textContent = e.target.value + '%'; };
for (const key of ['cavities', 'drillings', 'labels']) $('show-' + key).onchange = e => viewer?.toggle(key, e.target.checked);
for (const [circuit, color] of Object.entries(colors)) {
  const btn = element('button', null, 'circuit-toggle'); btn.setAttribute('aria-label', `显示油路 ${circuit}`); btn.setAttribute('aria-pressed', 'true');
  const dot = element('span', null, 'swatch'); dot.style.background = color; btn.append(dot, element('span', circuit));
  btn.onclick = () => { const show = btn.classList.contains('off'); btn.classList.toggle('off', !show); btn.setAttribute('aria-pressed', String(show)); viewer?.circuit(circuit, show); }; $('circuits').append(btn);
}
$('report-filter').onchange = renderReport;
$('json-open').onclick = () => { $('json-editor').value = JSON.stringify(draft, null, 2); $('json-error').textContent = ''; $('json-dialog').showModal(); };
$('json-close').onclick = () => $('json-dialog').close();
$('json-apply').onclick = async () => {
  $('json-apply').disabled = true;
  try { const raw = JSON.parse($('json-editor').value);
    const data = await api('/api/check-design', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-PMC-Request': 'local-console' }, body: JSON.stringify(raw) });
    draft = data; $('json-dialog').close(); renderTree(); select('block'); markDirty();
  } catch (e) { $('json-error').textContent = e.message; }
  finally { $('json-apply').disabled = false; }
};
window.addEventListener('beforeunload', e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });
setInterval(async () => {
  if (!state || busy || document.hidden) return;
  try {
    const next = await api('/api/state');
    if (next.revision !== state.revision || next.build?.build_id !== state.build?.build_id) {
      if (!dirty) await load();
      else { externalChange = true; renderHeader(); notice('磁盘设计或构建已更新；网页草稿已保留。重新读取后再编辑，避免覆盖。', true); }
    }
  } catch (e) { externalChange = true; renderHeader(); notice('本地服务或项目文件不可用：' + e.message, true); }
}, 5000);
load().catch(e => notice('无法加载：' + e.message, true));
