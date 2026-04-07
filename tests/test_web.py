"""
Tests for the MD2Office Web UI (FastAPI app).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")

from fastapi.testclient import TestClient
from src.web.app import create_app

client = TestClient(create_app())

SAMPLE_MD = b"# Test Document\n\n## Section\n\nSome content.\n\n- Item one\n- Item two\n"


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def test_health_returns_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# HTML UI
# ---------------------------------------------------------------------------

def test_index_returns_html():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "MD2Office" in resp.text
    assert "<form" in resp.text


# ---------------------------------------------------------------------------
# /convert endpoint
# ---------------------------------------------------------------------------

def test_convert_md_to_xlsx():
    resp = client.post(
        "/convert",
        data={"output_type": "xlsx"},
        files={"file": ("test.md", SAMPLE_MD, "text/markdown")},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert len(resp.content) > 0


def test_convert_txt_to_xlsx():
    content = b"# Plain Text\n\n## Section\n\nParagraph.\n"
    resp = client.post(
        "/convert",
        data={"output_type": "xlsx"},
        files={"file": ("notes.txt", content, "text/plain")},
    )
    assert resp.status_code == 200


def test_convert_html_to_xlsx():
    content = b"<html><body><h2>Section</h2><p>Content.</p></body></html>"
    resp = client.post(
        "/convert",
        data={"output_type": "xlsx"},
        files={"file": ("page.html", content, "text/html")},
    )
    assert resp.status_code == 200


def test_convert_md_to_pptx_with_bundled_template():
    resp = client.post(
        "/convert",
        data={"output_type": "pptx"},
        files={"file": ("slides.md", SAMPLE_MD, "text/markdown")},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.presentationml"
    )


def test_convert_md_to_docx_with_bundled_template():
    resp = client.post(
        "/convert",
        data={"output_type": "docx"},
        files={"file": ("doc.md", SAMPLE_MD, "text/markdown")},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml"
    )


def test_convert_unsupported_input_format_returns_422():
    resp = client.post(
        "/convert",
        data={"output_type": "xlsx"},
        files={"file": ("data.csv", b"a,b,c\n1,2,3\n", "text/csv")},
    )
    assert resp.status_code == 422


def test_convert_unsupported_output_type_returns_422():
    resp = client.post(
        "/convert",
        data={"output_type": "pdf"},
        files={"file": ("test.md", SAMPLE_MD, "text/markdown")},
    )
    assert resp.status_code == 422


def test_convert_output_filename_matches_input_stem():
    resp = client.post(
        "/convert",
        data={"output_type": "xlsx"},
        files={"file": ("my-report.md", SAMPLE_MD, "text/markdown")},
    )
    assert resp.status_code == 200
    cd = resp.headers.get("content-disposition", "")
    assert "my-report.xlsx" in cd
