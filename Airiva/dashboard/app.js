/**
 * app.js — APIx Dashboard JavaScript
 *
 * Three visualisations:
 *   1. Time-series line chart  (Chart.js, composite + 3 route sub-indices)
 *   2. Sector heatmap          (custom DOM grid, median fare per route/week)
 *   3. Lead-time elasticity    (scatter chart, fare vs advance_days)
 *
 * Data sources: Supabase Postgres tables (index_values, fare_quotes, cpi_official)
 * and FastAPI endpoints.
 */

'use strict';

/* ── Supabase Configuration (Strict Anon Client Only) ───────────────────────── */
const SUPABASE_URL = 'https://kaljpvfcqsmanximfldz.supabase.co';
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImthbGpwdmZjcXNtYW54aW1mbGR6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTA1NzQ5MjQsImV4cCI6MjEwNjE1MDkyNH0.N34SyWmiBqyyubokFMc_KmCS57i7ZWIzRAr2Uowp6Yw';
const supabase = (window.supabase && typeof window.supabase.createClient === 'function')
  ? window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
  : null;

/* ── XSS Safety Utility ─────────────────────────────────────────────────────── */
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/* ── Constants ───────────────────────────────────────────────────────────── */
const API_BASE   = '';                // same origin
const COLORS     = {
  composite : '#1D4ED8', // Corporate Blue
  'DEL-BOM' : '#059669', // Emerald
  'DEL-BLR' : '#D97706', // Amber
  'BOM-BLR' : '#DC2626', // Crimson
};
const ROUTES     = ['DEL-BOM', 'DEL-BLR', 'BOM-BLR'];
const ROUTE_COLS = { 'DEL-BOM': 'del_bom', 'DEL-BLR': 'del_blr', 'BOM-BLR': 'bom_blr' };

/* ── State ───────────────────────────────────────────────────────────────── */
let currentPeriod = 'daily';
let indexChartInst = null;
let elasticityChartInst = null;
let allDailyData = [];
let _allQuotes = [];

/* ── Live Supabase Queries ───────────────────────────────────────────────── */
async function fetchSupabaseIndex(period = 'daily') {
  if (!supabase) return null;
  try {
    const { data, error } = await supabase
      .from('index_values')
      .select('*')
      .eq('granularity', period)
      .order('date', { ascending: true });
    if (error || !data || !data.length) return null;

    // Reshape to daily structure
    const dateMap = {};
    data.forEach(r => {
      const d = r.date;
      if (!dateMap[d]) {
        dateMap[d] = { index_date: d, index_value: 100, del_bom: 100, del_blr: 100, bom_blr: 100 };
      }
      if (r.route_code === null) dateMap[d].index_value = Number(r.index_value);
      else if (r.route_code === 'DEL-BOM') dateMap[d].del_bom = Number(r.index_value);
      else if (r.route_code === 'DEL-BLR') dateMap[d].del_blr = Number(r.index_value);
      else if (r.route_code === 'BOM-BLR') dateMap[d].bom_blr = Number(r.index_value);
    });
    return Object.values(dateMap);
  } catch (err) {
    console.warn('[Supabase] index_values fetch error:', err);
    return null;
  }
}

async function fetchSupabaseQuotes() {
  if (!supabase) return null;
  try {
    const { data, error } = await supabase
      .from('fare_quotes')
      .select('*')
      .order('travel_date', { ascending: false })
      .limit(200);
    if (error || !data || !data.length) return null;

    // Check simulated badge
    const badge = document.getElementById('badge-simulated-global');
    if (badge) {
      const isSeed = data.every(q => q.source === 'seed' || q.source === 'synthetic' || q.scrape_date === '2026-07-01');
      badge.style.display = isSeed ? 'inline-flex' : 'none';
    }

    return data.map(q => {
      const [origin, destination] = (q.route_code || 'DEL-BOM').split('-');
      return {
        id: q.id,
        scrape_date: q.scrape_date,
        origin: origin || 'DEL',
        destination: destination || 'BOM',
        carrier: q.carrier,
        flight_number: q.flight_number,
        travel_date: q.travel_date,
        advance_purchase_days: q.advance_purchase_days,
        fare_class: q.fare_class,
        base_fare: q.base_fare,
        taxes_fees: q.taxes_fees,
        total_fare: q.total_fare,
        seats_available: q.seats_available,
        source: q.source,
        sold_out: q.sold_out
      };
    });
  } catch (err) {
    console.warn('[Supabase] fare_quotes fetch error:', err);
    return null;
  }
}

/* ── Fallback generator ─────────────────────────────────────────────────── */
function generateSyntheticData(numDays = 60) {
  const today = new Date();
  const data  = [];
  let base = { composite: 100, 'DEL-BOM': 100, 'DEL-BLR': 100, 'BOM-BLR': 100 };

  for (let i = numDays - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const dateStr = d.toISOString().split('T')[0];

    const rw = () => 1 + (Math.random() - 0.5) * 0.03;
    base.composite  *= rw();
    base['DEL-BOM'] *= rw();
    base['DEL-BLR'] *= rw();
    base['BOM-BLR'] *= rw();

    data.push({
      index_date   : dateStr,
      index_value  : +base.composite.toFixed(4),
      del_bom      : +base['DEL-BOM'].toFixed(4),
      del_blr      : +base['DEL-BLR'].toFixed(4),
      bom_blr      : +base['BOM-BLR'].toFixed(4),
      sample_size  : Math.floor(Math.random() * 60) + 20,
    });
  }
  return data;
}

function generateSyntheticQuotes(n = 50) {
  const routes   = ROUTES;
  const carriers = ['6E', 'AI', '6E', '9W'];
  const classes  = ['SAVER', 'FLEX', 'ECONOMY', 'SUPER_SAVER'];
  const sources  = ['indigo', 'air_india', 'makemytrip'];
  const today    = new Date();
  const quotes   = [];

  for (let i = 0; i < n; i++) {
    const [origin, dest] = routes[i % 3].split('-');
    const base   = 3000 + Math.random() * 4000;
    const tax    = base * 0.18;
    const tdate  = new Date(today);
    const adv    = [7, 30][i % 2];
    tdate.setDate(tdate.getDate() + adv);

    quotes.push({
      id                   : i + 1,
      scrape_date          : today.toISOString().split('T')[0],
      origin,
      destination          : dest,
      carrier              : carriers[i % 4],
      flight_number        : `${carriers[i % 4]}-${100 + Math.floor(Math.random() * 900)}`,
      travel_date          : tdate.toISOString().split('T')[0],
      advance_purchase_days: adv,
      fare_class           : classes[i % 4],
      base_fare            : +base.toFixed(2),
      taxes_fees           : +tax.toFixed(2),
      total_fare           : +(base + tax).toFixed(2),
      seats_available      : Math.floor(Math.random() * 9) + 1,
      source               : sources[i % 3],
      is_censored          : false,
      is_outlier           : false,
      is_duplicate         : false,
    });
  }
  return quotes;
}

/* ── API helpers ─────────────────────────────────────────────────────────── */
async function apiFetch(path, fallback) {
  try {
    const res = await fetch(API_BASE + path, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    return fallback;
  }
}

/* ── Chart.js global defaults ────────────────────────────────────────────── */
if (window.Chart) {
  Chart.defaults.color          = '#475569';
  Chart.defaults.font.family    = "'Inter', system-ui, -apple-system, sans-serif";
  Chart.defaults.font.size      = 12;
  Chart.defaults.plugins.legend.display = false;
}

function gridColor() { return 'rgba(0, 0, 0, 0.06)'; }

/* ── Chart 1: Time-series ────────────────────────────────────────────────── */
function buildIndexDatasets(data) {
  const mkDataset = (label, key, color) => ({
    label,
    data       : data.map(d => ({ x: d.index_date, y: d[key] })),
    borderColor: color,
    borderWidth: 2,
    pointRadius: data.length > 30 ? 0 : 3,
    pointHoverRadius: 5,
    tension    : 0.3,
    fill       : false,
  });

  return [
    { ...mkDataset('Composite APIx', 'index_value', COLORS.composite), borderWidth: 2.8,
      backgroundColor: 'rgba(29, 78, 216, 0.05)', fill: 'origin' },
    mkDataset('DEL-BOM (Delhi-Mumbai)', 'del_bom', COLORS['DEL-BOM']),
    mkDataset('DEL-BLR (Delhi-Bengaluru)', 'del_blr', COLORS['DEL-BLR']),
    mkDataset('BOM-BLR (Mumbai-Bengaluru)', 'bom_blr', COLORS['BOM-BLR']),
  ];
}

function renderIndexChart(data) {
  const canvas = document.getElementById('chart-index');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  if (indexChartInst) indexChartInst.destroy();

  indexChartInst = new Chart(ctx, {
    type: 'line',
    data: { datasets: buildIndexDatasets(data) },
    options: {
      responsive   : true,
      maintainAspectRatio: false,
      interaction  : { mode: 'index', intersect: false },
      plugins: {
        tooltip: {
          backgroundColor: '#0F172A',
          borderColor    : '#334155',
          borderWidth    : 1,
          titleColor     : '#FFFFFF',
          bodyColor      : '#CBD5E1',
          padding        : 10,
          callbacks: {
            label: ctx => ` ${ctx.dataset.label}: ${ctx.parsed.y.toFixed(2)}`,
          },
        },
      },
      scales: {
        x: {
          type  : 'time',
          time  : { unit: 'day', tooltipFormat: 'dd MMM yyyy', displayFormats: { day: 'dd MMM' }},
          grid  : { color: gridColor() },
          ticks : { maxTicksLimit: 12, color: '#64748B' },
        },
        y: {
          grid  : { color: gridColor() },
          ticks : { color: '#64748B', callback: v => v.toFixed(1) },
          title : { display: true, text: 'Index Value (Base = 100)', color: '#475569', font: { size: 11, weight: 'bold' } },
        },
      },
    },
  });
}

/* ── Chart 2: Heatmap ────────────────────────────────────────────────────── */
function fareToHue(fare, minF, maxF) {
  const t = Math.max(0, Math.min(1, (fare - minF) / (maxF - minF || 1)));
  const h = Math.round((1 - t) * 140);
  return `hsl(${h}, 70%, 42%)`;
}

function groupByWeek(data) {
  const weeks = {};
  data.forEach(d => {
    const date  = new Date(d.index_date);
    const year  = date.getFullYear();
    const week  = getISOWeek(date);
    const wk    = `${year}-W${String(week).padStart(2,'0')}`;
    if (!weeks[wk]) weeks[wk] = { label: wk, del_bom: [], del_blr: [], bom_blr: [] };
    if (d.del_bom) weeks[wk].del_bom.push(d.del_bom);
    if (d.del_blr) weeks[wk].del_blr.push(d.del_blr);
    if (d.bom_blr) weeks[wk].bom_blr.push(d.bom_blr);
  });
  return Object.values(weeks).slice(-12);
}

function getISOWeek(d) {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  date.setUTCDate(date.getUTCDate() + 4 - (date.getUTCDay() || 7));
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  return Math.ceil((((date - yearStart) / 86400000) + 1) / 7);
}

function median(arr) {
  if (!arr.length) return null;
  const s = [...arr].sort((a,b) => a-b);
  const m = Math.floor(s.length/2);
  return s.length % 2 ? s[m] : (s[m-1]+s[m])/2;
}

function renderHeatmap(data) {
  const container = document.getElementById('heatmap-container');
  if (!container) return;
  const weeks     = groupByWeek(data);
  if (!weeks.length) { container.innerHTML = '<div class="heatmap-loading">No data yet</div>'; return; }

  const allVals = [];
  weeks.forEach(w => {
    ['del_bom','del_blr','bom_blr'].forEach(k => { const m = median(w[k]); if (m) allVals.push(m); });
  });
  const minF = Math.min(...allVals);
  const maxF = Math.max(...allVals);

  container.innerHTML = '';
  const grid = document.createElement('div');
  grid.className = 'heatmap-grid';

  // Header row
  const headerRow = document.createElement('div');
  headerRow.className = 'heatmap-header-row';
  headerRow.innerHTML = '<div class="heatmap-route-label"></div>' +
    weeks.map(w => `<div class="heatmap-week-label">${escapeHtml(w.label.split('-')[1])}</div>`).join('');
  grid.appendChild(headerRow);

  // Data rows
  const routeKeys = [
    { label: 'DEL→BOM', key: 'del_bom' },
    { label: 'DEL→BLR', key: 'del_blr' },
    { label: 'BOM→BLR', key: 'bom_blr' },
  ];

  routeKeys.forEach(({ label, key }) => {
    const rowEl = document.createElement('div');
    rowEl.className = 'heatmap-data-row';
    let rowHtml = `<div class="heatmap-route-label">${escapeHtml(label)}</div>`;
    weeks.forEach(w => {
      const m = median(w[key]);
      if (m === null) {
        rowHtml += '<div class="heatmap-cell" style="background:rgba(255,255,255,0.03)" data-tip="No data"></div>';
      } else {
        const bg = fareToHue(m, minF, maxF);
        const tip = `${escapeHtml(label)} ${escapeHtml(w.label)}: idx ${m.toFixed(1)}`;
        rowHtml += `<div class="heatmap-cell" style="background:${bg}" data-tip="${tip}"></div>`;
      }
    });
    rowEl.innerHTML = rowHtml;
    grid.appendChild(rowEl);
  });

  container.appendChild(grid);
}

/* ── Chart 3: Lead-time elasticity scatter ───────────────────────────────── */
function renderElasticityChart(quotes) {
  const canvas = document.getElementById('chart-elasticity');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (elasticityChartInst) elasticityChartInst.destroy();

  const byWindow = {};
  quotes.forEach(q => {
    const w = q.advance_purchase_days;
    if (!byWindow[w]) byWindow[w] = [];
    byWindow[w].push(q.total_fare);
  });

  const datasets = Object.entries(byWindow).map(([days, fares]) => {
    const isT7 = days == 7;
    return {
      label          : isT7 ? 'T+7 Days (Close-In)' : 'T+30 Days (Advance)',
      data           : fares.map((f, i) => ({ x: +days + (Math.random()-0.5)*0.8, y: f })),
      backgroundColor: isT7 ? 'rgba(220, 38, 38, 0.6)' : 'rgba(5, 150, 105, 0.6)',
      borderColor    : isT7 ? '#DC2626' : '#059669',
      borderWidth    : 1,
      pointRadius    : 5,
      pointHoverRadius: 7,
    };
  });

  const means = Object.entries(byWindow).map(([days, fares]) => ({
    x: +days, y: fares.reduce((s,v) => s+v,0)/fares.length
  }));

  datasets.push({
    label          : 'Average Fare',
    data           : means,
    backgroundColor: '#1D4ED8',
    borderColor    : '#1D4ED8',
    borderWidth    : 2.5,
    pointRadius    : 8,
    pointStyle     : 'rectRot',
    showLine       : true,
    tension        : 0,
  });

  elasticityChartInst = new Chart(ctx, {
    type: 'scatter',
    data: { datasets },
    options: {
      responsive          : true,
      maintainAspectRatio : false,
      plugins: {
        legend: {
          display   : true,
          position  : 'top',
          labels    : { color: '#334155', font: { size: 11, family: "'Inter', sans-serif" }, boxWidth: 12, padding: 14 },
        },
        tooltip: {
          backgroundColor: '#0F172A',
          borderColor    : '#334155',
          borderWidth    : 1,
          titleColor     : '#FFFFFF',
          bodyColor      : '#CBD5E1',
          callbacks: {
            label: ctx => ` ₹${ctx.parsed.y.toLocaleString('en-IN')} @ T+${Math.round(ctx.parsed.x)} days`,
          },
        },
      },
      scales: {
        x: {
          title  : { display: true, text: 'Advance Purchase Days (Lead Time)', color: '#475569', font: { size: 11, weight: 'bold' } },
          grid   : { color: gridColor() },
          ticks  : { color: '#64748B', stepSize: 5 },
          min    : 3, max: 35,
        },
        y: {
          title  : { display: true, text: 'Total Ticket Price (₹)', color: '#475569', font: { size: 11, weight: 'bold' } },
          grid   : { color: gridColor() },
          ticks  : { color: '#64748B', callback: v => `₹${v.toLocaleString('en-IN')}` },
        },
      },
    },
  });
}

/* ── KPI cards update ────────────────────────────────────────────────────── */
function updateKPIs(data) {
  if (!data.length) return;
  const latest = data[data.length - 1];
  const prev   = data.length > 1 ? data[data.length - 2] : latest;

  function setKPI(valId, deltaId, curr, prev) {
    const el    = document.getElementById(valId);
    const delta = document.getElementById(deltaId);
    if (!el || curr == null) return;
    el.textContent = Number(curr).toFixed(2);
    if (delta && prev != null && Number(prev) !== 0) {
      const pct = ((Number(curr) - Number(prev)) / Number(prev) * 100);
      delta.textContent = `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
      delta.className   = `kpi-delta ${pct > 0 ? 'pos' : pct < 0 ? 'neg' : 'neutral'}`;
    }
  }

  setKPI('kpi-composite-val', 'kpi-composite-delta', latest.index_value, prev.index_value);
  setKPI('kpi-del-bom-val',   'kpi-del-bom-delta',   latest.del_bom,     prev.del_bom);
  setKPI('kpi-del-blr-val',   'kpi-del-blr-delta',   latest.del_blr,     prev.del_blr);
  setKPI('kpi-bom-blr-val',   'kpi-bom-blr-delta',   latest.bom_blr,     prev.bom_blr);
}

/* ── Quotes table (Safe XSS Escaping) ────────────────────────────────────── */
function sourceTag(source) {
  const map = { indigo: 'source-indigo', air_india: 'source-airindia', makemytrip: 'source-makemytrip' };
  const labelMap = { indigo: 'IndiGo (Direct)', air_india: 'Air India (Direct)', makemytrip: 'MakeMyTrip (OTA)' };
  const cls = map[source] || 'source-indigo';
  const label = labelMap[source] || source;
  return `<span class="badge-source ${cls}">${escapeHtml(label)}</span>`;
}

function renderTable(quotes) {
  const tbody = document.getElementById('quotes-tbody');
  if (!tbody) return;
  if (!quotes.length) {
    tbody.innerHTML = '<tr><td colspan="11" class="table-loading">No fare quotes match the selected filters.</td></tr>';
    return;
  }
  tbody.innerHTML = '';
  quotes.forEach(q => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${escapeHtml(q.scrape_date)}</td>
      <td><strong>${escapeHtml(q.origin)} ↔ ${escapeHtml(q.destination)}</strong></td>
      <td><strong>${escapeHtml(q.carrier)}</strong></td>
      <td>${escapeHtml(q.flight_number)}</td>
      <td>T+${escapeHtml(q.advance_purchase_days)}d</td>
      <td>${escapeHtml(q.fare_class || 'Economy')}</td>
      <td>${q.base_fare ? '₹' + Number(q.base_fare).toLocaleString('en-IN') : '—'}</td>
      <td>${q.taxes_fees ? '₹' + Number(q.taxes_fees).toLocaleString('en-IN') : '—'}</td>
      <td><strong>₹${Number(q.total_fare).toLocaleString('en-IN')}</strong></td>
      <td>${escapeHtml(q.seats_available ?? '—')}</td>
      <td>${sourceTag(q.source)}</td>
    `;
    tbody.appendChild(tr);
  });
}

function filterTable() {
  const routeFilter  = document.getElementById('filter-route')?.value;
  const windowFilter = document.getElementById('filter-window')?.value;

  let filtered = _allQuotes;
  if (routeFilter) {
    const [o, d] = routeFilter.split('-');
    filtered = filtered.filter(q => q.origin === o && q.destination === d);
  }
  if (windowFilter) {
    filtered = filtered.filter(q => q.advance_purchase_days === +windowFilter);
  }
  renderTable(filtered);
}

/* ── Init ────────────────────────────────────────────────────────────────── */
async function init() {
  // 1. Load index data (Prefer live Supabase index_values)
  const sbIndex = await fetchSupabaseIndex('daily');
  const daily = sbIndex || await apiFetch('/index/daily?days=60', generateSyntheticData(60));
  allDailyData = daily;
  renderIndexChart(daily);
  renderHeatmap(daily);
  updateKPIs(daily);

  // 2. Load quotes (Prefer live Supabase fare_quotes)
  const sbQuotes = await fetchSupabaseQuotes();
  let quotes = sbQuotes;
  if (!quotes) {
    const quotesResp = await apiFetch('/raw-quotes?page_size=100', null);
    quotes = quotesResp?.data ?? generateSyntheticQuotes(80);
  }
  _allQuotes = quotes;
  renderTable(quotes);

  // 3. Elasticity chart from quotes
  renderElasticityChart(quotes);
}

document.addEventListener('DOMContentLoaded', init);
