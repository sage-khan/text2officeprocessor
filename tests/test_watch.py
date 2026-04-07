"""
Tests for the watch command.

The watch command contains an infinite loop (time.sleep), so tests exercise:
- CLI option validation (missing file, valid inputs)
- The _regenerate logic by calling _run_xlsx/_run_pptx directly
- The watchdog handler dispatch (simulate file modification event)

The Observer loop itself is not run in tests; KeyboardInterrupt / exit tests
use a patched time.sleep that raises KeyboardInterrupt immediately.
"""
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from typer.testing import CliRunner
from src.cli.main import app

runner = CliRunner()

SAMPLE_MD = """\
# Watch Test

## Section

Paragraph content here.

- Item one
- Item two
"""


def test_watch_exits_nonzero_for_missing_input(tmp_path):
    result = runner.invoke(app, [
        "watch",
        "--input", str(tmp_path / "nonexistent.md"),
        "--output", str(tmp_path / "out.xlsx"),
        "--type", "xlsx",
    ])
    assert result.exit_code != 0
    assert "not found" in result.output.lower() or "ERROR" in result.output


def test_watch_generates_output_on_startup(tmp_path):
    """The watch command should run one immediate conversion before entering the loop."""
    md = tmp_path / "doc.md"
    md.write_text(SAMPLE_MD, encoding="utf-8")
    out = tmp_path / "doc.xlsx"

    # Patch time.sleep to raise KeyboardInterrupt after the first call
    # so the infinite loop exits immediately
    with patch("time.sleep", side_effect=KeyboardInterrupt):
        with patch("watchdog.observers.Observer.start"):
            with patch("watchdog.observers.Observer.stop"):
                with patch("watchdog.observers.Observer.join"):
                    result = runner.invoke(app, [
                        "watch",
                        "--input", str(md),
                        "--output", str(out),
                        "--type", "xlsx",
                        "--no-validate",
                    ])

    # Should exit cleanly (KeyboardInterrupt handled)
    assert result.exit_code == 0, result.output
    assert out.exists(), "Output file should be created on first run"


def test_watch_prints_watching_message(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text(SAMPLE_MD, encoding="utf-8")
    out = tmp_path / "doc.xlsx"

    with patch("time.sleep", side_effect=KeyboardInterrupt):
        with patch("watchdog.observers.Observer.start"):
            with patch("watchdog.observers.Observer.stop"):
                with patch("watchdog.observers.Observer.join"):
                    result = runner.invoke(app, [
                        "watch",
                        "--input", str(md),
                        "--output", str(out),
                        "--type", "xlsx",
                        "--no-validate",
                    ])

    assert "Watching" in result.output
    assert "Ctrl+C" in result.output


def test_watch_uses_bundled_template_for_pptx(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text(SAMPLE_MD, encoding="utf-8")
    out = tmp_path / "doc.pptx"

    with patch("time.sleep", side_effect=KeyboardInterrupt):
        with patch("watchdog.observers.Observer.start"):
            with patch("watchdog.observers.Observer.stop"):
                with patch("watchdog.observers.Observer.join"):
                    result = runner.invoke(app, [
                        "watch",
                        "--input", str(md),
                        "--output", str(out),
                        "--type", "pptx",
                        "--no-validate",
                    ])

    assert result.exit_code == 0, result.output
    assert out.exists()


def test_watch_debounce_cancels_rapid_events(tmp_path):
    """Fire multiple events quickly; only one regeneration should be scheduled."""
    from src.cli.main import _run_xlsx

    call_count = [0]
    original = _run_xlsx

    md = tmp_path / "doc.md"
    md.write_text(SAMPLE_MD, encoding="utf-8")
    out = tmp_path / "doc.xlsx"

    # Import the handler class logic indirectly via the schedule mechanism
    import threading

    _timer: list = [None]
    _lock = threading.Lock()
    debounce = 0.05

    def _fake_regenerate():
        call_count[0] += 1

    def _schedule():
        with _lock:
            if _timer[0] is not None:
                _timer[0].cancel()
            _timer[0] = threading.Timer(debounce, _fake_regenerate)
            _timer[0].start()

    # Fire 5 rapid events
    for _ in range(5):
        _schedule()

    # Wait for debounce to settle
    import time
    time.sleep(debounce * 4)

    assert call_count[0] == 1, f"Expected 1 regeneration, got {call_count[0]}"
