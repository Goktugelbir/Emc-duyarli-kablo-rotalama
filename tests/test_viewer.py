"""The interactive viewer (harness_demo/viewer/): JS syntax, data contract, capture API, optional browser run.

The browser test loads the generated page in headless Chrome and needs Chrome plus internet access
(three.js comes from a CDN), so it only runs with HARNESS_BROWSER_TESTS=1.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import main
from harness_demo.presentation import VIEWER_DIR

VIEWER_JS = (VIEWER_DIR / "viewer.js").read_text(encoding="utf-8")
CAPTURE_PY = (Path(main.__file__).parent / "harness_demo" / "capture.py").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def page(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("viewer")
    main.main(["--no-images", "--trials", "0", "--workers", "1",
               "--out", str(tmp / "out"), "--docs", str(tmp / "docs")])
    return tmp / "docs" / "index.html"


def _embedded_data(page: Path) -> dict:
    html = page.read_text(encoding="utf-8")
    return json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S).group(1))


def test_page_is_self_contained(page):
    html = page.read_text(encoding="utf-8")
    for placeholder in ("__STYLE__", "__SCRIPT__", "__DATA_JSON__", "__THREE_VERSION__"):
        assert placeholder not in html
    assert (VIEWER_DIR / "viewer.css").read_text(encoding="utf-8").strip()[:40] in html
    assert "window.viewer = {" in html  # the script was inlined


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_viewer_js_syntax(tmp_path):
    module = tmp_path / "viewer.mjs"  # .mjs: parse as an ES module (it uses import statements)
    module.write_text(VIEWER_JS, encoding="utf-8")
    proc = subprocess.run(["node", "--check", str(module)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_viewer_reads_only_embedded_data_fields(page):
    """Every top-level `D.<field>` the viewer uses must be provided by presentation.py."""
    used = set(re.findall(r"\bD\.([A-Za-z_]\w*)", VIEWER_JS))
    provided = set(_embedded_data(page))
    assert used, "the viewer should read its data from D"
    assert used <= provided, f"missing in the embedded data: {sorted(used - provided)}"


def test_capture_uses_only_existing_viewer_api():
    """capture.py drives the page through window.viewer; every member it calls must exist."""
    api_block = VIEWER_JS[VIEWER_JS.index("window.viewer = {"):]
    api_block = api_block[: api_block.index("\n};")]
    defined = set(re.findall(r"^\s{2}(\w+)(?:\(|:)", api_block, re.M))
    called = set(re.findall(r"window\.viewer\.(\w+)", CAPTURE_PY))
    assert called, "capture.py should drive window.viewer"
    assert called <= defined, f"not defined in viewer.js: {sorted(called - defined)}"


@pytest.mark.skipif(os.environ.get("HARNESS_BROWSER_TESTS") != "1",
                    reason="set HARNESS_BROWSER_TESTS=1 (needs Chrome + internet)")
def test_page_runs_without_errors_in_headless_chrome(page):
    from choreographer import Browser

    from harness_demo.capture import _open

    async def run() -> tuple[list, int, str]:
        async with Browser(headless=True, enable_gpu=True) as browser:
            p = await _open(browser, page)
            for key in _embedded_data(page)["methods"]:
                key = key["key"]
                await p.js(f"window.viewer.select('{key}'); window.viewer.progress(3.5); window.viewer.frame()")
            n = await p.js("window.viewer.methods.length")
            caption = await p.js("document.getElementById('caption').textContent")
            return await p.js("window.__viewerErrors"), n, caption

    errors, n_methods, caption = asyncio.run(run())
    assert errors == []
    assert n_methods == 5
    assert "e) Bütünleşik" in caption  # last selected method
