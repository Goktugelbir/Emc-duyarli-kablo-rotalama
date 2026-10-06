"""End-to-end smoke test of `python main.py --no-images` and the generated interactive page."""

from __future__ import annotations

import json
import re

import main


def test_main_without_images(tmp_path):
    out, docs = tmp_path / "out", tmp_path / "docs"
    main.main(["--no-images", "--trials", "1", "--workers", "1", "--out", str(out), "--docs", str(docs)])

    expected = ("metrics.md", "robustness.md", "lagrangian_history.json", "run_log.txt", "wirelist.csv", "routes.json")
    for name in expected:
        assert (out / name).is_file(), name
    assert not list(out.glob("*.png")), "--no-images must not export images"

    log = (out / "run_log.txt").read_text(encoding="utf-8")
    assert "e) Bütünleşik" in log and str(tmp_path) not in log  # no local paths in the log
    json.loads((out / "lagrangian_history.json").read_text(encoding="utf-8"))  # strict JSON (no Infinity)

    page = (docs / "index.html").read_text(encoding="utf-8")
    assert "__DATA_JSON__" not in page and "__THREE_VERSION__" not in page
    data = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1))
    assert [m["key"] for m in data["methods"]] == ["baseline", "bundled", "emc_aware", "lagrangian", "integrated"]
    assert data["initial"] == "integrated" and data["clearance"] == main.CLEARANCE_M
    n_vertices = len(data["mesh"]["v"]) // 3
    for m in data["methods"]:
        assert sorted(m["order"]) == sorted(m["routes"])
        assert all(0 <= i < n_vertices for path in m["routes"].values() for i in path)
        assert len(m["violations"]) == 3 * m["emc_points"]
