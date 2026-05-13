#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.benchmark.common import (  # noqa: E402
    append_summary,
    config_hash,
    file_hash,
    git_commit,
    relpath_or_str,
    utc_now,
)  # noqa: E402
from scripts.benchmark.parse_opentalking_logs import parse_log_file  # noqa: E402


def _float_or_none(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def base_row(args: argparse.Namespace, *, status: str) -> dict[str, Any]:
    config_paths = [Path(p) for p in args.config] if args.config else []
    raw_log = Path(args.raw_log) if args.raw_log else None
    return {
        "run_id": args.run_id or f"{int(time.time())}-{args.host}-{args.model}-{args.backend}",
        "created_at": utc_now(),
        "host": args.host,
        "backend": args.backend,
        "device_count": args.device_count,
        "model": args.model,
        "mode": "model-only",
        "cold_or_warm": args.cold_or_warm,
        "status": status,
        "git_commit": args.git_commit or git_commit(),
        "omnirt_commit": args.omnirt_commit,
        "config_hash": args.config_hash or config_hash(config_paths) or file_hash(raw_log),
        "raw_log_path": relpath_or_str(raw_log) if raw_log else "",
        "notes": args.notes,
    }


def run_quicktalk(args: argparse.Namespace) -> dict[str, Any]:
    cmd = [
        "opentalking-quicktalk-bench",
        "--asset-root",
        args.asset_root,
        "--template-video",
        args.template_video,
        "--audio",
        args.audio,
        "--output",
        args.video_output,
        "--device",
        args.device,
    ]
    started = time.perf_counter()
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    wall_ms = (time.perf_counter() - started) * 1000.0
    log_path = Path(args.output_dir) / "quicktalk-bench.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(
            [
                "$ " + " ".join(cmd),
                "",
                "[stdout]",
                proc.stdout,
                "[stderr]",
                proc.stderr,
            ]
        ),
        encoding="utf-8",
    )
    row = base_row(args, status="completed" if proc.returncode == 0 else "blocked")
    row["raw_log_path"] = relpath_or_str(log_path)
    row["e2e_ms"] = round(wall_ms, 2)
    if proc.returncode != 0:
        row["notes"] = (row["notes"] + " " if row["notes"] else "") + f"quicktalk rc={proc.returncode}"
        return row
    metrics = json.loads(proc.stdout)
    row.update(
        {
            "ttfv_ms": round(float(metrics.get("first_frame_seconds") or 0.0) * 1000.0, 2),
            "first_model_return_ms": round(float(metrics.get("first_frame_seconds") or 0.0) * 1000.0, 2),
            "model_generate_ms_avg": round(float(metrics.get("render_seconds") or 0.0) * 1000.0, 2),
            "steady_fps": round(float(metrics.get("render_fps") or 0.0), 2),
        }
    )
    return row


def run_log_parse(args: argparse.Namespace) -> dict[str, Any]:
    row = base_row(args, status=args.status)
    if not args.raw_log:
        row["status"] = "blocked"
        row["notes"] = (row["notes"] + " " if row["notes"] else "") + "--raw-log is required"
        return row
    summary = parse_log_file(Path(args.raw_log))["summary"]
    for key in (
        "ttfa_ms",
        "ttfv_ms",
        "e2e_ms",
        "steady_fps",
        "first_model_return_ms",
        "model_generate_ms_avg",
        "model_generate_ms_p50",
        "model_generate_ms_p95",
    ):
        value = summary.get(key)
        row[key] = round(float(value), 2) if value is not None else ""
    return row


def run_endpoint_smoke(args: argparse.Namespace) -> dict[str, Any]:
    row = base_row(args, status="completed")
    if not args.endpoint:
        row["status"] = "blocked"
        row["notes"] = (row["notes"] + " " if row["notes"] else "") + "--endpoint is required"
        return row
    url = args.endpoint.rstrip("/") + args.models_path
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=args.timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        row["first_model_return_ms"] = round(elapsed_ms, 2)
        row["notes"] = (row["notes"] + " " if row["notes"] else "") + f"models={body[:300]}"
    except (urllib.error.URLError, TimeoutError) as exc:
        row["status"] = "blocked"
        row["notes"] = (row["notes"] + " " if row["notes"] else "") + f"endpoint failed: {exc}"
    return row


def run_manual(args: argparse.Namespace) -> dict[str, Any]:
    row = base_row(args, status=args.status)
    for key in (
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
    ):
        row[key] = _float_or_none(getattr(args, key))
    return row


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--host", required=True, help="Public benchmark host label, for example cuda-8x3090")
    parser.add_argument("--backend", required=True, choices=["cuda", "ascend", "cpu", "mock"])
    parser.add_argument("--device-count", type=int, default=1)
    parser.add_argument("--model", required=True)
    parser.add_argument("--cold-or-warm", default="warm", choices=["cold", "warm"])
    parser.add_argument("--run-id", default="")
    parser.add_argument("--git-commit", default="")
    parser.add_argument("--omnirt-commit", default="")
    parser.add_argument("--config", action="append", default=[])
    parser.add_argument("--config-hash", default="")
    parser.add_argument("--raw-log", default="")
    parser.add_argument("--notes", default="")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect model-only benchmark rows.")
    sub = parser.add_subparsers(dest="command", required=True)

    quicktalk = sub.add_parser("quicktalk", help="Run opentalking-quicktalk-bench and record metrics.")
    add_common(quicktalk)
    quicktalk.add_argument("--asset-root", required=True)
    quicktalk.add_argument("--template-video", required=True)
    quicktalk.add_argument("--audio", required=True)
    quicktalk.add_argument("--video-output", required=True)
    quicktalk.add_argument("--device", default="cuda:0")

    logs = sub.add_parser("log", help="Parse existing OpenTalking timing logs.")
    add_common(logs)
    logs.add_argument("--status", default="completed", choices=["completed", "blocked", "pending", "not_run"])

    endpoint = sub.add_parser("endpoint-smoke", help="Check an OmniRT models endpoint.")
    add_common(endpoint)
    endpoint.add_argument("--endpoint", required=True)
    endpoint.add_argument("--models-path", default="/v1/audio2video/models")
    endpoint.add_argument("--timeout", type=float, default=10.0)

    manual = sub.add_parser("manual", help="Append a manually verified or blocked benchmark row.")
    add_common(manual)
    manual.add_argument("--status", default="pending", choices=["completed", "blocked", "pending", "not_run"])
    for key in (
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
    ):
        manual.add_argument(f"--{key.replace('_', '-')}", dest=key)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "quicktalk":
        row = run_quicktalk(args)
    elif args.command == "log":
        row = run_log_parse(args)
    elif args.command == "endpoint-smoke":
        row = run_endpoint_smoke(args)
    elif args.command == "manual":
        row = run_manual(args)
    else:
        raise AssertionError(args.command)
    saved = append_summary(args.output_dir, row)
    print(json.dumps(saved, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
