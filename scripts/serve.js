/**
 * scripts/serve.js — Standalone development server for Airiva Dashboard & API
 *
 * Serves:
 *   /              → Airiva/dashboard/index.html
 *   /dashboard/*   → static files in Airiva/dashboard/
 *   /index/daily   → daily index time-series
 *   /index/weekly  → weekly index time-series
 *   /index/monthly → monthly index time-series
 *   /raw-quotes    → fare quotes parsed from data/seed/synthetic_fares.csv
 *   /health        → system health endpoint
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');

const PORT = process.env.PORT || 8000;
const DASHBOARD_DIR = path.resolve(__dirname, '..', 'Airiva', 'dashboard');
const SEED_FILE = path.resolve(__dirname, '..', 'data', 'seed', 'synthetic_fares.csv');

const MIME_TYPES = {
  '.html': 'text/html; charset=UTF-8',
  '.css': 'text/css; charset=UTF-8',
  '.js': 'application/javascript; charset=UTF-8',
  '.json': 'application/json; charset=UTF-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
};

// Parse seed quotes
function loadSeedQuotes() {
  if (!fs.existsSync(SEED_FILE)) return [];
  const lines = fs.readFileSync(SEED_FILE, 'utf-8').trim().split('\n');
  const headers = lines[0].split(',').map(h => h.trim());
  const quotes = [];

  for (let i = 1; i < lines.length; i++) {
    const parts = lines[i].split(',').map(p => p.trim());
    if (parts.length < headers.length) continue;
    const row = {};
    headers.forEach((h, idx) => {
      row[h] = parts[idx];
    });
    quotes.push({
      id: i,
      scrape_date: '2026-07-08',
      origin: row.origin,
      destination: row.destination,
      route_code: `${row.origin}-${row.destination}`,
      carrier: row.carrier,
      flight_number: row.flight_number,
      travel_date: row.travel_date,
      advance_purchase_days: parseInt(row.advance_purchase_days, 10),
      fare_class: row.fare_class,
      base_fare: parseFloat(row.base_fare),
      taxes_fees: parseFloat(row.taxes_fees),
      total_fare: parseFloat(row.total_fare),
      seats_available: parseInt(row.seats_available, 10),
      source: row.source,
      is_censored: false,
      is_outlier: false,
      is_duplicate: false
    });
  }
  return quotes;
}

const seedQuotes = loadSeedQuotes();

// Generate time-series index data
function generateDailyIndex(days = 60) {
  const result = [];
  const today = new Date();
  let baseComp = 100.0, baseDelBom = 100.0, baseDelBlr = 100.0, baseBomBlr = 100.0;

  // Weights: DEL-BOM: 0.40, DEL-BLR: 0.35, BOM-BLR: 0.25
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const dateStr = d.toISOString().split('T')[0];

    // Systematic seasonal trend + small noise
    const trend = Math.sin((days - i) / 10) * 0.4;
    const noise1 = (Math.random() - 0.49) * 0.8;
    const noise2 = (Math.random() - 0.49) * 0.9;
    const noise3 = (Math.random() - 0.49) * 0.7;

    baseDelBom = Math.max(85, Math.min(130, +(baseDelBom * (1 + (trend + noise1) / 100)).toFixed(4)));
    baseDelBlr = Math.max(85, Math.min(130, +(baseDelBlr * (1 + (trend + noise2) / 100)).toFixed(4)));
    baseBomBlr = Math.max(85, Math.min(130, +(baseBomBlr * (1 + (trend + noise3) / 100)).toFixed(4)));

    baseComp = +(0.40 * baseDelBom + 0.35 * baseDelBlr + 0.25 * baseBomBlr).toFixed(4);

    result.push({
      index_date: dateStr,
      index_value: baseComp,
      del_bom: baseDelBom,
      del_blr: baseDelBlr,
      bom_blr: baseBomBlr,
      sample_size: 45 + Math.floor(Math.random() * 25),
      computed_at: new Date(d.getTime() + 18 * 3600 * 1000).toISOString()
    });
  }
  return result;
}

const dailyIndexData = generateDailyIndex(60);

const server = http.createServer((req, res) => {
  const parsed = url.parse(req.url, true);
  const pathname = parsed.pathname;

  // Enable CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', '*');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  if (pathname === '/favicon.ico') {
    res.writeHead(204);
    res.end();
    return;
  }

  // API Endpoints
  if (pathname === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', db_connected: true, version: '0.1.0' }));
    return;
  }

  if (pathname === '/index/daily') {
    const days = parseInt(parsed.query.days || '30', 10);
    const data = dailyIndexData.slice(-days);
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(data));
    return;
  }

  if (pathname === '/index/weekly') {
    // Group into weeks
    const weeks = [];
    for (let i = 0; i < dailyIndexData.length; i += 7) {
      const chunk = dailyIndexData.slice(i, i + 7);
      if (chunk.length === 0) continue;
      const start = chunk[0].index_date;
      const avg = key => +(chunk.reduce((s, r) => s + r[key], 0) / chunk.length).toFixed(4);
      weeks.push({
        week_start_date: start,
        iso_year: 2026,
        iso_week: Math.floor(i / 7) + 1,
        index_value: avg('index_value'),
        del_bom: avg('del_bom'),
        del_blr: avg('del_blr'),
        bom_blr: avg('bom_blr'),
        sample_size: chunk.reduce((s, r) => s + r.sample_size, 0)
      });
    }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(weeks));
    return;
  }

  if (pathname === '/index/monthly') {
    // 6 months
    const months = [
      { year: 2026, month: 2, index_value: 98.42, del_bom: 99.10, del_blr: 97.80, bom_blr: 98.20 },
      { year: 2026, month: 3, index_value: 100.00, del_bom: 100.00, del_blr: 100.00, bom_blr: 100.00 },
      { year: 2026, month: 4, index_value: 102.35, del_bom: 103.12, del_blr: 101.90, bom_blr: 101.85 },
      { year: 2026, month: 5, index_value: 105.80, del_bom: 107.20, del_blr: 104.95, bom_blr: 104.80 },
      { year: 2026, month: 6, index_value: 103.90, del_bom: 104.85, del_blr: 103.40, bom_blr: 102.90 },
      { year: 2026, month: 7, index_value: 107.45, del_bom: 108.90, del_blr: 106.80, bom_blr: 105.70 },
    ];
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(months));
    return;
  }

  if (pathname === '/raw-quotes') {
    const pageSize = parseInt(parsed.query.page_size || '100', 10);
    const data = (seedQuotes.length > 0 ? seedQuotes : []).slice(0, pageSize);
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ total: data.length, data: data }));
    return;
  }

  // MoSPI CPI Airfare Official Benchmark
  if (pathname === '/benchmark/cpi' || pathname === '/data/benchmark/cpi_benchmark.json') {
    const benchPath = path.resolve(__dirname, '..', 'data', 'benchmark', 'cpi_benchmark.json');
    if (fs.existsSync(benchPath)) {
      res.writeHead(200, { 'Content-Type': 'application/json; charset=UTF-8' });
      res.end(fs.readFileSync(benchPath, 'utf-8'));
      return;
    }
  }

  if (pathname === '/data/cpi/cpi_airfare_clean.csv') {
    const csvPath = path.resolve(__dirname, '..', 'data', 'cpi', 'cpi_airfare_clean.csv');
    if (fs.existsSync(csvPath)) {
      res.writeHead(200, { 'Content-Type': 'text/csv; charset=UTF-8' });
      res.end(fs.readFileSync(csvPath, 'utf-8'));
      return;
    }
  }

  // Static files from Airiva/dashboard
  let relPath = pathname;
  if (relPath === '/' || relPath === '/dashboard' || relPath === '/dashboard/' || relPath === '/Airiva-dashboard.html') {
    relPath = '/index.html';
  } else if (relPath.startsWith('/dashboard/')) {
    relPath = relPath.replace(/^\/dashboard/, '');
  }

  const filePath = path.join(DASHBOARD_DIR, relPath);
  const ext = path.extname(filePath).toLowerCase();

  fs.stat(filePath, (err, stats) => {
    if (err || !stats.isFile()) {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=UTF-8' });
      res.end('404 Not Found');
      return;
    }

    const contentType = MIME_TYPES[ext] || 'application/octet-stream';
    res.writeHead(200, { 'Content-Type': contentType });
    fs.createReadStream(filePath).pipe(res);
  });
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`Airiva Server & Dashboard running at http://127.0.0.1:${PORT}/`);
  console.log(`- Dashboard: http://127.0.0.1:${PORT}/`);
  console.log(`- API Daily: http://127.0.0.1:${PORT}/index/daily`);
  console.log(`- API Quotes: http://127.0.0.1:${PORT}/raw-quotes`);
  console.log(`- Health: http://127.0.0.1:${PORT}/health`);
});
