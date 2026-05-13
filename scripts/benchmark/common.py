from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUMMARY_FIELDS = [
    "run_id",
    "created_at",
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
    "model_generate_ms_avg",
    "model_generate_ms_p50",
    "model_generate_ms_p95",
    "resource_peak_vram_or_hbm_gb",
    "drop_frame_rate",
    "git_commit",
    "omnirt_commit",
    "config_hash",
    "raw_log_path",
    "notes",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def git_commit(cwd: Path | None = None) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=str(cwd or repo_root()),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def file_hash(path: Path | None) -> str:
    if path is None:
        return ""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()[:16]
    except FileNotFoundError:
        return ""


def config_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    used = False
    for path in paths:
        if not path.exists():
            continue
        used = True
        digest.update(str(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16] if used else ""


def output_paths(output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / "summary.json", output_dir / "summary.csv"


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {field: row.get(field, "") for field in SUMMARY_FIELDS}
    for field in SUMMARY_FIELDS:
        if out[field] is None:
            out[field] = ""
    return out


def load_rows(summary_json: Path) -> list[dict[str, Any]]:
    if not summary_json.exists():
        return []
    data = json.loads(summary_json.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("runs"), list):
        return [normalize_row(item) for item in data["runs"]]
    if isinstance(data, list):
        return [normalize_row(item) for item in data]
    raise ValueError(f"Unsupported summary format: {summary_json}")


def append_summary(output_dir: Path, row: dict[str, Any]) -> dict[str, Any]:
    row = normalize_row(row)
    summary_json, summary_csv = output_paths(output_dir)
    rows = load_rows(summary_json)
    rows.append(row)
    summary_json.write_text(
        json.dumps({"runs": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with summary_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return row


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * pct
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    frac = pos - low
    return ordered[low] * (1.0 - frac) + ordered[high] * frac


def relpath_or_str(path: str | Path | None, base: Path | None = None) -> str:
    if path is None or str(path) == "":
        return ""
    p = Path(path)
    try:
        return str(p.resolve().relative_to((base or repo_root()).resolve()))
    except Exception:
        return str(path)
