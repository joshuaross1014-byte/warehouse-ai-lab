/* WMS Dev Workbench front end. Plain DOM, no framework, no build step.
   One function per tab (viewOps, viewTrace, ...). Everything talks to /api/* with ?profile=. */
'use strict';

const state = {
  profile: localStorage.getItem('wb.profile') || 'PROD',
  view: location.hash.slice(1) || 'ops',
  profiles: [],
};
const $ = (sel, el = document) => el.querySelector(sel);
const el = (tag, attrs = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') n.className = v;
    else if (k === 'html') n.innerHTML = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) n.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k !== null && k !== undefined) n.append(k.nodeType ? k : document.createTextNode(String(k)));
  return n;
};
const status = (msg) => { $('#status').textContent = msg; };

async function api(path, { body, method, params } = {}) {
  const url = new URL(path, location.origin);
  url.searchParams.set('profile', state.profile);
  for (const [k, v] of Object.entries(params || {})) if (v !== undefined && v !== '') url.searchParams.set(k, v);
  const opts = body ? { method: method || 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : { method: method || 'GET' };
  const t0 = performance.now();
  const r = await fetch(url, opts);
  const j = await r.json().catch(() => ({ error: r.statusText }));
  status(`${method || 'GET'} ${url.pathname} ${r.status} ${Math.round(performance.now() - t0)} ms`);
  if (!r.ok || j.error) throw new Error(j.error || r.statusText);
  return j;
}

/* ---------- generic result table ---------- */
function fmtCell(v) {
  if (v === null || v === undefined) return el('td', { class: 'null' }, 'null');
  if (typeof v === 'number') return el('td', { class: 'num' }, Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 4 }));
  const s = String(v);
  return el('td', { title: s.length > 60 ? s : null }, s);
}
function toCSV(res) {
  const esc = (v) => v === null || v === undefined ? '' : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v);
  return [res.columns.map(esc).join(','), ...res.rows.map(r => r.map(esc).join(','))].join('\n');
}
function download(name, text) {
  const a = el('a', { href: URL.createObjectURL(new Blob([text], { type: 'text/csv' })), download: name });
  document.body.append(a); a.click(); a.remove();
}
function resultTable(res, { onRow, tall, filter = true } = {}) {
  const wrap = el('div');
  if (res.error) return el('div', { class: 'err' }, res.error);
  if (!res.columns || !res.columns.length) return el('div', { class: 'empty' }, res.rowcount !== undefined ? `${res.rowcount} row(s) affected` : 'no result');
  if (!res.rows.length) return el('div', { class: 'empty' }, 'no rows');
  let rows = res.rows.slice();
  let sortCol = -1, sortDir = 1;
  const tbody = el('tbody');
  const render = () => {
    tbody.replaceChildren(...rows.map(r => {
      const tr = el('tr', { class: onRow ? 'clickable' : '' }, ...r.map(fmtCell));
      if (onRow) tr.addEventListener('click', () => onRow(Object.fromEntries(res.columns.map((c, i) => [c, r[i]]))));
      return tr;
    }));
  };
  const thead = el('thead', {}, el('tr', {}, ...res.columns.map((c, i) => el('th', {
    onclick: () => {
      sortDir = sortCol === i ? -sortDir : 1; sortCol = i;
      rows.sort((a, b) => (a[i] === null) - (b[i] === null) || (a[i] > b[i] ? 1 : a[i] < b[i] ? -1 : 0) * sortDir);
      render();
    }
  }, c))));
  render();
  const toolbar = el('div', { class: 'toolbar' },
    el('span', { class: 'hint' }, `${res.rows.length.toLocaleString()} rows${res.truncated ? ' (truncated, raise max rows)' : ''} · ${res.ms ?? '?'} ms`),
    el('span', { class: 'spacer' }),
    filter ? el('input', { class: 'filter', placeholder: 'filter rows…', oninput: (e) => {
      const q = e.target.value.toLowerCase();
      rows = res.rows.filter(r => !q || r.some(v => String(v ?? '').toLowerCase().includes(q)));
      render();
    } }) : null,
    el('button', { class: 'ghost', onclick: () => download(`${res.query || 'result'}.csv`, toCSV(res)) }, 'CSV'));
  wrap.append(toolbar, el('div', { class: 'tablewrap' + (tall ? ' tall' : '') }, el('table', { class: 'grid' }, thead, tbody)));
  return wrap;
}
function card(title, body, meta) {
  return el('div', { class: 'card' }, el('h3', {}, title, meta ? el('span', { class: 'meta' }, meta) : null), body);
}
function loading(msg = 'loading…') { return el('div', { class: 'empty' }, msg); }

/* ---------- Ops ---------- */
async function viewOps(main) {
  const params = { days: 7, hours: 24, wh: localStorage.getItem('wb.wh') || '' };
  const bar = el('div', { class: 'bar' },
    el('label', {}, 'warehouse'), el('input', { type: 'text', value: params.wh, placeholder: 'all', oninput: e => { params.wh = e.target.value.toUpperCase(); localStorage.setItem('wb.wh', params.wh); } }),
    el('label', {}, 'days'), el('input', { type: 'number', value: params.days, min: 1, oninput: e => params.days = e.target.value }),
    el('label', {}, 'hours'), el('input', { type: 'number', value: params.hours, min: 1, oninput: e => params.hours = e.target.value }),
    el('button', { class: 'primary', onclick: () => load() }, 'Refresh all'));
  const grid = el('div', { class: 'grid' });
  main.append(bar, el('div', { class: 'hint' }, 'Each panel is one named query in queries/ops.sql. Click a row in an orders/waves panel to jump to Trace.'), grid);
  const panels = await api('/api/ops/panels');
  const load = () => {
    grid.replaceChildren(...panels.map(p => card(p.title, loading(), p.name)));
    panels.forEach((p, i) => api(`/api/ops/${p.name}`, { params }).then(res => {
      const onRow = (row) => {
        if (row.wave_id) gotoTrace('wave', row.wave_id, row.wh_id);
        else if (row.order_number) gotoTrace('order', row.order_number, row.wh_id);
        else if (row.id && row.name) gotoTrace('employee', row.id);
        else if (row.employee_id) gotoTrace('employee', row.employee_id);
      };
      grid.children[i].replaceChildren(el('h3', {}, p.title, el('span', { class: 'meta' }, `${p.name} · ${res.ms} ms`)), resultTable(res, { onRow }));
    }).catch(e => grid.children[i].replaceChildren(el('h3', {}, p.title), el('div', { class: 'err' }, e.message))));
  };
  load();
}

/* ---------- Trace ---------- */
function gotoTrace(kind, key, wh) {
  state.traceReq = { kind, key, wh: wh || '' };
  location.hash = 'trace';
  show('trace');
}
async function viewTrace(main) {
  const kinds = await api('/api/trace/kinds');
  const req = state.traceReq || { kind: 'order', key: '', wh: '' };
  state.traceReq = null;
  const kindSel = el('select', {}, ...kinds.map(k => el('option', { value: k, selected: k === req.kind ? '' : null }, k)));
  const keyIn = el('input', { type: 'text', value: req.key, placeholder: 'order number / item / HU / PO / wave / employee id / location', style: 'min-width:360px' });
  const whIn = el('input', { type: 'text', value: req.wh, placeholder: 'wh (optional)' });
  const out = el('div');
  const run = async () => {
    const key = keyIn.value.trim(); if (!key) return;
    out.replaceChildren(loading(`tracing ${kindSel.value} ${key}…`));
    try {
      const t = await api(`/api/trace/${kindSel.value}`, { params: { n: key, wh: whIn.value.trim() } });
      out.replaceChildren(...t.sections.map(s => {
        const onRow = (row) => {
          if (kindSel.value !== 'wave' && row.wave_id) gotoTrace('wave', row.wave_id, row.wh_id);
          else if (kindSel.value !== 'hu' && (row.hu_id || row.container_id || row.destination_hu_id)) gotoTrace('hu', row.hu_id || row.container_id || row.destination_hu_id);
          else if (kindSel.value !== 'order' && row.order_number) gotoTrace('order', row.order_number, row.wh_id);
          else if (kindSel.value !== 'item' && row.item_number) gotoTrace('item', row.item_number, row.wh_id);
          else if (kindSel.value !== 'location' && row.location_id) gotoTrace('location', row.location_id, row.wh_id);
          else if (kindSel.value !== 'employee' && row.employee_id) gotoTrace('employee', row.employee_id);
        };
        return card(s.title, resultTable(s.result, { onRow }), `${s.result.query} · ${s.result.ms ?? '-'} ms`);
      }));
    } catch (e) { out.replaceChildren(el('div', { class: 'err' }, e.message)); }
  };
  keyIn.addEventListener('keydown', e => { if (e.key === 'Enter') run(); });
  main.append(el('div', { class: 'bar' }, kindSel, keyIn, whIn, el('button', { class: 'primary', onclick: run }, 'Trace')),
    el('div', { class: 'hint' }, 'Rows are clickable: a wave_id jumps to the wave trace, an hu_id to the HU trace, and so on.'), out);
  if (req.key) run();
}

/* ---------- Schema ---------- */
async function viewSchema(main) {
  const search = el('input', { type: 'text', placeholder: 'table name contains…', value: 't_' });
  const list = el('ul', { class: 'list' });
  const detail = el('div', { class: 'card' }, el('div', { class: 'empty' }, 'pick a table'));
  const colSearch = el('input', { type: 'text', placeholder: 'find column across tables…' });
  const loadList = async () => {
    list.replaceChildren(el('li', {}, 'loading…'));
    const res = await api('/api/schema/tables', { params: { like: search.value } });
    const ci = Object.fromEntries(res.columns.map((c, i) => [c, i]));
    list.replaceChildren(...res.rows.map(r => el('li', { onclick: (e) => { [...list.children].forEach(x => x.classList.remove('active')); e.currentTarget.classList.add('active'); openTable(r[ci.table_name]); } },
      r[ci.table_name], el('span', { class: 'meta' }, Number(r[ci.row_count]).toLocaleString()))));
  };
  const openTable = async (name) => {
    detail.replaceChildren(el('h3', {}, name), loading());
    try {
      const t = await api('/api/schema/table', { params: { name } });
      const tabs = {
        Columns: () => resultTable(t.columns, { filter: false, tall: true }),
        Indexes: () => resultTable(t.indexes, { filter: false }),
        'Foreign keys': () => resultTable(t.foreign_keys, { filter: false }),
        Triggers: () => resultTable(t.triggers, { filter: false }),
        'Used by': () => resultTable(t.used_by, { onRow: (row) => gotoObject(row.object_name.replace(/^dbo\./, '')) }),
        Sample: null,
      };
      const body = el('div');
      const sub = el('div', { class: 'subtabs' });
      const pick = async (label) => {
        [...sub.children].forEach(b => b.classList.toggle('active', b.textContent === label));
        if (label === 'Sample') { body.replaceChildren(loading()); body.replaceChildren(resultTable(await api('/api/schema/sample', { params: { name, n: 50 } }), { tall: true })); }
        else body.replaceChildren(tabs[label]());
      };
      sub.append(...Object.keys(tabs).map(l => el('button', { onclick: () => pick(l) }, l)));
      detail.replaceChildren(el('h3', {}, name, el('span', { class: 'meta' }, `${t.columns.rows.length} columns · ${t.indexes.rows.length} indexes · used by ${t.used_by.rows.length} objects`)), sub, body);
      pick('Columns');
    } catch (e) { detail.replaceChildren(el('h3', {}, name), el('div', { class: 'err' }, e.message)); }
  };
  search.addEventListener('keydown', e => { if (e.key === 'Enter') loadList(); });
  colSearch.addEventListener('keydown', async e => {
    if (e.key !== 'Enter') return;
    detail.replaceChildren(el('h3', {}, `columns like "${colSearch.value}"`), loading());
    const res = await api('/api/schema/find_column', { params: { like: colSearch.value } });
    detail.replaceChildren(el('h3', {}, `columns like "${colSearch.value}"`), resultTable(res, { tall: true, onRow: (row) => openTable(row.table_name) }));
  });
  main.append(el('div', { class: 'split' },
    el('div', { class: 'card' }, el('h3', {}, search, el('button', { class: 'ghost', onclick: loadList }, 'go')), list),
    el('div', {}, el('div', { class: 'bar' }, colSearch), detail)));
  loadList();
}

/* ---------- Objects ---------- */
function gotoObject(name) { state.objectReq = name; location.hash = 'objects'; show('objects'); }
function codeBlock(text) {
  return el('pre', { class: 'code' }, ...String(text || '').split('\n').map(l => el('span', { class: 'ln' }, l + '\n')));
}
async function viewObjects(main) {
  const q = el('input', { type: 'text', placeholder: 'name contains… (or body text with the box ticked)', value: state.objectReq || 'usp_', style: 'min-width:320px' });
  const body = el('input', { type: 'checkbox', id: 'bodysearch' });
  const list = el('ul', { class: 'list' });
  const detail = el('div', { class: 'card' }, el('div', { class: 'empty' }, 'pick an object'));
  const search = async () => {
    list.replaceChildren(el('li', {}, 'searching…'));
    const res = await api('/api/objects/search', { params: { q: q.value, body: body.checked ? 1 : 0 } });
    const ci = Object.fromEntries(res.columns.map((c, i) => [c, i]));
    list.replaceChildren(...res.rows.map(r => el('li', { onclick: (e) => { [...list.children].forEach(x => x.classList.remove('active')); e.currentTarget.classList.add('active'); open(r[ci.name]); } },
      r[ci.name], el('span', { class: 'meta' }, `${r[ci.type_desc].replace('SQL_', '').slice(0, 10)} ${String(r[ci.modify_date]).slice(0, 10)}`))));
    if (!res.rows.length) list.replaceChildren(el('li', {}, 'no matches'));
  };
  const open = async (name) => {
    detail.replaceChildren(el('h3', {}, name), loading());
    try {
      const o = await api('/api/objects/definition', { params: { name } });
      const row = o.definition.rows[0];
      if (!row) throw new Error(`${name} not found on ${state.profile}`);
      const def = row[o.definition.columns.indexOf('definition')];
      const modified = row[o.definition.columns.indexOf('modify_date')];
      const sub = el('div', { class: 'subtabs' });
      const pane = el('div');
      const tabs = {
        Definition: () => codeBlock(def),
        Parameters: () => resultTable(o.parameters, { filter: false }),
        Dependencies: () => resultTable(o.deps, { onRow: (r) => r.type_desc && !r.type_desc.includes('TABLE') ? open(r.object_name.replace(/^dbo\./, '')) : null }),
      };
      const pick = (l) => { [...sub.children].forEach(b => b.classList.toggle('active', b.textContent === l)); pane.replaceChildren(tabs[l]()); };
      sub.append(...Object.keys(tabs).map(l => el('button', { onclick: () => pick(l) }, l)),
        el('span', { class: 'spacer' }),
        el('button', { class: 'ghost', onclick: () => { state.diffReq = name; location.hash = 'diff'; show('diff'); } }, 'Diff PROD vs TEST'),
        el('button', { class: 'ghost', onclick: () => download(`${name}.sql`, def) }, 'Download .sql'));
      detail.replaceChildren(el('h3', {}, name, el('span', { class: 'meta' }, `modified ${modified} · ${(def || '').length.toLocaleString()} chars`)), sub, pane);
      pick('Definition');
    } catch (e) { detail.replaceChildren(el('h3', {}, name), el('div', { class: 'err' }, e.message)); }
  };
  q.addEventListener('keydown', e => { if (e.key === 'Enter') search(); });
  const recent = el('button', { class: 'ghost', onclick: async () => {
    detail.replaceChildren(el('h3', {}, 'objects modified in the last 30 days'), loading());
    detail.replaceChildren(el('h3', {}, 'objects modified in the last 30 days'), resultTable(await api('/api/objects/recent', { params: { days: 30 } }), { tall: true, onRow: (r) => open(r.name) }));
  } }, 'Recent changes');
  const stats = el('button', { class: 'ghost', onclick: async () => {
    detail.replaceChildren(el('h3', {}, 'proc stats (plan cache, since last restart)'), loading());
    detail.replaceChildren(el('h3', {}, 'proc stats (plan cache, since last restart)'), resultTable(await api('/api/objects/proc_stats', { params: { like: q.value } }), { tall: true, onRow: (r) => open(r.proc_name) }));
  } }, 'Proc stats');
  main.append(el('div', { class: 'split' },
    el('div', { class: 'card' }, el('h3', {}, q, el('label', { for: 'bodysearch', title: 'search inside definitions (slower)' }, body, ' body'), el('button', { class: 'ghost', onclick: search }, 'go')), list),
    el('div', {}, el('div', { class: 'bar' }, recent, stats), detail)));
  if (state.objectReq) { const n = state.objectReq; state.objectReq = null; q.value = n; search(); open(n); }
  else search();
}

/* ---------- SQL ---------- */
async function viewSQL(main) {
  const ta = el('textarea', { placeholder: 'SELECT TOP 100 * FROM t_order WITH (NOLOCK) WHERE wh_id = \'MAIN\' ORDER BY order_date DESC', spellcheck: 'false' });
  ta.value = localStorage.getItem('wb.sql') || '';
  const maxRows = el('input', { type: 'number', value: 500, min: 1, max: 5000, style: 'width:90px' });
  const allowWrite = el('input', { type: 'checkbox', id: 'allowwrite' });
  const out = el('div');
  const hist = el('ul', { class: 'list' });
  const savedList = el('ul', { class: 'list' });
  const run = async () => {
    const sql = ta.value.trim(); if (!sql) return;
    localStorage.setItem('wb.sql', ta.value);
    out.replaceChildren(loading('running…'));
    try {
      const res = await api('/api/sql/run', { body: { sql, profile: state.profile, max_rows: Number(maxRows.value), allow_write: allowWrite.checked } });
      res.query = 'adhoc';
      out.replaceChildren(card(`${res.kind} on ${res.profile}`, resultTable(res, { tall: true }), `${res.rowcount} rows · ${res.ms} ms`));
    } catch (e) { out.replaceChildren(el('div', { class: 'err' }, e.message)); }
    loadHistory();
  };
  const loadHistory = async () => {
    const h = await api('/api/sql/history', { params: { n: 40 } });
    hist.replaceChildren(...h.map(r => el('li', { title: r.sql, onclick: () => { ta.value = r.sql; } },
      el('span', { style: `color:${r.error ? 'var(--bad)' : r.kind === 'write' ? 'var(--warn)' : 'var(--muted)'}` }, r.profile),
      r.sql.replace(/\s+/g, ' ').slice(0, 70), el('span', { class: 'meta' }, r.error ? 'err' : `${r.rowcount}r ${r.ms}ms`))));
  };
  const loadSaved = async () => {
    const s = await api('/api/sql/saved');
    savedList.replaceChildren(...s.map(r => el('li', { title: r.note || r.sql, onclick: () => { ta.value = r.sql; } }, r.name,
      el('span', { class: 'meta' }, el('button', { class: 'ghost', onclick: async (e) => { e.stopPropagation(); if (confirm(`delete saved query "${r.name}"?`)) { await api('/api/sql/saved', { method: 'DELETE', params: { name: r.name } }); loadSaved(); } } }, '✕')))));
    if (!s.length) savedList.replaceChildren(el('li', {}, el('span', { class: 'hint' }, 'nothing saved yet')));
  };
  const save = async () => {
    const name = prompt('save as (name):'); if (!name) return;
    await api('/api/sql/saved', { body: { name, sql: ta.value, note: '' } }); loadSaved();
  };
  const library = el('button', { class: 'ghost', onclick: async () => {
    const lib = await api('/api/sql/library');
    out.replaceChildren(card('named query library (queries/*.sql)', el('ul', { class: 'list' },
      ...Object.entries(lib).map(([k, v]) => el('li', { onclick: () => { ta.value = v; } }, k, el('span', { class: 'meta' }, `${v.split('\n').length} lines`))))));
  } }, 'Library');
  ta.addEventListener('keydown', e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); run(); } });
  main.append(el('div', { class: 'split' },
    el('div', {}, card('history (local)', hist), el('div', { style: 'height:12px' }), card('saved queries', savedList)),
    el('div', {},
      ta,
      el('div', { class: 'bar' },
        el('button', { class: 'primary', onclick: run }, 'Run (Ctrl+Enter)'),
        el('label', {}, 'max rows'), maxRows,
        el('label', { for: 'allowwrite', title: 'only honoured on a writable profile (TEST with WORKBENCH_ALLOW_WRITES=1)' }, allowWrite, ' allow write'),
        el('button', { class: 'ghost', onclick: save }, 'Save'), library,
        el('span', { class: 'hint' }, 'one statement; PROD is always read-only; :name binds are not available here')),
      out)));
  loadHistory(); loadSaved();
}

/* ---------- Diff ---------- */
async function viewDiff(main) {
  const name = el('input', { type: 'text', placeholder: 'object name, e.g. usp_picking_tx', value: state.diffReq || '', style: 'min-width:300px' });
  state.diffReq = null;
  const left = el('select', {}, ...state.profiles.map(p => el('option', { value: p.name, selected: p.name === 'PROD' ? '' : null }, p.name)));
  const right = el('select', {}, ...state.profiles.map(p => el('option', { value: p.name, selected: p.name === 'TEST' ? '' : null }, p.name)));
  const bulk = el('input', { type: 'text', placeholder: 'bulk compare: name pattern, e.g. usp_%', style: 'min-width:260px' });
  const out = el('div');
  const runOne = async () => {
    if (!name.value.trim()) return;
    out.replaceChildren(loading('diffing…'));
    try {
      const d = await api('/api/diff/object', { params: { name: name.value.trim(), left: left.value, right: right.value } });
      const head = d.same ? 'identical' : !d.left_exists ? `missing on ${d.left}` : !d.right_exists ? `missing on ${d.right}` : `${d.diff.length} diff lines`;
      const body = el('div', { class: 'diff' }, ...d.diff.map(l => el('div', { class: l.startsWith('+++') || l.startsWith('---') ? 'hdr' : l.startsWith('@@') ? 'hunk' : l.startsWith('+') ? 'add' : l.startsWith('-') ? 'del' : '' }, l)));
      out.replaceChildren(card(`${d.name}: ${head}`, d.diff.length ? body : el('div', { class: 'empty' }, head), `${d.left} ${d.left_len} chars · ${d.right} ${d.right_len} chars`));
    } catch (e) { out.replaceChildren(el('div', { class: 'err' }, e.message)); }
  };
  const runBulk = async () => {
    out.replaceChildren(loading('hashing definitions on both servers…'));
    try {
      const d = await api('/api/diff/bulk', { params: { like: bulk.value, left: left.value, right: right.value } });
      const stats = el('div', { class: 'body' }, ...Object.entries(d.summary).map(([k, v]) => el('span', { class: 'stat' }, el('b', {}, v), k)));
      out.replaceChildren(card(`bulk compare ${d.left} vs ${d.right}`, el('div', {}, stats, resultTable(d, { tall: true, onRow: (r) => { name.value = r.name; runOne(); } }))));
    } catch (e) { out.replaceChildren(el('div', { class: 'err' }, e.message)); }
  };
  name.addEventListener('keydown', e => { if (e.key === 'Enter') runOne(); });
  bulk.addEventListener('keydown', e => { if (e.key === 'Enter') runBulk(); });
  main.append(el('div', { class: 'bar' }, name, left, el('span', {}, 'vs'), right, el('button', { class: 'primary', onclick: runOne }, 'Diff')),
    el('div', { class: 'bar' }, bulk, el('button', { class: 'ghost', onclick: runBulk }, 'Bulk compare')),
    el('div', { class: 'hint' }, 'Needs credentials for both profiles. Bulk compare hashes every matching module on each server and lists same / differs / one-side-only.'), out);
  if (name.value) runOne();
}

/* ---------- shell ---------- */
const VIEWS = { ops: viewOps, trace: viewTrace, schema: viewSchema, objects: viewObjects, sql: viewSQL, diff: viewDiff };
async function show(view) {
  state.view = VIEWS[view] ? view : 'ops';
  location.hash = state.view;
  document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('active', b.dataset.view === state.view));
  const main = $('#main'); main.replaceChildren(loading());
  main.replaceChildren();
  try { await VIEWS[state.view](main); } catch (e) { main.replaceChildren(el('div', { class: 'err' }, e.message)); }
}
async function setProfile(name) {
  state.profile = name; localStorage.setItem('wb.profile', name);
  const p = state.profiles.find(x => x.name === name);
  document.documentElement.style.setProperty('--profile', p ? p.color : '#4f8cff');
  checkHealth();
  show(state.view);
}
async function checkHealth() {
  const h = $('#health'); h.textContent = '…'; h.className = 'pill';
  try {
    const r = await api('/api/health');
    const me = r.profiles[state.profile];
    h.textContent = me.ok ? `${me.server_name} · ${me.db} · ${me.login} · ${me.ms} ms` : `down: ${me.error}`;
    h.className = 'pill ' + (me.ok ? 'ok' : 'bad');
  } catch (e) { h.textContent = e.message; h.className = 'pill bad'; }
}
(async function init() {
  const profs = await api('/api/sql/profiles');
  state.profiles = profs.filter(p => p.name);
  const sel = $('#profile');
  sel.replaceChildren(...state.profiles.map(p => el('option', { value: p.name, selected: p.name === state.profile ? '' : null }, `${p.name} · ${p.server}${p.writable ? ' (writable)' : ''}`)));
  sel.addEventListener('change', () => setProfile(sel.value));
  document.querySelectorAll('.tabs button').forEach(b => b.addEventListener('click', () => show(b.dataset.view)));
  window.addEventListener('hashchange', () => { if (location.hash.slice(1) !== state.view) show(location.hash.slice(1)); });
  setProfile(state.profile);
})();
