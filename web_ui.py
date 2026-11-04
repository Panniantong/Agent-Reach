#!/usr/bin/env python3
"""
Agent Reach Web Explorer & Auto-Saver.
Lightweight, standalone web interface with zero external dependencies.
"""

import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, "/Agent-Reach")
from lead_saver import get_leads_by_search_id, get_search_history, run_lead_search

PORT = 7860

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Agent Reach - Lead Finder & Auto-Saver</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --border: #334155;
      --accent: #38bdf8;
      --accent-hover: #0ea5e9;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --success: #10b981;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
    body { background-color: var(--bg); color: var(--text); min-height: 100vh; display: flex; flex-direction: column; }
    header {
      background-color: var(--card-bg);
      border-bottom: 1px solid var(--border);
      padding: 1rem 2rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .logo { display: flex; align-items: center; gap: 0.75rem; font-size: 1.25rem; font-weight: 700; color: var(--text); }
    .badge {
      font-size: 0.75rem;
      padding: 0.2rem 0.6rem;
      border-radius: 9999px;
      background: rgba(56, 189, 248, 0.15);
      color: var(--accent);
      border: 1px solid rgba(56, 189, 248, 0.3);
    }
    .main-container {
      display: grid;
      grid-template-columns: 320px 1fr;
      flex: 1;
      height: calc(100vh - 65px);
    }
    .sidebar {
      background-color: #131c31;
      border-right: 1px solid var(--border);
      padding: 1.25rem;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }
    .sidebar-title { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); font-weight: 600; }
    .history-list { display: flex; flex-direction: column; gap: 0.5rem; }
    .history-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      padding: 0.85rem;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .history-card:hover, .history-card.active { border-color: var(--accent); background: #26354d; }
    .history-query { font-weight: 600; font-size: 0.95rem; margin-bottom: 0.25rem; }
    .history-meta { font-size: 0.78rem; color: var(--text-muted); display: flex; justify-content: space-between; }
    .content-area {
      padding: 1.5rem 2rem;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 1.5rem;
    }
    .search-panel {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.25rem 1.5rem;
      display: grid;
      grid-template-columns: 2fr 1.5fr 1fr 90px auto;
      gap: 1rem;
      align-items: end;
    }
    .form-group { display: flex; flex-direction: column; gap: 0.35rem; }
    .form-group label { font-size: 0.8rem; font-weight: 600; color: var(--text-muted); }
    input, select {
      background: #0f172a;
      border: 1px solid var(--border);
      color: var(--text);
      padding: 0.65rem 0.85rem;
      border-radius: 6px;
      font-size: 0.9rem;
      outline: none;
      transition: border-color 0.15s;
    }
    input:focus, select:focus { border-color: var(--accent); }
    button.btn-search {
      background: var(--accent);
      color: #0f172a;
      border: none;
      font-weight: 600;
      padding: 0.65rem 1.25rem;
      border-radius: 6px;
      cursor: pointer;
      transition: background-color 0.15s;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    button.btn-search:hover { background: var(--accent-hover); }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    .table-container {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }
    .table-header {
      padding: 1rem 1.5rem;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .table-title { font-size: 1.1rem; font-weight: 600; }
    .table-actions { display: flex; gap: 0.75rem; }
    .btn-export {
      background: #253349;
      border: 1px solid var(--border);
      color: var(--text);
      font-size: 0.82rem;
      font-weight: 500;
      padding: 0.4rem 0.8rem;
      border-radius: 6px;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
    }
    .btn-export:hover { border-color: var(--accent); color: var(--accent); }
    table { width: 100%; border-collapse: collapse; text-align: left; font-size: 0.88rem; }
    th {
      background: #172033;
      color: var(--text-muted);
      font-weight: 600;
      padding: 0.75rem 1rem;
      border-bottom: 1px solid var(--border);
      text-transform: uppercase;
      font-size: 0.72rem;
      letter-spacing: 0.05em;
    }
    td { padding: 0.85rem 1rem; border-bottom: 1px solid rgba(51, 65, 85, 0.4); vertical-align: middle; }
    tr:hover td { background: rgba(56, 189, 248, 0.03); }
    .contact-cell { font-family: monospace; font-size: 0.82rem; color: #38bdf8; }
    .email-cell { color: #a78bfa; font-size: 0.82rem; }
    .empty-state { text-align: center; padding: 4rem 1rem; color: var(--text-muted); }
    .spinner {
      border: 2px solid rgba(255, 255, 255, 0.3);
      border-radius: 50%;
      border-top: 2px solid #0f172a;
      width: 14px;
      height: 14px;
      animation: spin 0.8s linear infinite;
    }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <header>
    <div class="logo">
      <span>🚀</span>
      <span>Agent Reach Lead Explorer</span>
      <span class="badge">Auto-Saving Active</span>
    </div>
    <div style="font-size: 0.85rem; color: var(--text-muted)">
      Backend: Exa Semantic Indexer + CloakBrowser
    </div>
  </header>

  <div class="main-container">
    <div class="sidebar">
      <div class="sidebar-title">Saved Search History</div>
      <div id="historyList" class="history-list">
        <div style="color: var(--text-muted); font-size: 0.85rem;">Loading history...</div>
      </div>
    </div>

    <div class="content-area">
      <div class="search-panel">
        <div class="form-group">
          <label>Query / Niche</label>
          <input type="text" id="queryInput" placeholder="e.g. Cake sellers, Dentists, CTOs" value="cake sellers">
        </div>
        <div class="form-group">
          <label>Location</label>
          <input type="text" id="locationInput" placeholder="e.g. Kolkata, Mumbai, Miami" value="Kolkata">
        </div>
        <div class="form-group">
          <label>Platform</label>
          <select id="platformSelect">
            <option value="linkedin">LinkedIn Profiles</option>
            <option value="web">All Public Web</option>
            <option value="twitter">Twitter / X</option>
            <option value="reddit">Reddit</option>
          </select>
        </div>
        <div class="form-group">
          <label>Limit</label>
          <select id="limitSelect">
            <option value="5">5</option>
            <option value="10" selected>10</option>
            <option value="20">20</option>
          </select>
        </div>
        <button id="searchBtn" class="btn-search" onclick="doSearch()">
          <span id="btnText">Search & Save</span>
        </button>
      </div>

      <div class="table-container">
        <div class="table-header">
          <div class="table-title" id="resultsTitle">Leads Results</div>
          <div class="table-actions" id="exportActions" style="display: none;">
            <a id="btnCsv" href="#" class="btn-export" download>📥 Export CSV</a>
            <a id="btnJson" href="#" class="btn-export" download>📥 Export JSON</a>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th style="width: 40px;">#</th>
              <th>Name</th>
              <th>Business / Brand</th>
              <th>Role / Headline</th>
              <th>Phone / WhatsApp</th>
              <th>Email</th>
              <th>Location</th>
              <th>Profile Link</th>
            </tr>
          </thead>
          <tbody id="leadsTableBody">
            <tr>
              <td colspan="8" class="empty-state">Select a saved search from the history or run a new search above.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    let currentSearchId = null;

    async function loadHistory() {
      try {
        const res = await fetch('/api/history');
        const data = await res.json();
        const container = document.getElementById('historyList');
        if (!data || data.length === 0) {
          container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem;">No saved searches yet.</div>';
          return;
        }
        container.innerHTML = data.map(item => `
          <div class="history-card ${currentSearchId === item.id ? 'active' : ''}" onclick="selectSearch(${item.id})">
            <div class="history-query">${escapeHtml(item.query)}</div>
            <div class="history-meta">
              <span>📍 ${escapeHtml(item.location || 'Any')}</span>
              <span>👥 ${item.lead_count} leads</span>
            </div>
            <div style="font-size: 0.72rem; color: #64748b; margin-top: 0.25rem;">
              ${item.created_at}
            </div>
          </div>
        `).join('');

        if (currentSearchId === null && data.length > 0) {
          selectSearch(data[0].id);
        }
      } catch (err) {
        console.error('Failed to load history:', err);
      }
    }

    async function selectSearch(id) {
      currentSearchId = id;
      loadHistory();
      try {
        const res = await fetch('/api/search/' + id);
        const data = await res.json();
        renderLeads(data.leads, data.search);
      } catch (err) {
        alert('Failed to load search leads');
      }
    }

    function renderLeads(leads, searchMeta) {
      const tbody = document.getElementById('leadsTableBody');
      const title = document.getElementById('resultsTitle');
      const exportActions = document.getElementById('exportActions');
      const btnCsv = document.getElementById('btnCsv');
      const btnJson = document.getElementById('btnJson');

      if (searchMeta) {
        title.innerText = `${searchMeta.query} in ${searchMeta.location || 'Any location'} (${leads.length} leads)`;
      }

      if (currentSearchId) {
        exportActions.style.display = 'flex';
        btnCsv.href = '/download/csv/' + currentSearchId;
        btnJson.href = '/download/json/' + currentSearchId;
      }

      if (!leads || leads.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No leads found for this query.</td></tr>';
        return;
      }

      tbody.innerHTML = leads.map((l, idx) => `
        <tr>
          <td>${idx + 1}</td>
          <td style="font-weight: 600;">${escapeHtml(l.name || 'N/A')}</td>
          <td>${escapeHtml(l.business || 'N/A')}</td>
          <td style="color: var(--text-muted);">${escapeHtml(l.role || 'N/A')}</td>
          <td class="contact-cell">${escapeHtml(l.phone || 'Not listed')}</td>
          <td class="email-cell">${escapeHtml(l.email || 'Not listed')}</td>
          <td>${escapeHtml(l.location || 'N/A')}</td>
          <td>
            ${l.url ? `<a href="${escapeHtml(l.url)}" target="_blank" style="color: var(--accent); text-decoration: none;">View ↗</a>` : 'N/A'}
          </td>
        </tr>
      `).join('');
    }

    async function doSearch() {
      const query = document.getElementById('queryInput').value.trim();
      const location = document.getElementById('locationInput').value.trim();
      const platform = document.getElementById('platformSelect').value;
      const limit = document.getElementById('limitSelect').value;

      if (!query) {
        alert('Please enter a search query');
        return;
      }

      const btn = document.getElementById('searchBtn');
      const btnText = document.getElementById('btnText');
      btn.disabled = true;
      btnText.innerHTML = '<span class="spinner"></span> Searching...';

      try {
        const res = await fetch('/api/search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query, location, platform, limit })
        });
        const data = await res.json();
        if (!data.ok) {
          alert('Search Error: ' + (data.error || 'Failed to fetch'));
        } else {
          await loadHistory();
          renderLeads(data.leads, { query, location });
        }
      } catch (err) {
        alert('Error connecting to backend: ' + err.message);
      } finally {
        btn.disabled = false;
        btnText.innerText = 'Search & Save';
      }
    }

    function escapeHtml(text) {
      if (!text) return '';
      return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    window.onload = loadHistory;
  </script>
</body>
</html>
"""

class RequestHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
            return

        if path == "/api/history":
            history = get_search_history()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(history).encode("utf-8"))
            return

        if path.startswith("/api/search/"):
            try:
                search_id = int(path.split("/")[-1])
                leads = get_leads_by_search_id(search_id)
                history = get_search_history()
                search_meta = next((s for s in history if s['id'] == search_id), None)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "leads": leads, "search": search_meta}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))
            return

        if path.startswith("/download/csv/"):
            try:
                search_id = int(path.split("/")[-1])
                history = get_search_history()
                meta = next((s for s in history if s['id'] == search_id), None)
                if meta and os.path.exists(meta.get("csv_path", "")):
                    with open(meta["csv_path"], "rb") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/csv; charset=utf-8")
                    self.send_header("Content-Disposition", f"attachment; filename=\"{os.path.basename(meta['csv_path'])}\"")
                    self.end_headers()
                    self.wfile.write(data)
                    return
            except Exception:
                pass
            self.send_response(404)
            self.end_headers()
            return

        if path.startswith("/download/json/"):
            try:
                search_id = int(path.split("/")[-1])
                history = get_search_history()
                meta = next((s for s in history if s['id'] == search_id), None)
                if meta and os.path.exists(meta.get("json_path", "")):
                    with open(meta["json_path"], "rb") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Disposition", f"attachment; filename=\"{os.path.basename(meta['json_path'])}\"")
                    self.end_headers()
                    self.wfile.write(data)
                    return
            except Exception:
                pass
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/search":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                payload = json.loads(body)
                query = payload.get("query", "").strip()
                location = payload.get("location", "").strip()
                platform = payload.get("platform", "linkedin")
                limit = int(payload.get("limit", 10))

                result = run_lead_search(
                    query=query,
                    location=location,
                    platform=platform,
                    limit=limit
                )

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        # Silent logger to prevent terminal clutter
        return

def run_server():
    server_address = ("0.0.0.0", PORT)
    httpd = HTTPServer(server_address, RequestHandler)
    print(f"[*] Agent Reach Web UI running at http://localhost:{PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
