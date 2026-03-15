/* =========================================================
   AI-FINDER — Frontend SPA logic
   ========================================================= */

'use strict';

// ── API base ──────────────────────────────────────────────
const API = '/api/v1';

// ── State ─────────────────────────────────────────────────
let state = {
  view: 'dashboard',
  results: { page: 1, per_page: 20, platform: '', has_secrets: null, q: '' },
  dorks: { type: 'google' },
};

// ── DOM helpers ───────────────────────────────────────────
const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'cls') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const c of children) {
    if (c == null) continue;
    e.append(typeof c === 'string' ? document.createTextNode(c) : c);
  }
  return e;
}

// ── Fetch wrapper ─────────────────────────────────────────
async function apiFetch(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

// ── Toast notifications ───────────────────────────────────
function toast(msg, type = 'info', duration = 4000) {
  const box = $('#toast-container');
  const t = el('div', { cls: `toast ${type}` }, msg);
  box.append(t);
  setTimeout(() => t.remove(), duration);
}

// ── Platform badge ────────────────────────────────────────
const PLATFORM_COLORS = {
  claude:    { bg: '#d97706', text: '#fff' },
  openai:    { bg: '#10b981', text: '#fff' },
  cursor:    { bg: '#8b5cf6', text: '#fff' },
  copilot:   { bg: '#3b82f6', text: '#fff' },
  langchain: { bg: '#f59e0b', text: '#000' },
  crewai:    { bg: '#ef4444', text: '#fff' },
  cline:     { bg: '#06b6d4', text: '#000' },
  gemini:    { bg: '#6366f1', text: '#fff' },
  unknown:   { bg: '#6b7280', text: '#fff' },
};

function platformBadge(platform) {
  const { bg, text } = PLATFORM_COLORS[platform] || PLATFORM_COLORS.unknown;
  return el('span', {
    cls: 'platform-badge',
    style: `background:${bg};color:${text}`,
  }, platform);
}

// ── Navigation ────────────────────────────────────────────
function showView(viewName) {
  state.view = viewName;
  $$('.view').forEach(v => v.classList.remove('active'));
  $(`#view-${viewName}`)?.classList.add('active');
  $$('.nav-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.view === viewName);
  });
  if (viewName === 'dashboard') loadDashboard();
  if (viewName === 'results')   loadResults();
  if (viewName === 'dorks')     loadDorks();
}

// ── Dashboard ─────────────────────────────────────────────
async function loadDashboard() {
  try {
    const [stats, recent] = await Promise.all([
      apiFetch('/stats'),
      apiFetch('/results?page=1&per_page=5'),
    ]);
    renderStats(stats);
    renderPlatformBreakdown(stats.by_platform);
    renderRecentResults(recent.results);
  } catch (e) {
    toast(e.message, 'error');
  }
}

function renderStats(stats) {
  $('#stat-total').textContent   = stats.total.toLocaleString();
  $('#stat-secrets').textContent = stats.with_secrets.toLocaleString();
  $('#stat-findings').textContent = stats.total_secret_findings.toLocaleString();
  const platforms = Object.keys(stats.by_platform).length;
  $('#stat-platforms').textContent = platforms;
}

function renderPlatformBreakdown(byPlatform) {
  const container = $('#platform-breakdown');
  container.innerHTML = '';
  for (const [p, count] of Object.entries(byPlatform)) {
    const color = PLATFORM_COLORS[p] || PLATFORM_COLORS.unknown;
    const chip = el('div',
      {
        cls: 'platform-chip',
        style: `background:${color.bg}22;color:${color.bg};border-color:${color.bg}44`,
        onclick: () => {
          state.results.platform = p;
          showView('results');
        },
      },
      p,
      el('span', { cls: 'chip-count' }, `(${count})`),
    );
    container.append(chip);
  }
}

function renderRecentResults(results) {
  const container = $('#recent-results');
  container.innerHTML = '';
  if (!results.length) {
    container.append(emptyState('🔍', 'No findings yet. Start a scan to discover AI configurations.'));
    return;
  }
  results.forEach(r => container.append(resultRow(r)));
}

// ── Results view ──────────────────────────────────────────
async function loadResults() {
  const { page, per_page, platform, has_secrets, q } = state.results;
  const params = new URLSearchParams({ page, per_page });
  if (platform) params.set('platform', platform);
  if (has_secrets !== null) params.set('has_secrets', has_secrets);
  if (q) params.set('q', q);

  try {
    const data = await apiFetch(`/results?${params}`);
    renderResultsList(data);
  } catch (e) {
    toast(e.message, 'error');
  }
}

function renderResultsList(data) {
  const container = $('#results-list');
  const countEl   = $('#results-count');
  const paginEl   = $('#results-pagination');
  container.innerHTML = '';
  paginEl.innerHTML   = '';

  countEl.textContent = `${data.total.toLocaleString()} result${data.total !== 1 ? 's' : ''}`;

  if (!data.results.length) {
    container.append(emptyState('🔍', 'No results match the current filters.'));
    return;
  }

  data.results.forEach(r => container.append(resultRow(r)));
  renderPagination(paginEl, data.page, data.pages);
}

function resultRow(r) {
  const row = el('div', { cls: 'result-row', onclick: () => openDetail(r.id) });

  // Platform badge
  row.append(el('div', { cls: 'result-platform' }, platformBadge(r.platform)));

  // Body
  const body = el('div', { cls: 'result-body' });
  body.append(el('div', { cls: 'result-url', title: r.url }, r.url));
  const tagsEl = el('div', { cls: 'result-tags' });
  (r.tags || '').split(',').filter(Boolean).slice(0, 6).forEach(t =>
    tagsEl.append(el('span', { cls: 'tag' }, t.trim())),
  );
  body.append(tagsEl);
  row.append(body);

  // Meta
  const meta = el('div', { cls: 'result-meta' });
  if (r.has_secrets) {
    meta.append(el('div', { cls: 'secret-badge' }, '⚠', ' secrets'));
  }
  meta.append(el('div', { cls: 'ts' }, fmtDate(r.indexed_at)));
  row.append(meta);

  return row;
}

function renderPagination(container, current, total) {
  if (total <= 1) return;

  const prev = el('button', {
    cls: 'page-btn',
    disabled: current <= 1 ? '' : null,
    onclick: () => { state.results.page = current - 1; loadResults(); },
  }, '← Prev');
  container.append(prev);

  // Show window of pages
  const start = Math.max(1, current - 2);
  const end   = Math.min(total, current + 2);
  for (let p = start; p <= end; p++) {
    const btn = el('button', {
      cls: `page-btn${p === current ? ' active' : ''}`,
      onclick: () => { state.results.page = p; loadResults(); },
    }, String(p));
    container.append(btn);
  }

  const next = el('button', {
    cls: 'page-btn',
    onclick: () => { state.results.page = current + 1; loadResults(); },
  }, 'Next →');
  if (current >= total) next.disabled = true;
  container.append(next);
}

// ── Detail modal ──────────────────────────────────────────
async function openDetail(id) {
  try {
    const r = await apiFetch(`/results/${id}`);
    renderDetailModal(r);
    $('#modal-overlay').classList.add('open');
  } catch (e) {
    toast(e.message, 'error');
  }
}

function renderDetailModal(r) {
  const modal = $('#detail-modal');
  modal.innerHTML = '';

  modal.append(
    el('button', { cls: 'modal-close', onclick: closeModal }, '✕'),
    el('div', { cls: 'modal-title' }, r.url),
  );

  // KV grid
  const grid = el('div', { cls: 'detail-grid' });
  const kv = (k, v) => {
    const d = el('div', { cls: 'detail-kv' });
    d.append(el('div', { cls: 'detail-key' }, k));
    d.append(el('div', { cls: 'detail-val' }, v || '—'));
    return d;
  };
  grid.append(
    kv('Platform', platformBadge(r.platform)),
    kv('Indexed', fmtDate(r.indexed_at, true)),
    kv('Hash', r.content_hash.slice(0, 16) + '…'),
    kv('Secrets', r.has_secrets ? el('span', { style: 'color:var(--danger)' }, '⚠ Yes') : 'None'),
  );
  modal.append(grid);

  // Tags
  if (r.tags) {
    modal.append(sectionTitle('Tags'));
    const tagsEl = el('div', { cls: 'result-tags', style: 'margin-bottom:.5rem' });
    r.tags.split(',').filter(Boolean).forEach(t =>
      tagsEl.append(el('span', { cls: 'tag' }, t.trim())),
    );
    modal.append(tagsEl);
  }

  // Secret findings
  if (r.secret_findings?.length) {
    modal.append(sectionTitle(`Secret Findings (${r.secret_findings.length})`));
    const list = el('div', { cls: 'secret-list' });
    r.secret_findings.forEach(f => {
      const item = el('div', { cls: 'secret-item' });
      item.append(el('div', { cls: 'secret-rule' }, f.rule_name || 'unknown'));
      if (f.redacted) item.append(el('div', { cls: 'secret-redacted' }, f.redacted));
      if (f.context) item.append(el('div', { style: 'font-size:.78rem;color:var(--text-muted);margin-top:.25rem' }, f.context));
      list.append(item);
    });
    modal.append(list);
  }

  // Raw content
  if (r.raw_content) {
    modal.append(sectionTitle('Raw Content'));
    const wrap = el('div', { cls: 'raw-content-wrap' });
    const pre  = el('pre', { cls: 'raw-pre' }, r.raw_content);
    const btn  = el('button', { cls: 'raw-toggle', onclick: () => {
      pre.classList.toggle('open');
      btn.querySelector('.arrow').textContent = pre.classList.contains('open') ? '▲' : '▼';
    }},
      el('span', {}, 'Show raw content'),
      el('span', { cls: 'arrow' }, '▼'),
    );
    wrap.append(btn, pre);
    modal.append(wrap);
  }
}

function closeModal() {
  $('#modal-overlay').classList.remove('open');
}

function sectionTitle(text) {
  return el('div', { cls: 'section-title' }, text);
}

// ── Dorks view ────────────────────────────────────────────
async function loadDorks() {
  const type = state.dorks.type;
  try {
    const dorks = await apiFetch(`/dorks?type=${type}`);
    renderDorksTable(dorks);
  } catch (e) {
    toast(e.message, 'error');
  }
}

function renderDorksTable(dorks) {
  const tbody = $('#dorks-body');
  tbody.innerHTML = '';
  dorks.forEach(d => {
    const tr = el('tr', {});
    const copyBtn = el('button', {
      cls: 'copy-btn',
      onclick: () => { navigator.clipboard.writeText(d.query); toast('Copied!', 'success', 2000); },
    }, 'Copy');
    const tagsCell = el('td', {});
    (d.tags || []).forEach(t => tagsCell.append(el('span', { cls: 'tag' }, t)));
    tr.append(
      el('td', {}, d.query),
      el('td', {}, d.description),
      tagsCell,
      el('td', {}, copyBtn),
    );
    tbody.append(tr);
  });
}

// ── Scan view ─────────────────────────────────────────────
function initScanForm() {
  const form   = $('#scan-form');
  const jobBox = $('#scan-job-box');
  let pollTimer;

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const urls = $('#scan-urls').value.trim().split('\n').filter(Boolean);
    const body = {
      urls,
      github_search: $('#scan-github').checked,
      github_token:  $('#scan-github-token').value.trim() || null,
      gitlab_search: $('#scan-gitlab').checked,
      gitlab_token:  $('#scan-gitlab-token').value.trim() || null,
    };
    try {
      const job = await apiFetch('/scan', { method: 'POST', body: JSON.stringify(body) });
      showJobBox(jobBox, job);
      pollTimer = setInterval(() => pollJob(job.job_id, jobBox, pollTimer, 'scan'), 2000);
    } catch (err) {
      toast(err.message, 'error');
    }
  });
}

// ── Crawl view ────────────────────────────────────────────
function initCrawlForm() {
  const form   = $('#crawl-form');
  const jobBox = $('#crawl-job-box');
  let pollTimer;

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const body = {
      github_token: $('#crawl-github-token').value.trim() || null,
      gitlab_token: $('#crawl-gitlab-token').value.trim() || null,
      target_url:   $('#crawl-target').value.trim() || null,
      use_github:   $('#crawl-use-github').checked,
      use_gitlab:   $('#crawl-use-gitlab').checked,
      max_queries:  parseInt($('#crawl-max-queries').value) || null,
      urls_file:    $('#crawl-urls-file').value.trim() || 'urls.txt',
    };
    try {
      const job = await apiFetch('/crawl', { method: 'POST', body: JSON.stringify(body) });
      showJobBox(jobBox, job);
      pollTimer = setInterval(() => pollJob(job.job_id, jobBox, pollTimer, 'crawl'), 2000);
    } catch (err) {
      toast(err.message, 'error');
    }
  });
}

// ── Job polling ───────────────────────────────────────────
function showJobBox(box, job) {
  box.classList.add('visible');
  updateJobBox(box, job);
}

function updateJobBox(box, job) {
  const statusEl = box.querySelector('.job-status-line');
  const idEl     = box.querySelector('.job-id');
  const icon = job.status === 'running' || job.status === 'queued'
    ? '<div class="spinner"></div>'
    : job.status === 'done' ? '✅' : '❌';
  const msg = job.message || job.error || job.status;
  statusEl.innerHTML = `${icon} <span>${msg}</span>`;
  idEl.textContent = `Job ID: ${job.job_id}`;
}

async function pollJob(jobId, box, timer, type) {
  try {
    const job = await apiFetch(`/jobs/${jobId}`);
    updateJobBox(box, job);
    if (job.status === 'done' || job.status === 'error') {
      clearInterval(timer);
      if (job.status === 'done') {
        toast(job.message, 'success');
        if (type === 'scan') loadDashboard();
      } else {
        toast(job.error || 'Job failed', 'error');
      }
    }
  } catch (e) {
    clearInterval(timer);
    toast(e.message, 'error');
  }
}

// ── Hero search → results ─────────────────────────────────
function initHeroSearch() {
  const searchInput = $('#hero-search');
  const searchForm  = $('#hero-search-form');
  searchForm.addEventListener('submit', e => {
    e.preventDefault();
    const q = searchInput.value.trim();
    if (q) {
      state.results.q = q;
      state.results.page = 1;
      showView('results');
    }
  });
}

// ── Results filters ───────────────────────────────────────
function initResultsFilters() {
  // Platform select — populated dynamically
  const platformSel = $('#filter-platform');
  apiFetch('/platforms').then(platforms => {
    platforms.forEach(p => {
      platformSel.append(el('option', { value: p }, p));
    });
  }).catch(() => {});

  platformSel.addEventListener('change', () => {
    state.results.platform = platformSel.value;
    state.results.page = 1;
    loadResults();
  });

  $('#filter-secrets').addEventListener('change', function () {
    state.results.has_secrets = this.checked ? true : null;
    state.results.page = 1;
    loadResults();
  });

  $('#results-search-form').addEventListener('submit', e => {
    e.preventDefault();
    state.results.q = $('#results-search-input').value.trim();
    state.results.page = 1;
    loadResults();
  });
}

// ── Utility ───────────────────────────────────────────────
function fmtDate(iso, long = false) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (long) return d.toLocaleString();
  return d.toLocaleDateString();
}

function emptyState(icon, msg) {
  return el('div', { cls: 'empty-state' },
    el('div', { cls: 'empty-icon' }, icon),
    el('p', {}, msg),
  );
}

// ── Init ──────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Nav buttons
  $$('.nav-btn[data-view]').forEach(btn => {
    btn.addEventListener('click', () => showView(btn.dataset.view));
  });

  // Modal close
  $('#modal-overlay').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeModal();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
  });

  // Dork type selector
  $$('.dork-type-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('.dork-type-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.dorks.type = btn.dataset.type;
      loadDorks();
    });
  });

  initHeroSearch();
  initResultsFilters();
  initScanForm();
  initCrawlForm();

  // Start on dashboard
  showView('dashboard');
});
