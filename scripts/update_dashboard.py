# scripts/update_dashboard.py
import re
import sys
from pathlib import Path

DASHBOARD_FILE = Path("Airiva/dashboard/index.html")

def update_dashboard():
    if not DASHBOARD_FILE.exists():
        print(f"Error: {DASHBOARD_FILE} does not exist!")
        sys.exit(1)

    with open(DASHBOARD_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    # Create backup
    backup_file = DASHBOARD_FILE.with_suffix(".html.bak")
    with open(backup_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Backup created at {backup_file}")

    # 1. Update <head>: Add CSP meta tag & Pinned Supabase JS
    csp_meta = """  <!-- Content Security Policy: Strict origin, Supabase API, Render backend, and trusted CDNs -->
  <meta http-equiv="Content-Security-Policy"
    content="default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self' https://kaljpvfcqsmanximfldz.supabase.co https://airiva.onrender.com https://cdn.jsdelivr.net http://localhost:* http://127.0.0.1:*; object-src 'none'; frame-src 'none';" />"""
    
    supabase_script = """  <!-- Supabase JS Client (Pinned Version 2.39.8) -->
  <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.39.8/dist/umd/supabase.js"></script>"""

    if "Content-Security-Policy" not in html:
        html = html.replace('<meta name="viewport" content="width=device-width, initial-scale=1.0" />',
                            '<meta name="viewport" content="width=device-width, initial-scale=1.0" />\n' + csp_meta)
    
    if "supabase-js" not in html:
        html = html.replace('<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>',
                            '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>\n' + supabase_script)

    # 2. Add extra CSS styles for Simulated badge, admin tabs, and auth errors
    extra_styles = """
    /* Simulated Data Badge */
    .badge-simulated {
      background: #FFFBEB !important;
      color: #B45309 !important;
      border: 1px solid #FDE68A !important;
      padding: 4px 10px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }

    /* Auth error alert */
    .auth-error-alert {
      background: #FEF2F2;
      color: #B91C1C;
      border: 1px solid #FECACA;
      padding: 10px 14px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 16px;
      display: none;
    }

    /* Admin Tabs Styling */
    .admin-tab-btn {
      padding: 8px 16px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      border: 1px solid var(--color-line);
      background: var(--color-panel);
      color: var(--color-muted);
      transition: all 0.2s ease;
    }
    .admin-tab-btn:hover {
      background: var(--color-accent-subtle);
      color: var(--color-accent);
    }
    .admin-tab-btn.active {
      background: var(--color-accent);
      color: #ffffff;
      border-color: var(--color-accent);
      box-shadow: 0 2px 6px rgba(47, 144, 212, 0.25);
    }
    .admin-tab-pane {
      display: none;
    }
    .admin-tab-pane.active {
      display: block;
    }
"""
    if "/* Admin Tabs Styling */" not in html:
        html = html.replace('/* ==========================================================================\n       Airiva — FRONTEND & UI STRUCTURE PLAN V2',
                            extra_styles + '\n    /* ==========================================================================\n       Airiva — FRONTEND & UI STRUCTURE PLAN V2')

    # 3. Navbar: City-Pair Heatmaps data-role="analyst admin", and add global simulated badge
    html = re.sub(r'<li data-role="guest analyst admin">\s*<a class="nav-link" data-page="heatmaps"',
                  r'<li data-role="analyst admin"><a class="nav-link" data-page="heatmaps"',
                  html)

    badge_markup = '<span class="badge-simulated" id="badge-simulated-global" style="display:none;" title="Dataset contains seed/synthetic baseline records only">⚠️ Simulated Data</span>\n      '
    if 'id="badge-simulated-global"' not in html:
        html = html.replace('<!-- Authentication Controls (Guest Sign In / Register vs Active Session) -->',
                            badge_markup + '<!-- Authentication Controls (Guest Sign In / Register vs Active Session) -->')

    # 4. Replace Login form contents: Remove role switcher & 1-click login, add real inputs & MFA container
    login_section_old = re.search(r'(<section class="page-view" id="page-login">.*?)(<section class="page-view" id="page-register">)', html, re.DOTALL)
    if login_section_old:
        new_login_section = """<section class="page-view" id="page-login">
      <div class="auth-page-container">
        <div class="auth-card">
          <div class="auth-card-header">
            <div class="auth-card-badge">
              <span>🔐</span>
              <span>Airiva Security Portal</span>
            </div>
            <h1 class="auth-card-title">Sign In to Institutional Console</h1>
            <p class="auth-card-desc">
              Accredited access for Statistical Analysts (MoSPI / RBI) and System Administrators (NSO / DGCA).
            </p>
          </div>

          <div id="login-error" class="auth-error-alert">Invalid email or password</div>

          <form id="form-login" onsubmit="handleLoginSubmit(event)">
            <div class="auth-form-field">
              <label class="auth-label" for="login-email">Official Institutional Email</label>
              <input type="email" id="login-email" class="auth-input" placeholder="e.g. analyst@mospi.gov.in" required autocomplete="username">
            </div>

            <div class="auth-form-field">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <label class="auth-label" for="login-password" style="margin-bottom:0;">Password</label>
                <a href="javascript:void(0)" onclick="togglePasswordVisibility('login-password')"
                  style="font-size:11px; color:var(--palette-azure); text-decoration:none;">Show Password</a>
              </div>
              <input type="password" id="login-password" class="auth-input" placeholder="••••••••••••" required autocomplete="current-password">
            </div>

            <button type="submit" id="btn-login-submit" class="auth-btn-primary">
              <span>Sign In to Dashboard</span>
              <span>→</span>
            </button>
          </form>

          <!-- Admin MFA Prompt (Displayed if user has enrolled MFA authenticator) -->
          <div id="mfa-prompt-container" style="display:none; margin-top:20px; padding:18px; border-radius:10px; background:var(--color-accent-subtle); border:1px solid var(--color-line);">
            <div style="font-weight:700; color:var(--color-ink); margin-bottom:6px; display:flex; align-items:center; gap:8px;">
              <span>🛡️</span>
              <span style="font-size:14px;">Administrator MFA Verification</span>
            </div>
            <p style="font-size:12px; color:var(--color-muted); line-height:1.5; margin-bottom:12px;">
              Elevated credentials require two-factor authentication. Please enter the 6-digit code from your authenticator app:
            </p>
            <div style="display:flex; gap:10px; align-items:center;">
              <input type="text" id="mfa-code" class="auth-input" placeholder="123456" maxlength="6" style="letter-spacing:6px; font-weight:700; text-align:center; font-size:18px; max-width:160px;">
              <button type="button" class="btn btn-accent" onclick="handleMfaVerify()">Verify &amp; Enter</button>
            </div>
            <div id="mfa-error" style="display:none; color:#B91C1C; font-size:12px; font-weight:600; margin-top:8px;">Invalid authenticator code.</div>
          </div>

          <div class="auth-footer-nav" style="margin-top:24px;">
            Need institutional clearance? Contact your NSO / MoSPI System Administrator for invitation.
          </div>
        </div>
      </div>
    </section>

    """
        html = html[:login_section_old.start()] + new_login_section + html[login_section_old.end() - len(login_section_old.group(2)):]

    # 5. Remove role switcher from Register page
    html = re.sub(r'<div class="auth-role-group">.*?</div>\s*</div>\s*(?=<div class="auth-form-field">)', '', html, flags=re.DOTALL)

    # 6. Replace Admin page with Tabbed interface (Scraper Control, Compliance, User Management)
    admin_section_old = re.search(r'(<section class="page-view" id="page-admin">.*?)(<section class="page-view" id="page-restricted">)', html, re.DOTALL)
    if admin_section_old:
        new_admin_section = """<section class="page-view" id="page-admin">
      <div class="plain-page-container">

        <!-- Admin View Header -->
        <div class="page-header" style="margin-bottom:20px;">
          <div class="page-header-badge">
            <span>⚡</span>
            <span>RESTRICTED ACCESS · SYSTEM ADMINISTRATOR ONLY</span>
          </div>
          <h1 class="page-header-title">Administrative Orchestrator &amp; Compliance Console</h1>
          <p class="page-header-desc">
            Direct operational control over airline web scrapers, compliance auditing, rate limits, and institutional user access.
          </p>
        </div>

        <!-- Admin Tabs Header -->
        <div class="admin-tabs" style="display:flex; gap:12px; margin-bottom:24px; border-bottom:1px solid var(--color-line); padding-bottom:12px;">
          <button type="button" class="admin-tab-btn active" id="tab-btn-scrapers" onclick="switchAdminTab('scrapers')">
            ⚡ Scraper Control
          </button>
          <button type="button" class="admin-tab-btn" id="tab-btn-compliance" onclick="switchAdminTab('compliance')">
            📋 Data Sources &amp; Compliance
          </button>
          <button type="button" class="admin-tab-btn" id="tab-btn-users" onclick="switchAdminTab('users')">
            👥 User Management
          </button>
        </div>

        <!-- TAB 1: SCRAPER CONTROL -->
        <div class="admin-tab-pane active" id="admin-tab-scrapers">
          <!-- 4 System KPI Metric Cards -->
          <div class="stat-cards-grid" style="margin-bottom:24px;">
            <div class="stat-card">
              <div class="stat-card-label">Active Scrapers</div>
              <div class="stat-card-value" style="color:var(--status-emerald);">3 Sources</div>
              <div class="stat-card-desc">IndiGo · Air India · MakeMyTrip</div>
            </div>
            <div class="stat-card">
              <div class="stat-card-label">Database Fare Quotes</div>
              <div class="stat-card-value" id="admin-stat-quotes">Loading...</div>
              <div class="stat-card-desc">public.fare_quotes (RLS Protected)</div>
            </div>
            <div class="stat-card">
              <div class="stat-card-label">MoSPI Official CPI</div>
              <div class="stat-card-value" id="admin-stat-cpi">1,880 Rows</div>
              <div class="stat-card-desc">public.cpi_official (Base 2024=100)</div>
            </div>
            <div class="stat-card">
              <div class="stat-card-label">FastAPI Service</div>
              <div class="stat-card-value" style="color:var(--color-accent);">v1.0 Ready</div>
              <div class="stat-card-desc">JWT Auth &amp; Rate-Limiting</div>
            </div>
          </div>

          <div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px; margin-bottom:24px;">
            <!-- Trigger Scraper Controller -->
            <div class="card">
              <div class="card-header">
                <div>
                  <h3 class="card-title">Live Scraper Trigger</h3>
                  <p class="card-subtitle">Calls FastAPI POST /v1/admin/trigger-scrape with Supabase Bearer token</p>
                </div>
                <span class="badge badge-live">Admin Protected</span>
              </div>
              <div class="card-body" style="display:flex; flex-direction:column; gap:14px;">
                <div>
                  <label style="font-size:12px; font-weight:700; color:var(--color-ink); display:block; margin-bottom:8px;">Target Sources:</label>
                  <div style="display:flex; gap:16px;">
                    <label style="display:flex; align-items:center; gap:6px; font-size:13px; cursor:pointer;">
                      <input type="checkbox" id="scrape-src-indigo" value="indigo" checked> IndiGo
                    </label>
                    <label style="display:flex; align-items:center; gap:6px; font-size:13px; cursor:pointer;">
                      <input type="checkbox" id="scrape-src-airindia" value="air_india" checked> Air India
                    </label>
                    <label style="display:flex; align-items:center; gap:6px; font-size:13px; cursor:pointer;">
                      <input type="checkbox" id="scrape-src-makemytrip" value="makemytrip" checked> MakeMyTrip
                    </label>
                  </div>
                </div>
                <div style="display:flex; gap:10px;">
                  <button class="btn btn-sm btn-accent" style="flex:1;" onclick="triggerLiveScrape()">
                    ▶ Dispatch Collection Cycle
                  </button>
                  <button class="btn btn-sm btn-secondary" onclick="loadAdminScrapeLogs()">
                    🔄 Refresh Logs
                  </button>
                </div>
                <div id="trigger-scrape-status" style="font-size:12px; color:var(--color-muted); line-height:1.4;">
                  Ready to trigger collection. Requests are queued in background workers with anti-bot evasion.
                </div>
              </div>
            </div>

            <!-- Terminal Console -->
            <div class="card" style="display:flex; flex-direction:column;">
              <div class="card-header" style="background:#0D1524; border-bottom:1px solid #1E2D4A;">
                <div style="display:flex; align-items:center; gap:8px;">
                  <span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:#E26959;"></span>
                  <span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:#F3C97E;"></span>
                  <span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:#3EB39D;"></span>
                  <span style="font-family:var(--font-data); font-size:12px; color:#A3B3CC; font-weight:600; margin-left:6px;">
                    admin@airiva-nso: ~/scrapers/orchestrator
                  </span>
                </div>
                <span class="badge badge-neutral" style="background:#16233A; color:#8FA1BD; border:1px solid #253752;">LIVE TTY</span>
              </div>
              <div class="card-body" style="padding:0; flex:1;">
                <div class="terminal-console" id="admin-terminal-output" style="height:220px; margin:0; border-radius:0; border:none;">[SYSTEM] Airiva Admin TTY initialized.
[AUTH] Authenticated via Supabase RLS. Ready for dispatch.</div>
              </div>
            </div>
          </div>

          <!-- Live Scrape Log Table -->
          <div class="card">
            <div class="card-header">
              <div>
                <h3 class="card-title">Recent Scrape Run Logs (GET /v1/admin/scrape-log)</h3>
                <p class="card-subtitle">Detailed audit records of all collection attempts from public.scrape_log</p>
              </div>
            </div>
            <div class="card-body" style="padding:0;">
              <div class="table-container" style="max-height:280px; overflow-y:auto;">
                <table class="data-table" style="width:100%; border-collapse:collapse;">
                  <thead>
                    <tr>
                      <th style="padding:10px 14px; text-align:left; font-size:11px;">ID</th>
                      <th style="padding:10px 14px; text-align:left; font-size:11px;">Source</th>
                      <th style="padding:10px 14px; text-align:left; font-size:11px;">Route</th>
                      <th style="padding:10px 14px; text-align:left; font-size:11px;">Window</th>
                      <th style="padding:10px 14px; text-align:left; font-size:11px;">Status</th>
                      <th style="padding:10px 14px; text-align:left; font-size:11px;">Quotes</th>
                      <th style="padding:10px 14px; text-align:left; font-size:11px;">Error / Detail</th>
                      <th style="padding:10px 14px; text-align:left; font-size:11px;">Timestamp</th>
                    </tr>
                  </thead>
                  <tbody id="admin-scrapelog-tbody">
                    <tr><td colspan="8" style="padding:16px; text-align:center; color:var(--color-muted);">Click "Refresh Logs" to query /v1/admin/scrape-log...</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>

        <!-- TAB 2: DATA SOURCES & COMPLIANCE -->
        <div class="admin-tab-pane" id="admin-tab-compliance">
          <div class="card" style="margin-bottom:24px;">
            <div class="card-header">
              <div>
                <h3 class="card-title">Monitored Airlines &amp; Online Travel Agencies</h3>
                <p class="card-subtitle">Active carrier ingestion configurations, rate limits and robots.txt compliance status</p>
              </div>
              <span class="badge badge-live">Active Compliance</span>
            </div>
            <div class="card-body" style="padding:0;">
              <table class="data-table" style="width:100%; border-collapse:collapse;">
                <thead>
                  <tr>
                    <th style="padding:10px 14px; text-align:left; font-size:11px;">Source Identifier</th>
                    <th style="padding:10px 14px; text-align:left; font-size:11px;">Type</th>
                    <th style="padding:10px 14px; text-align:left; font-size:11px;">Endpoint Base</th>
                    <th style="padding:10px 14px; text-align:left; font-size:11px;">Robots.txt Policy</th>
                    <th style="padding:10px 14px; text-align:left; font-size:11px;">Rate Limit / Delay</th>
                    <th style="padding:10px 14px; text-align:left; font-size:11px;">Ingestion Status</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td style="padding:10px 14px; font-weight:700;">indigo</td>
                    <td style="padding:10px 14px;">Direct Carrier</td>
                    <td style="padding:10px 14px;"><code>https://www.goindigo.in</code></td>
                    <td style="padding:10px 14px;"><span class="badge badge-live">Verified Allowed</span></td>
                    <td style="padding:10px 14px;">2.0s jitter / random delay</td>
                    <td style="padding:10px 14px;"><span class="badge badge-live">Operational</span></td>
                  </tr>
                  <tr>
                    <td style="padding:10px 14px; font-weight:700;">air_india</td>
                    <td style="padding:10px 14px;">Direct Carrier</td>
                    <td style="padding:10px 14px;"><code>https://www.airindia.com</code></td>
                    <td style="padding:10px 14px;"><span class="badge badge-live">Verified Allowed</span></td>
                    <td style="padding:10px 14px;">2.5s jitter / random delay</td>
                    <td style="padding:10px 14px;"><span class="badge badge-live">Operational</span></td>
                  </tr>
                  <tr>
                    <td style="padding:10px 14px; font-weight:700;">makemytrip</td>
                    <td style="padding:10px 14px;">Online Travel Agency</td>
                    <td style="padding:10px 14px;"><code>https://www.makemytrip.com</code></td>
                    <td style="padding:10px 14px;"><span class="badge badge-live">Verified Allowed</span></td>
                    <td style="padding:10px 14px;">3.0s jitter / random delay</td>
                    <td style="padding:10px 14px;"><span class="badge badge-live">Operational</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Regulatory & Econometric Foundations -->
          <div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px;">
            <div class="card">
              <div class="card-header">
                <div>
                  <h3 class="card-title">DGCA Table 4.3 Corridor Weight Matrix</h3>
                  <p class="card-subtitle">Official passenger volume weights applied in Törnqvist aggregator</p>
                </div>
              </div>
              <div class="card-body" style="padding:0;">
                <table class="data-table" style="width:100%; border-collapse:collapse;">
                  <thead>
                    <tr>
                      <th style="padding:10px 14px; text-align:left; font-size:11px;">Corridor</th>
                      <th style="padding:10px 14px; text-align:left; font-size:11px;">City Pair</th>
                      <th style="padding:10px 14px; text-align:left; font-size:11px;">DGCA Annual Weight</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr><td style="padding:10px 14px; font-weight:700;">DEL-BOM</td><td style="padding:10px 14px;">Delhi ↔ Mumbai</td><td style="padding:10px 14px; font-weight:700; color:var(--color-accent);">37.0% (0.370)</td></tr>
                    <tr><td style="padding:10px 14px; font-weight:700;">DEL-BLR</td><td style="padding:10px 14px;">Delhi ↔ Bengaluru</td><td style="padding:10px 14px; font-weight:700; color:var(--color-accent);">35.5% (0.355)</td></tr>
                    <tr><td style="padding:10px 14px; font-weight:700;">BOM-BLR</td><td style="padding:10px 14px;">Mumbai ↔ Bengaluru</td><td style="padding:10px 14px; font-weight:700; color:var(--color-accent);">27.5% (0.275)</td></tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div class="card">
              <div class="card-header">
                <div>
                  <h3 class="card-title">Security &amp; RLS Protection Model</h3>
                  <p class="card-subtitle">Architectural verification of zero-trust public/analyst/admin boundaries</p>
                </div>
              </div>
              <div class="card-body" style="font-size:13px; color:var(--color-muted); line-height:1.6; display:flex; flex-direction:column; gap:8px;">
                <div>🔒 <strong>Row Level Security (RLS):</strong> Enforced at Postgres engine level. Browser client uses <code>SUPABASE_ANON_KEY</code> only.</div>
                <div>🛡️ <strong>Zero Client Write:</strong> Direct table inserts/updates/deletes are strictly revoked from <code>anon</code> and <code>authenticated</code> roles.</div>
                <div>⚡ <strong>Service-Role Isolation:</strong> Pipeline crawler and data ingestors use service-role key on trusted Python server environments only.</div>
                <div>🎫 <strong>Cryptographic Tokens:</strong> FastAPI backend validates JWT signatures via Supabase Auth Admin.</div>
              </div>
            </div>
          </div>
        </div>

        <!-- TAB 3: USER MANAGEMENT -->
        <div class="admin-tab-pane" id="admin-tab-users">
          <div style="display:grid; grid-template-columns: 1fr 2fr; gap:20px; margin-bottom:24px;">
            <!-- Invite User Form -->
            <div class="card">
              <div class="card-header">
                <div>
                  <h3 class="card-title">Invite New User</h3>
                  <p class="card-subtitle">Calls POST /v1/admin/invite-user via FastAPI &amp; Supabase Auth Admin</p>
                </div>
              </div>
              <div class="card-body">
                <form id="form-invite-user" onsubmit="handleInviteUserSubmit(event)" style="display:flex; flex-direction:column; gap:14px;">
                  <div class="auth-form-field">
                    <label class="auth-label" for="invite-email">User Official Email</label>
                    <input type="email" id="invite-email" class="auth-input" placeholder="colleague@mospi.gov.in" required>
                  </div>
                  <div class="auth-form-field">
                    <label class="auth-label" for="invite-role">Assigned System Role</label>
                    <select id="invite-role" class="form-select" style="width:100%; padding:10px; border-radius:8px; border:1px solid var(--color-line); font-size:13px;">
                      <option value="analyst" selected>Analyst / Auditor (Microdata, Quotes, Heatmaps)</option>
                      <option value="admin">Administrator (Scrapers, Pipeline, Users)</option>
                    </select>
                  </div>
                  <button type="submit" class="btn btn-accent" id="btn-invite-submit">
                    ✉️ Send Official Invitation
                  </button>
                  <div id="invite-status" style="font-size:12px; display:none; padding:8px; border-radius:6px;"></div>
                </form>
              </div>
            </div>

            <!-- Profiles Table -->
            <div class="card">
              <div class="card-header">
                <div>
                  <h3 class="card-title">Accredited Profiles (public.profiles)</h3>
                  <p class="card-subtitle">Registered system accounts read directly from Supabase via Admin RLS</p>
                </div>
                <button class="btn btn-sm btn-secondary" onclick="loadAdminProfiles()">🔄 Refresh</button>
              </div>
              <div class="card-body" style="padding:0;">
                <div class="table-container" style="max-height:340px; overflow-y:auto;">
                  <table class="data-table" style="width:100%; border-collapse:collapse;">
                    <thead>
                      <tr>
                        <th style="padding:10px 14px; text-align:left; font-size:11px;">User ID</th>
                        <th style="padding:10px 14px; text-align:left; font-size:11px;">Email</th>
                        <th style="padding:10px 14px; text-align:left; font-size:11px;">Role</th>
                        <th style="padding:10px 14px; text-align:left; font-size:11px;">Registered</th>
                      </tr>
                    </thead>
                    <tbody id="admin-profiles-tbody">
                      <tr><td colspan="4" style="padding:16px; text-align:center; color:var(--color-muted);">Loading profiles...</td></tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>

      </div>
    </section>

    """
        html = html[:admin_section_old.start()] + new_admin_section + html[admin_section_old.end() - len(admin_section_old.group(2)):]

    # 7. JavaScript Application Logic overhaul
    # Extract the <script> block and replace with hardened Supabase-integrated code
    script_match = re.search(r'<script>(.*?)</script>', html, re.DOTALL)
    if not script_match:
        print("Error: Could not find <script> tag in index.html!")
        sys.exit(1)

    with open("scripts/dashboard_script.js", "r", encoding="utf-8") as f:
        new_script_content = f.read()

    html = html[:script_match.start()] + f"<script>\n{new_script_content}\n  </script>" + html[script_match.end():]

    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print("Airiva/dashboard/index.html updated successfully!")

if __name__ == "__main__":
    update_dashboard()
