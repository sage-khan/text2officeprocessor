"""
src/web/app.py

MD2Office Web UI — a minimal FastAPI application that exposes the conversion
pipeline through a browser interface.

Endpoints:
  GET  /           — Single-page HTML UI
  GET  /health     — JSON health check
  POST /convert    — Convert an uploaded file; returns the output file

Start with:
  md2office serve [--host 0.0.0.0] [--port 8000]
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

_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>MD2Office — Document Converter</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f5f7fa;
      color: #1a1a2e;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 2rem 1rem;
    }
    header { text-align: center; margin-bottom: 2rem; }
    header h1 { font-size: 2rem; font-weight: 700; color: #16213e; }
    header p  { color: #555; margin-top: 0.4rem; font-size: 0.95rem; }
    .card {
      background: #fff;
      border-radius: 12px;
      box-shadow: 0 4px 20px rgba(0,0,0,.08);
      padding: 2rem;
      width: 100%;
      max-width: 560px;
    }
    .drop-zone {
      border: 2px dashed #cbd5e1;
      border-radius: 8px;
      padding: 2rem;
      text-align: center;
      cursor: pointer;
      transition: border-color .2s, background .2s;
      margin-bottom: 1.2rem;
    }
    .drop-zone.drag-over { border-color: #6366f1; background: #eef2ff; }
    .drop-zone svg { width: 40px; height: 40px; color: #94a3b8; margin-bottom: .5rem; }
    .drop-zone p { color: #64748b; font-size: .9rem; }
    .drop-zone strong { color: #6366f1; }
    #file-name { font-size: .85rem; color: #475569; margin-top: .4rem; }
    .field { margin-bottom: 1rem; }
    .field label { display: block; font-weight: 600; font-size: .85rem; margin-bottom: .3rem; color: #334155; }
    .field select, .field input[type=text] {
      width: 100%;
      padding: .5rem .75rem;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      font-size: .9rem;
      background: #f8fafc;
      color: #1e293b;
    }
    .field select:focus, .field input[type=text]:focus {
      outline: 2px solid #6366f1;
      border-color: #6366f1;
    }
    button[type=submit] {
      width: 100%;
      padding: .75rem;
      background: #6366f1;
      color: #fff;
      border: none;
      border-radius: 8px;
      font-size: 1rem;
      font-weight: 600;
      cursor: pointer;
      transition: background .2s;
    }
    button[type=submit]:hover { background: #4f46e5; }
    button[type=submit]:disabled { background: #a5b4fc; cursor: default; }
    #status { margin-top: 1rem; font-size: .9rem; min-height: 1.5rem; }
    #status.error { color: #dc2626; }
    #status.success { color: #16a34a; }
    #download-link {
      display: none;
      margin-top: 1rem;
      text-align: center;
    }
    #download-link a {
      display: inline-block;
      padding: .6rem 1.5rem;
      background: #0ea5e9;
      color: #fff;
      border-radius: 6px;
      text-decoration: none;
      font-weight: 600;
      font-size: .9rem;
    }
    #download-link a:hover { background: #0284c7; }
    .badges { display: flex; gap: .5rem; flex-wrap: wrap; margin-top: 2rem; justify-content: center; }
    .badge {
      background: #f1f5f9;
      border: 1px solid #e2e8f0;
      border-radius: 4px;
      padding: .2rem .6rem;
      font-size: .75rem;
      color: #475569;
    }
  </style>
</head>
<body>
<header>
  <h1>MD2Office</h1>
  <p>Convert Markdown, text, or HTML to PPTX, DOCX, or XLSX</p>
</header>

<div class="card">
  <form id="convert-form" enctype="multipart/form-data">
    <div class="drop-zone" id="drop-zone">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
        <polyline points="17 8 12 3 7 8"/>
        <line x1="12" y1="3" x2="12" y2="15"/>
      </svg>
      <p>Drop your file here or <strong>click to browse</strong></p>
      <p id="file-name">No file selected</p>
      <input type="file" id="file-input" name="file"
             accept=".md,.txt,.html,.htm" style="display:none" required />
    </div>

    <div class="field">
      <label for="output-type">Output format</label>
      <select name="output_type" id="output-type">
        <option value="pptx">PPTX — PowerPoint presentation</option>
        <option value="docx">DOCX — Word document</option>
        <option value="xlsx">XLSX — Excel spreadsheet</option>
      </select>
    </div>

    <div class="field">
      <label for="llm-provider">LLM normalisation (optional)</label>
      <select name="llm_provider" id="llm-provider">
        <option value="">None (rule-based only)</option>
        <option value="ollama">Ollama (local)</option>
        <option value="openai">OpenAI</option>
        <option value="claude">Claude</option>
        <option value="groq">Groq</option>
        <option value="openrouter">OpenRouter</option>
      </select>
    </div>

    <div class="field">
      <label for="llm-model">LLM model name <span style="font-weight:400;color:#94a3b8">(leave blank for provider default)</span></label>
      <input type="text" name="llm_model" id="llm-model" placeholder="e.g. mistral, gpt-4o-mini" />
    </div>

    <button type="submit" id="convert-btn">Convert</button>
    <div id="status"></div>
    <div id="download-link"><a id="dl-anchor" href="#">Download output file</a></div>
  </form>
</div>

<div class="badges">
  <span class="badge">md .txt .html → .pptx .docx .xlsx</span>
  <span class="badge">Template-driven</span>
  <span class="badge">LLM-optional</span>
  <span class="badge">Open Source · MIT</span>
</div>

<script>
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const fileName  = document.getElementById('file-name');
const form      = document.getElementById('convert-form');
const status    = document.getElementById('status');
const btn       = document.getElementById('convert-btn');
const dlDiv     = document.getElementById('download-link');
const dlAnchor  = document.getElementById('dl-anchor');

dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  if (e.dataTransfer.files.length) {
    fileInput.files = e.dataTransfer.files;
    fileName.textContent = e.dataTransfer.files[0].name;
  }
});
fileInput.addEventListener('change', () => {
  fileName.textContent = fileInput.files.length ? fileInput.files[0].name : 'No file selected';
});

form.addEventListener('submit', async e => {
  e.preventDefault();
  if (!fileInput.files.length) { setStatus('Please select a file.', 'error'); return; }

  btn.disabled = true;
  dlDiv.style.display = 'none';
  setStatus('Converting\u2026', '');

  const data = new FormData(form);

  try {
    const resp = await fetch('/convert', { method: 'POST', body: data });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      setStatus('\u274c ' + (err.detail || 'Conversion failed.'), 'error');
      return;
    }
    const blob = await resp.blob();
    const cd   = resp.headers.get('content-disposition') || '';
    const match = cd.match(/filename="?([^"]+)"?/);
    const outName = match ? match[1] : 'output';
    const url = URL.createObjectURL(blob);
    dlAnchor.href = url;
    dlAnchor.download = outName;
    dlDiv.style.display = 'block';
    setStatus('\u2705 Conversion complete!', 'success');
  } catch (err) {
    setStatus('\u274c Network error: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
  }
});

function setStatus(msg, cls) {
  status.textContent = msg;
  status.className = cls;
}
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
            "  pip install md2office[web]\n"
            "or: pip install fastapi 'uvicorn[standard]' python-multipart"
        )

    app = FastAPI(title="MD2Office Web UI", version="0.2.4", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index():
        return HTMLResponse(content=_HTML)

    @app.get("/health")
    async def health():
        return JSONResponse({"status": "ok", "service": "md2office"})

    @app.post("/convert")
    async def convert(
        file: UploadFile = File(...),
        output_type: str = Form("pptx"),
        llm_provider: Optional[str] = Form(None),
        llm_model: Optional[str] = Form(None),
    ):
        """
        Convert an uploaded file to the requested output format.

        Returns the converted file as a downloadable attachment.
        """
        from src.core.engines.docx.engine import DOCXEngine
        from src.core.engines.pptx.engine import PPTXEngine
        from src.core.engines.xlsx.engine import XLSXEngine
        from src.core.exceptions import MD2OfficeError
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

        # Resolve LLM provider
        provider = None
        if llm_provider and llm_provider.strip():
            try:
                from src.core.llm.providers import build_provider
                llm_cfg = {}
                if llm_model and llm_model.strip():
                    llm_cfg["model"] = llm_model.strip()
                provider = build_provider(llm_provider.strip(), llm_cfg)
            except Exception as exc:
                logger.warning("Web: could not init LLM provider '%s': %s", llm_provider, exc)

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
            except MD2OfficeError as exc:
                raise HTTPException(status_code=422, detail=str(exc))
            except Exception as exc:
                logger.exception("Web convert error")
                raise HTTPException(status_code=500, detail=f"Conversion failed: {exc}")

            out_name = stem + out_ext
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
