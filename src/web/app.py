"""
src/web/app.py

Text2OfficeProcessor Web UI — a minimal FastAPI application that exposes the conversion
pipeline through a browser interface.

Endpoints:
  GET  /           — Single-page HTML UI
  GET  /health     — JSON health check
  POST /convert    — Convert an uploaded file; returns the output file

Start with:
  text2officeprocessor serve [--host 0.0.0.0] [--port 8000]
  python -m uvicorn src.web.app:create_app --factory --reload
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False

try:
    import python_multipart  # type: ignore  # noqa: F401
    _MULTIPART_AVAILABLE = True
except ImportError:
    _MULTIPART_AVAILABLE = False

_HTML = r"""\
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Text2OfficeProcessor — Document Converter</title>
  <style>
    /* ── Reset & tokens ───────────────────────────────────────────────────── */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
      --bg:        #f1f5f9;
      --surface:   #ffffff;
      --surface2:  #f8fafc;
      --border:    #e2e8f0;
      --text:      #0f172a;
      --muted:     #64748b;
      --accent:    #6366f1;
      --accent-h:  #4f46e5;
      --accent-lt: #eef2ff;
      --teal:      #0ea5e9;
      --teal-h:    #0284c7;
      --green:     #16a34a;
      --red:       #dc2626;
      --amber:     #d97706;
      --radius:    10px;
      --shadow:    0 4px 24px rgba(0,0,0,.08);
      --font:      -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    [data-theme="dark"] {
      --bg:        #0f172a;
      --surface:   #1e293b;
      --surface2:  #162032;
      --border:    #334155;
      --text:      #f1f5f9;
      --muted:     #94a3b8;
      --accent-lt: #1e1b4b;
      --shadow:    0 4px 24px rgba(0,0,0,.4);
    }

    /* ── Base ─────────────────────────────────────────────────────────────── */
    html { scroll-behavior: smooth; }
    body {
      font-family: var(--font);
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      transition: background .3s, color .3s;
    }

    /* ── Top nav ──────────────────────────────────────────────────────────── */
    nav {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: .875rem 2rem;
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      position: sticky;
      top: 0;
      z-index: 100;
      box-shadow: 0 1px 8px rgba(0,0,0,.06);
    }
    .nav-brand {
      display: flex;
      align-items: center;
      gap: .6rem;
      font-weight: 800;
      font-size: 1.2rem;
      letter-spacing: -.02em;
      color: var(--text);
      text-decoration: none;
    }
    .nav-brand .logo-dot { color: var(--accent); }
    .nav-right { display: flex; align-items: center; gap: 1rem; }
    .nav-badge {
      font-size: .7rem;
      font-weight: 600;
      padding: .2rem .6rem;
      background: var(--accent-lt);
      color: var(--accent);
      border-radius: 999px;
      border: 1px solid var(--accent);
    }
    .theme-btn {
      background: none;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: .3rem .6rem;
      cursor: pointer;
      font-size: 1rem;
      color: var(--muted);
      transition: border-color .2s, color .2s;
      line-height: 1;
    }
    .theme-btn:hover { border-color: var(--accent); color: var(--accent); }

    /* ── Layout ───────────────────────────────────────────────────────────── */
    .page {
      max-width: 1120px;
      margin: 0 auto;
      padding: 2rem 1.5rem 4rem;
      display: grid;
      grid-template-columns: 1fr 340px;
      gap: 2rem;
      align-items: start;
    }
    @media (max-width: 820px) {
      .page { grid-template-columns: 1fr; }
      .sidebar { order: -1; }
    }

    /* ── Card ─────────────────────────────────────────────────────────────── */
    .card {
      background: var(--surface);
      border-radius: var(--radius);
      border: 1px solid var(--border);
      box-shadow: var(--shadow);
      padding: 1.75rem;
    }
    .card-title {
      font-size: 1rem;
      font-weight: 700;
      margin-bottom: 1.25rem;
      color: var(--text);
      display: flex;
      align-items: center;
      gap: .5rem;
    }
    .card-title .icon { font-size: 1.1rem; }

    /* ── Tab strip (File / Paste) ─────────────────────────────────────────── */
    .tabs {
      display: flex;
      gap: .25rem;
      margin-bottom: 1.25rem;
      background: var(--surface2);
      padding: .25rem;
      border-radius: 8px;
      border: 1px solid var(--border);
    }
    .tab-btn {
      flex: 1;
      padding: .45rem .75rem;
      border: none;
      background: none;
      border-radius: 6px;
      font-size: .85rem;
      font-weight: 600;
      color: var(--muted);
      cursor: pointer;
      transition: background .2s, color .2s;
    }
    .tab-btn.active {
      background: var(--surface);
      color: var(--accent);
      box-shadow: 0 1px 4px rgba(0,0,0,.08);
    }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }

    /* ── Drop zone ────────────────────────────────────────────────────────── */
    .drop-zone {
      border: 2px dashed var(--border);
      border-radius: 8px;
      padding: 2rem 1rem;
      text-align: center;
      cursor: pointer;
      transition: border-color .2s, background .2s;
      background: var(--surface2);
    }
    .drop-zone:hover, .drop-zone.drag-over {
      border-color: var(--accent);
      background: var(--accent-lt);
    }
    .drop-zone svg { width: 36px; height: 36px; color: var(--muted); margin-bottom: .5rem; }
    .drop-zone .dz-hint { font-size: .85rem; color: var(--muted); }
    .drop-zone strong { color: var(--accent); }
    #file-chip {
      display: none;
      margin-top: .75rem;
      background: var(--accent-lt);
      border: 1px solid var(--accent);
      border-radius: 6px;
      padding: .4rem .75rem;
      font-size: .82rem;
      color: var(--accent);
      font-weight: 600;
    }

    /* ── Paste panel ─────────────────────────────────────────────────────── */
    #paste-input {
      width: 100%;
      min-height: 180px;
      resize: vertical;
      padding: .75rem;
      background: var(--surface2);
      border: 1px solid var(--border);
      border-radius: 8px;
      font-family: "JetBrains Mono", "Fira Code", "Cascadia Code", monospace;
      font-size: .82rem;
      color: var(--text);
      line-height: 1.6;
      transition: border-color .2s;
    }
    #paste-input:focus { outline: 2px solid var(--accent); border-color: var(--accent); }
    .paste-hint {
      font-size: .75rem;
      color: var(--muted);
      margin-top: .4rem;
    }

    /* ── Format cards ────────────────────────────────────────────────────── */
    .format-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: .75rem;
      margin-bottom: 1.25rem;
    }
    .fmt-card {
      border: 2px solid var(--border);
      border-radius: 8px;
      padding: .75rem .5rem;
      text-align: center;
      cursor: pointer;
      transition: border-color .2s, background .2s, transform .1s;
      background: var(--surface2);
      user-select: none;
    }
    .fmt-card:hover { border-color: var(--accent); transform: translateY(-1px); }
    .fmt-card.selected {
      border-color: var(--accent);
      background: var(--accent-lt);
    }
    .fmt-icon { font-size: 1.6rem; display: block; margin-bottom: .3rem; }
    .fmt-label { font-size: .75rem; font-weight: 700; color: var(--text); }
    .fmt-sub   { font-size: .68rem; color: var(--muted); }

    /* ── Form fields ─────────────────────────────────────────────────────── */
    .field { margin-bottom: 1rem; }
    .field label {
      display: block;
      font-weight: 600;
      font-size: .8rem;
      margin-bottom: .35rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .04em;
    }
    .field select, .field input[type=text] {
      width: 100%;
      padding: .5rem .75rem;
      border: 1px solid var(--border);
      border-radius: 6px;
      font-size: .88rem;
      background: var(--surface2);
      color: var(--text);
      transition: border-color .2s;
    }
    .field select:focus, .field input[type=text]:focus {
      outline: 2px solid var(--accent);
      border-color: var(--accent);
    }
    #llm-model-wrap { display: none; }

    /* ── Convert button ──────────────────────────────────────────────────── */
    #convert-btn {
      width: 100%;
      padding: .8rem;
      background: var(--accent);
      color: #fff;
      border: none;
      border-radius: 8px;
      font-size: .95rem;
      font-weight: 700;
      cursor: pointer;
      transition: background .2s, transform .1s, box-shadow .2s;
      letter-spacing: .01em;
      margin-top: .25rem;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: .5rem;
    }
    #convert-btn:hover:not(:disabled) {
      background: var(--accent-h);
      box-shadow: 0 4px 12px rgba(99,102,241,.35);
      transform: translateY(-1px);
    }
    #convert-btn:disabled { background: #a5b4fc; cursor: default; transform: none; box-shadow: none; }

    /* ── Progress bar ────────────────────────────────────────────────────── */
    #progress-wrap {
      display: none;
      margin-top: 1rem;
      height: 4px;
      background: var(--border);
      border-radius: 99px;
      overflow: hidden;
    }
    #progress-bar {
      height: 100%;
      background: linear-gradient(90deg, var(--accent), var(--teal));
      border-radius: 99px;
      width: 0%;
      transition: width .4s ease;
      animation: none;
    }
    #progress-bar.indeterminate {
      width: 40% !important;
      animation: slide 1.2s ease-in-out infinite;
    }
    @keyframes slide {
      0%   { transform: translateX(-100%); }
      100% { transform: translateX(350%); }
    }

    /* ── Status message ──────────────────────────────────────────────────── */
    #status-msg {
      margin-top: .75rem;
      font-size: .85rem;
      min-height: 1.4rem;
      display: flex;
      align-items: center;
      gap: .4rem;
    }
    #status-msg.error  { color: var(--red); }
    #status-msg.success { color: var(--green); }
    #status-msg.info   { color: var(--muted); }

    /* ── Download area ───────────────────────────────────────────────────── */
    #download-area {
      display: none;
      margin-top: 1rem;
      background: var(--surface2);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1rem;
      text-align: center;
    }
    #download-area .dl-name {
      font-size: .82rem;
      color: var(--muted);
      margin-bottom: .6rem;
      word-break: break-all;
    }
    #dl-anchor {
      display: inline-flex;
      align-items: center;
      gap: .4rem;
      padding: .6rem 1.4rem;
      background: var(--teal);
      color: #fff;
      border-radius: 6px;
      text-decoration: none;
      font-weight: 700;
      font-size: .88rem;
      transition: background .2s, box-shadow .2s;
    }
    #dl-anchor:hover {
      background: var(--teal-h);
      box-shadow: 0 4px 12px rgba(14,165,233,.35);
    }

    /* ── Sidebar ─────────────────────────────────────────────────────────── */
    .sidebar { display: flex; flex-direction: column; gap: 1.25rem; }

    /* History list */
    #history-list { list-style: none; display: flex; flex-direction: column; gap: .5rem; }
    #history-list li {
      display: flex;
      align-items: center;
      gap: .6rem;
      padding: .55rem .75rem;
      background: var(--surface2);
      border: 1px solid var(--border);
      border-radius: 6px;
      font-size: .8rem;
    }
    #history-list .h-icon { font-size: 1.1rem; flex-shrink: 0; }
    #history-list .h-name { flex: 1; color: var(--text); font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    #history-list .h-time { color: var(--muted); font-size: .72rem; flex-shrink: 0; }
    #history-list a { text-decoration: none; font-size: .72rem; color: var(--teal); font-weight: 600; flex-shrink: 0; }
    #history-empty { font-size: .82rem; color: var(--muted); text-align: center; padding: .75rem 0; }

    /* Tips */
    .tip {
      display: flex;
      gap: .6rem;
      padding: .6rem .75rem;
      border-radius: 6px;
      font-size: .78rem;
      line-height: 1.5;
      background: var(--surface2);
      border: 1px solid var(--border);
    }
    .tip .tip-icon { font-size: 1rem; flex-shrink: 0; }
    .tip .tip-text { color: var(--muted); }
    .tip strong { color: var(--text); }

    /* ── Footer ──────────────────────────────────────────────────────────── */
    footer {
      text-align: center;
      font-size: .75rem;
      color: var(--muted);
      padding: 1.5rem 1rem 2rem;
      border-top: 1px solid var(--border);
    }
    footer a { color: var(--accent); text-decoration: none; }
  </style>
</head>
<body>

<!-- ── Top nav ── -->
<nav>
  <a class="nav-brand" href="/">
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
      <line x1="16" y1="13" x2="8" y2="13"/>
      <line x1="16" y1="17" x2="8" y2="17"/>
      <polyline points="10 9 9 9 8 9"/>
    </svg>
    Text<span class="logo-dot">2</span>OfficeProcessor
  </a>
  <div class="nav-right">
    <span class="nav-badge">v0.3.1</span>
    <button class="theme-btn" id="theme-toggle" title="Toggle dark mode">🌙</button>
  </div>
</nav>

<!-- ── Main layout ── -->
<div class="page">

  <!-- ── Left: converter ── -->
  <main>
    <div class="card">
      <div class="card-title"><span class="icon">⚡</span> Convert Document</div>

      <!-- Input tabs -->
      <div class="tabs">
        <button class="tab-btn active" data-tab="file">📁 Upload File</button>
        <button class="tab-btn" data-tab="paste">✏️ Paste / Type</button>
      </div>

      <!-- File tab -->
      <div class="tab-panel active" id="tab-file">
        <div class="drop-zone" id="drop-zone">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="17 8 12 3 7 8"/>
            <line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
          <p class="dz-hint">Drop your file here or <strong>click to browse</strong></p>
          <p class="dz-hint" style="margin-top:.25rem;font-size:.75rem">.md &nbsp;.txt &nbsp;.html &nbsp;.htm</p>
          <input type="file" id="file-input" accept=".md,.txt,.html,.htm" style="display:none" />
          <div id="file-chip">📄 <span id="file-chip-name"></span></div>
        </div>
      </div>

      <!-- Paste tab -->
      <div class="tab-panel" id="tab-paste">
        <textarea id="paste-input" placeholder="# My Document

## Section

Start typing your Markdown here..."></textarea>
        <p class="paste-hint">Supports Markdown, plain text, and HTML. The content will be saved as <code>pasted.md</code>.</p>
        <div class="field" style="margin-top:.75rem">
          <label>Input format</label>
          <select id="paste-fmt">
            <option value=".md">Markdown (.md)</option>
            <option value=".txt">Plain text (.txt)</option>
            <option value=".html">HTML (.html)</option>
          </select>
        </div>
      </div>

      <!-- Format selector -->
      <div style="margin-top:1.25rem">
        <div class="field" style="margin-bottom:.75rem">
          <label>Output format</label>
        </div>
        <div class="format-grid">
          <div class="fmt-card selected" data-fmt="pptx">
            <span class="fmt-icon">📊</span>
            <div class="fmt-label">PPTX</div>
            <div class="fmt-sub">PowerPoint</div>
          </div>
          <div class="fmt-card" data-fmt="docx">
            <span class="fmt-icon">📝</span>
            <div class="fmt-label">DOCX</div>
            <div class="fmt-sub">Word</div>
          </div>
          <div class="fmt-card" data-fmt="xlsx">
            <span class="fmt-icon">📈</span>
            <div class="fmt-label">XLSX</div>
            <div class="fmt-sub">Excel</div>
          </div>
        </div>
        <input type="hidden" id="selected-fmt" value="pptx" />
      </div>

      <div class="field">
        <label>Output filename (optional)</label>
        <input type="text" id="output-name" placeholder="Example: quarterly-report" />
      </div>

      <!-- LLM options (collapsible) -->
      <details style="margin-bottom:1rem">
        <summary style="cursor:pointer;font-size:.82rem;font-weight:700;color:var(--muted);
                        text-transform:uppercase;letter-spacing:.04em;user-select:none;
                        list-style:none;display:flex;align-items:center;gap:.4rem">
          <span>⚙️ LLM Options</span>
          <span style="font-weight:400;color:var(--muted)"> (optional)</span>
        </summary>
        <div style="margin-top:.75rem">
          <div class="field">
            <label>LLM provider</label>
            <select id="llm-provider">
              <option value="">Auto (default local)</option>
              <option value="none">Rule-based only (disable LLM)</option>
              <option value="ollama">Ollama (local)</option>
              <option value="vllm">vLLM (local/server)</option>
              <option value="openai">OpenAI</option>
              <option value="claude">Anthropic Claude</option>
              <option value="groq">Groq</option>
              <option value="openrouter">OpenRouter</option>
            </select>
          </div>
          <div class="field" id="llm-model-wrap">
            <label>Model name <span style="text-transform:none;font-weight:400">(leave blank for default)</span></label>
            <input type="text" id="llm-model" placeholder="e.g. mistral, gpt-4o-mini" />
          </div>
        </div>
      </details>

      <!-- Convert button -->
      <button id="convert-btn">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="23 4 23 10 17 10"/>
          <polyline points="1 20 1 14 7 14"/>
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
        </svg>
        Convert
      </button>

      <!-- Progress -->
      <div id="progress-wrap">
        <div id="progress-bar" class="indeterminate"></div>
      </div>

      <!-- Status -->
      <div id="status-msg" class="info"></div>
      <div style="margin-top:.25rem;font-size:.78rem;color:var(--muted)">
        Output is downloaded by your browser (usually your Downloads folder) unless your browser asks for a location.
      </div>

      <!-- Download -->
      <div id="download-area">
        <div class="dl-name" id="dl-filename"></div>
        <a id="dl-anchor" href="#">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          Download
        </a>
      </div>
    </div>
  </main>

  <!-- ── Sidebar ── -->
  <aside class="sidebar">

    <!-- Conversion history -->
    <div class="card">
      <div class="card-title"><span class="icon">🕒</span> Recent Conversions</div>
      <ul id="history-list">
        <li id="history-empty"><span id="history-empty-text">No conversions yet</span></li>
      </ul>
    </div>

    <!-- Quick tips -->
    <div class="card">
      <div class="card-title"><span class="icon">💡</span> Quick Tips</div>
      <div style="display:flex;flex-direction:column;gap:.5rem">
        <div class="tip">
          <span class="tip-icon">📄</span>
          <span class="tip-text"><strong>PPTX:</strong> Use <code>## Heading</code> for each slide. Bullet points map to slide body.</span>
        </div>
        <div class="tip">
          <span class="tip-icon">📝</span>
          <span class="tip-text"><strong>DOCX:</strong> Headings become section titles. Tables and lists are preserved.</span>
        </div>
        <div class="tip">
          <span class="tip-icon">📈</span>
          <span class="tip-text"><strong>XLSX:</strong> Markdown tables map directly to sheet rows and columns.</span>
        </div>
        <div class="tip">
          <span class="tip-icon">🤖</span>
          <span class="tip-text"><strong>LLM:</strong> Ollama runs locally. OpenAI/Claude/Groq need API keys via environment variables.</span>
        </div>
      </div>
    </div>

    <!-- Supported formats -->
    <div class="card">
      <div class="card-title"><span class="icon">📋</span> Supported Inputs</div>
      <div style="display:flex;flex-direction:column;gap:.35rem">
        <div class="tip"><span class="tip-icon">✍️</span><span class="tip-text"><strong>.md</strong> — Markdown (headings, lists, tables, code)</span></div>
        <div class="tip"><span class="tip-icon">📃</span><span class="tip-text"><strong>.txt</strong> — Plain text (auto-parsed by structure)</span></div>
        <div class="tip"><span class="tip-icon">🌐</span><span class="tip-text"><strong>.html</strong> — HTML (full inline/block parsing)</span></div>
      </div>
    </div>

  </aside>
</div>

<!-- ── Footer ── -->
<footer>
  Text2OfficeProcessor &#x2014; Open Source &#xB7; MIT &#xB7;
  <a href="https://github.com/sage-khan/text2officeprocessor" target="_blank" rel="noopener">GitHub</a>
</footer>

<script>
/* ── Theme toggle ─────────────────────────────────────────────────────────── */
const html = document.documentElement;
const themeBtn = document.getElementById('theme-toggle');
function applyTheme(t) {
  html.setAttribute('data-theme', t);
  themeBtn.textContent = t === 'dark' ? '☀️' : '🌙';
  localStorage.setItem('text2officeprocessor-theme', t);
}
applyTheme(localStorage.getItem('text2officeprocessor-theme') || 'light');
themeBtn.addEventListener('click', () => {
  applyTheme(html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
});

/* ── Tab switching ────────────────────────────────────────────────────────── */
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  });
});

/* ── Format cards ─────────────────────────────────────────────────────────── */
const fmtInput = document.getElementById('selected-fmt');
document.querySelectorAll('.fmt-card').forEach(card => {
  card.addEventListener('click', () => {
    document.querySelectorAll('.fmt-card').forEach(c => c.classList.remove('selected'));
    card.classList.add('selected');
    fmtInput.value = card.dataset.fmt;
  });
});

/* ── Drop zone ────────────────────────────────────────────────────────────── */
const dropZone   = document.getElementById('drop-zone');
const fileInput  = document.getElementById('file-input');
const fileChip   = document.getElementById('file-chip');
const chipName   = document.getElementById('file-chip-name');

dropZone.addEventListener('click', () => fileInput.click());
['dragover','dragenter'].forEach(ev => dropZone.addEventListener(ev, e => {
  e.preventDefault(); dropZone.classList.add('drag-over');
}));
['dragleave','dragend'].forEach(ev => dropZone.addEventListener(ev, () => {
  dropZone.classList.remove('drag-over');
}));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  if (e.dataTransfer.files.length) {
    const dropped = e.dataTransfer.files[0];
    const dt = new DataTransfer();
    dt.items.add(dropped);
    fileInput.files = dt.files;
    setFile(dropped);
  }
});
fileInput.addEventListener('change', () => {
  if (fileInput.files.length) setFile(fileInput.files[0]);
});
function setFile(f) {
  chipName.textContent = f.name;
  fileChip.style.display = 'block';
}

/* ── LLM model field visibility ───────────────────────────────────────────── */
const llmProvider = document.getElementById('llm-provider');
const llmModelWrap = document.getElementById('llm-model-wrap');
llmProvider.addEventListener('change', () => {
  llmModelWrap.style.display = (llmProvider.value && llmProvider.value !== 'none') ? 'block' : 'none';
});

/* ── History ──────────────────────────────────────────────────────────────── */
const historyList = document.getElementById('history-list');
const historyEmpty = document.getElementById('history-empty');
const FMT_ICONS = { pptx: '📊', docx: '📝', xlsx: '📈' };
const history = [];
function addHistory(name, fmt, url) {
  const now = new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
  history.unshift({ name, fmt, url, time: now });
  if (history.length > 8) history.pop();
  renderHistory();
}
function renderHistory() {
  historyList.innerHTML = '';
  if (!history.length) {
    historyList.innerHTML = '<li id="history-empty"><span>No conversions yet</span></li>';
    return;
  }
  history.forEach(h => {
    const li = document.createElement('li');
    li.innerHTML = \`
      <span class="h-icon">\${FMT_ICONS[h.fmt] || '📄'}</span>
      <span class="h-name" title="\${h.name}">\${h.name}</span>
      <span class="h-time">\${h.time}</span>
      <a href="\${h.url}" download="\${h.name}">↓</a>
    \`;
    historyList.appendChild(li);
  });
}

/* ── Conversion ───────────────────────────────────────────────────────────── */
const convertBtn    = document.getElementById('convert-btn');
const progressWrap  = document.getElementById('progress-wrap');
const progressBar   = document.getElementById('progress-bar');
const statusMsg     = document.getElementById('status-msg');
const downloadArea  = document.getElementById('download-area');
const dlFilename    = document.getElementById('dl-filename');
const dlAnchor      = document.getElementById('dl-anchor');
const pasteInput    = document.getElementById('paste-input');
const pasteFmt      = document.getElementById('paste-fmt');
const llmModel      = document.getElementById('llm-model');
const outputName    = document.getElementById('output-name');

function setStatus(msg, cls = 'info') {
  statusMsg.textContent = msg;
  statusMsg.className = cls;
}
function showProgress(on) {
  progressWrap.style.display = on ? 'block' : 'none';
  progressBar.classList.toggle('indeterminate', on);
}

convertBtn.addEventListener('click', async () => {
  const activeTab = document.querySelector('.tab-btn.active').dataset.tab;
  const fmt = fmtInput.value;
  const provider = llmProvider.value;
  const model = llmModel.value.trim();
  const requestedOutputName = outputName.value.trim();

  const formData = new FormData();
  formData.append('output_type', fmt);
  if (provider) formData.append('llm_provider', provider);
  if (model)    formData.append('llm_model', model);
  if (requestedOutputName) formData.append('output_name', requestedOutputName);

  if (activeTab === 'file') {
    if (!fileInput.files.length) { setStatus('⚠ Please select a file first.', 'error'); return; }
    formData.append('file', fileInput.files[0]);
  } else {
    const txt = pasteInput.value.trim();
    if (!txt) { setStatus('⚠ Please enter some content.', 'error'); return; }
    const ext = pasteFmt.value;
    const blob = new Blob([txt], { type: 'text/plain' });
    formData.append('file', blob, 'pasted' + ext);
  }

  convertBtn.disabled = true;
  downloadArea.style.display = 'none';
  showProgress(true);
  setStatus('Converting, please wait…', 'info');

  try {
    const resp = await fetch('/convert', { method: 'POST', body: formData });
    showProgress(false);

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      setStatus('✗ ' + (err.detail || 'Conversion failed.'), 'error');
      return;
    }

    const blob = await resp.blob();
    const cd = resp.headers.get('content-disposition') || '';
    const m  = cd.match(/filename="?([^"]+)"?/);
    const outName = m ? m[1] : 'output.' + fmt;
    const url = URL.createObjectURL(blob);

    dlFilename.textContent = outName;
    dlAnchor.href = url;
    dlAnchor.download = outName;
    downloadArea.style.display = 'block';
    setStatus('✓ Conversion complete!', 'success');
    addHistory(outName, fmt, url);

  } catch (err) {
    showProgress(false);
    setStatus('✗ Network error: ' + err.message, 'error');
  } finally {
    convertBtn.disabled = false;
  }
});
</script>
</body>
</html>
"""


def create_app():
    """
    Factory function that creates and returns the FastAPI application.

    FastAPI is imported at module level (soft optional); this function raises
    ImportError at call time if the web extras are not installed.
    """
    if not _FASTAPI_AVAILABLE:
        raise ImportError(
            "Web UI requires extra dependencies. Install with:\n"
            "  pip install text2officeprocessor[web]\n"
            "or: pip install fastapi 'uvicorn[standard]' python-multipart"
        )
    if not _MULTIPART_AVAILABLE:
        raise ImportError(
            "Web UI requires python-multipart for file uploads. Install with:\n"
            "  pip install python-multipart\n"
            "or install all web extras: pip install text2officeprocessor[web]"
        )

    app = FastAPI(title="Text2OfficeProcessor Web UI", version="0.3.1", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index():
        return HTMLResponse(content=_HTML)

    @app.get("/health")
    async def health():
        return JSONResponse({"status": "ok", "service": "text2officeprocessor"})

    @app.post("/convert")
    async def convert(
        file: UploadFile = File(...),
        output_type: str = Form("pptx"),
        llm_provider: Optional[str] = Form(None),
        llm_model: Optional[str] = Form(None),
        output_name: Optional[str] = Form(None),
    ):
        """
        Convert an uploaded file to the requested output format.

        Returns the converted file as a downloadable attachment.
        """
        from src.core.engines.docx.engine import DOCXEngine
        from src.core.engines.pptx.engine import PPTXEngine
        from src.core.engines.xlsx.engine import XLSXEngine
        from src.core.exceptions import Text2OfficeProcessorError
        from src.core.models import OutputFormat
        from src.core.parser.preprocessor import InputPreprocessor
        from src.core.planner.content_planner import ContentPlanner

        supported_in = {".md", ".txt", ".html", ".htm"}
        suffix = Path(file.filename or "input").suffix.lower()
        if suffix not in supported_in:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported input format '{suffix}'. Supported: {', '.join(sorted(supported_in))}",
            )

        output_type = output_type.lower().strip()
        if output_type not in ("pptx", "docx", "xlsx"):
            raise HTTPException(status_code=422, detail=f"Unsupported output type '{output_type}'.")

        try:
            fmt = OutputFormat(output_type)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Unknown output format: {output_type}")

        # Resolve LLM provider (local-first from llm_config.yaml unless disabled)
        provider = None
        try:
            from src.core.llm.providers import build_provider
            from src.core.llm.runtime_config import resolve_provider_selection

            resolved_name, llm_cfg = resolve_provider_selection(llm_provider, llm_model)
            if resolved_name:
                provider = build_provider(resolved_name, llm_cfg)
        except Exception as exc:
            logger.warning("Web: could not initialize configured LLM provider: %s", exc)

        # Resolve bundled template
        from src.cli.main import _bundled_templates_dir
        tdir = _bundled_templates_dir()
        template_path = None
        if fmt == OutputFormat.PPTX:
            candidate = tdir / "generic-slides.pptx"
            if candidate.exists():
                template_path = candidate
        elif fmt == OutputFormat.DOCX:
            candidate = tdir / "generic-document.docx"
            if candidate.exists():
                template_path = candidate

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            in_path = tmp_dir / (Path(file.filename or "input").stem + suffix)
            content = await file.read()
            in_path.write_bytes(content)

            stem = Path(file.filename or "output").stem
            out_ext = {"pptx": ".pptx", "docx": ".docx", "xlsx": ".xlsx"}[output_type]
            out_path = tmp_dir / (stem + out_ext)

            try:
                preprocessor = InputPreprocessor()
                parsed = preprocessor.parse(in_path)

                if fmt == OutputFormat.PPTX:
                    if not template_path:
                        raise HTTPException(status_code=500, detail="No PPTX template available.")
                    from src.core.llm.normalizer import LLMNormalizer
                    normalizer = LLMNormalizer(provider=provider)
                    normalized = normalizer.normalize(parsed)
                    planner = ContentPlanner()
                    plan = planner.plan_slides(parsed, normalized)
                    PPTXEngine().render(plan, template_path, out_path)

                elif fmt == OutputFormat.DOCX:
                    if not template_path:
                        raise HTTPException(status_code=500, detail="No DOCX template available.")
                    plan = ContentPlanner.plan_document(parsed)
                    DOCXEngine().render(plan, template_path, out_path)

                elif fmt == OutputFormat.XLSX:
                    plan = ContentPlanner.plan_spreadsheet(parsed)
                    XLSXEngine().render(plan, out_path)

            except HTTPException:
                raise
            except Text2OfficeProcessorError as exc:
                raise HTTPException(status_code=422, detail=str(exc))
            except Exception as exc:
                logger.exception("Web convert error")
                raise HTTPException(status_code=500, detail=f"Conversion failed: {exc}")

            safe_stem = stem
            if output_name and output_name.strip():
                safe_stem = Path(output_name.strip()).name
                if "." in safe_stem:
                    safe_stem = Path(safe_stem).stem
                safe_stem = safe_stem.strip() or stem

            out_name = safe_stem + out_ext
            media_types = {
                ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
            # Copy to a persistent temp file so FileResponse can stream it
            import shutil
            final_tmp = tempfile.NamedTemporaryFile(
                suffix=out_ext, delete=False, dir=tempfile.gettempdir()
            )
            shutil.copy2(str(out_path), final_tmp.name)
            final_tmp.close()

            return FileResponse(
                path=final_tmp.name,
                media_type=media_types.get(out_ext, "application/octet-stream"),
                filename=out_name,
                headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
                background=_cleanup_task(final_tmp.name),
            )

    return app


def _cleanup_task(path: str):
    """Return a BackgroundTask that deletes the temporary output file."""
    from starlette.background import BackgroundTask

    def _delete():
        try:
            os.unlink(path)
        except OSError:
            pass

    return BackgroundTask(_delete)
