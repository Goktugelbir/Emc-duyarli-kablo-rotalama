"""Performance metrics and table formatting."""

from __future__ import annotations

from typing import Any

import numpy as np

from .checks import CheckReport
from .graph import RoutingGraph
from .routing import RoutingResult

Row = dict[str, Any]  # one metric row per method (heterogeneous values: label, floats, counts)

# (key, header, format)
COLUMNS: list[tuple[str, str, str]] = [
    ("label", "Yöntem", "{}"),
    ("total_length_m", "Toplam uzunluk [m]", "{:.2f}"),
    ("unique_length_m", "Benzersiz uzunluk [m]", "{:.2f}"),
    ("bundling_ratio", "Demetlenme oranı", "{:.3f}"),
    ("emc_points", "EMC ihlali [nokta]", "{}"),
    ("bend_points", "Bükülme ihlali", "{}"),
    ("forbidden_points", "Yasak hacim ihlali", "{}"),
    ("clearance_points", "Boşluk payı ihlali [nokta]", "{}"),
    ("capacity_edges", "Kapasite ihlali [ayrıt]", "{}"),
    ("runtime_s", "Süre [s]", "{:.2f}"),
]


def compute_metrics(result: RoutingResult, graph: RoutingGraph, report: CheckReport) -> Row:
    """Length, bundling and violation metrics for one method."""
    edge_sets = [graph.path_edge_ids(p) for p in result.routes.values()]
    total = float(sum(graph.lengths[e].sum() for e in edge_sets))
    unique = float(graph.lengths[np.unique(np.concatenate(edge_sets))].sum())
    return {
        "method": result.method,
        "label": result.label,
        "total_length_m": total,
        "unique_length_m": unique,
        "bundling_ratio": 1.0 - unique / total,
        **report.as_dict(),
        "runtime_s": result.runtime_s,
    }


def _cells(rows: list[Row]) -> list[list[str]]:
    """Formatted cell strings for every row."""
    return [[fmt.format(r[key]) for key, _, fmt in COLUMNS] for r in rows]


def format_console_table(rows: list[Row]) -> str:
    """Fixed-width plain-text table."""
    headers = [h for _, h, _ in COLUMNS]
    cells = _cells(rows)
    widths = [max(len(h), *(len(c[i]) for c in cells)) for i, h in enumerate(headers)]
    line = "-+-".join("-" * w for w in widths)
    out = [" | ".join(h.ljust(w) for h, w in zip(headers, widths)), line]
    for row in cells:
        out.append(" | ".join(c.ljust(w) if i == 0 else c.rjust(w) for i, (c, w) in enumerate(zip(row, widths))))
    return "\n".join(out)


def format_markdown_table(rows: list[Row]) -> str:
    """GitHub-flavoured Markdown table."""
    headers = [h for _, h, _ in COLUMNS]
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join([":---"] + ["---:"] * (len(headers) - 1)) + "|"]
    out += ["| " + " | ".join(c) + " |" for c in _cells(rows)]
    return "\n".join(out)
