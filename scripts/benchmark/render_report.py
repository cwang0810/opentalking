#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.benchmark.common import load_rows, relpath_or_str, repo_root  # noqa: E402


DISPLAY_FIELDS = [
    "host",
    "backend",
    "device_count",
    "model",
    "mode",
    "cold_or_warm",
    "status",
    "ttfa_ms",
    "ttfv_ms",
    "e2e_ms",
    "steady_fps",
    "first_model_return_ms",
    "model_generate_ms_p50",
    "model_generate_ms_p95",
    "resource_peak_vram_or_hbm_gb",
    "drop_frame_rate",
    "raw_log_path",
]


def _cell(value: Any) -> str:
    if value in (None, ""):
        return "-"
    text = str(value).replace("\n", " ").replace("|", "\\|")
    return text


def _table(rows: list[dict[str, Any]]) -> str:
    header = "| " + " | ".join(DISPLAY_FIELDS) + " |"
    sep = "| " + " | ".join(["---"] * len(DISPLAY_FIELDS)) + " |"
    body = [
        "| " + " | ".join(_cell(row.get(field)) for field in DISPLAY_FIELDS) + " |"
        for row in rows
    ]
    return "\n".join([header, sep, *body])


def render(rows: list[dict[str, Any]]) -> str:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("backend") or "unknown")].append(row)

    sections = []
    for backend in ("cuda", "ascend", "cpu", "mock", "unknown"):
        if not grouped.get(backend):
            continue
        title = {
            "cuda": "## GPU / CUDA Results",
            "ascend": "## NPU / Ascend Results",
            "cpu": "## CPU Results",
            "mock": "## Mock Results",
            "unknown": "## Other Results",
        }[backend]
        sections.append(title + "\n\n" + _table(grouped[backend]))

    if not sections:
        sections.append(
            "## Results\n\n"
            "No benchmark summary rows have been collected yet. Generate rows with "
            "`scripts/benchmark/collect_model_bench.py` and "
            "`scripts/benchmark/collect_e2e_bench.py`."
        )

    return "\n\n".join(sections)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render benchmark result tables from summary JSON.")
    parser.add_argument("--summary-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=repo_root() / "docs" / "benchmark.md")
    parser.add_argument("--replace-marker", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = load_rows(args.summary_json)
    rendered = render(rows)
    if args.replace_marker and args.output.exists():
        text = args.output.read_text(encoding="utf-8")
        start = "<!-- BENCHMARK_RESULTS_START -->"
        end = "<!-- BENCHMARK_RESULTS_END -->"
        if start not in text or end not in text:
            raise SystemExit(f"Missing result markers in {args.output}")
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + start + "\n" + rendered + "\n" + end + after
    else:
        text = rendered + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(relpath_or_str(args.output))


if __name__ == "__main__":
    main()
