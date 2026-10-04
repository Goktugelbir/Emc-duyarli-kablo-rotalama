"""Regression: the published metrics (outputs/metrics.md, README) for the default configuration.

Values hold for the pinned dependency versions in requirements.txt. If a deliberate change
alters them, update this table together with the README.
"""

from __future__ import annotations

import pytest

# method: (total length, unique length, bundling ratio, EMC, bend, forbidden, clearance, capacity)
EXPECTED = {
    "baseline": (61.66, 51.65, 0.162, 980, 0, 0, 0, 20),
    "bundled": (71.84, 17.80, 0.752, 5660, 15, 0, 0, 116),
    "emc_aware": (66.18, 35.22, 0.468, 0, 8, 0, 0, 35),
    "lagrangian": (61.76, 53.80, 0.129, 887, 0, 0, 0, 0),
    "integrated": (66.05, 40.80, 0.382, 0, 0, 0, 0, 0),
}
KEYS = ("total_length_m", "unique_length_m", "bundling_ratio", "emc_points", "bend_points",
        "forbidden_points", "clearance_points", "capacity_edges")


@pytest.mark.parametrize("method", EXPECTED)
def test_published_metrics(metrics, method):
    row = metrics[method]
    total, unique, ratio, *counts = EXPECTED[method]
    assert row["total_length_m"] == pytest.approx(total, abs=0.006)
    assert row["unique_length_m"] == pytest.approx(unique, abs=0.006)
    assert row["bundling_ratio"] == pytest.approx(ratio, abs=0.0006)
    assert [row[k] for k in KEYS[3:]] == counts
