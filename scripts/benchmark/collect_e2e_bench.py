#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.benchmark.common import append_summary, config_hash, git_commit, relpath_or_str, utc_now  # noqa: E402
from scripts.benchmark.parse_opentalking_logs import parse_log_file  # noqa: E402


def _request_json(method: str, url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_multipart_file(url: str, field: str, path: Path, timeout: float) -> dict[str, Any]:
    boundary = f"----opentalking-benchmark-{int(time.time() * 1000)}"
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        (
            f'Content-Disposition: form-data; name="{field}"; filename="{path.name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8")
    )
    body.extend(path.read_bytes())
    body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    request = urllib.request.Request(
        url,
        data=bytes(body),
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def build_row(args: argparse.Namespace, status: str, session_id: str = "") -> dict[str, Any]:
    config_paths = [Path(p) for p in args.config] if args.config else []
    return {
        "run_id": args.run_id or f"{int(time.time())}-{args.host}-{args.model}-{args.backend}-e2e",
        "created_at": utc_now(),
        "host": args.host,
        "backend": args.backend,
        "device_count": args.device_count,
        "model": args.model,
        "mode": "end-to-end",
        "cold_or_warm": args.cold_or_warm,
        "status": status,
        "git_commit": args.git_commit or git_commit(),
        "omnirt_commit": args.omnirt_commit,
        "config_hash": args.config_hash or config_hash(config_paths),
        "raw_log_path": relpath_or_str(args.log_file) if args.log_file else "",
        "notes": f"{args.notes} session_id={session_id}".strip(),
    }


def parse_and_fill(row: dict[str, Any], log_file: Path | None) -> dict[str, Any]:
    if log_file is None or not log_file.exists():
        row["status"] = "pending" if row["status"] == "completed" else row["status"]
        row["notes"] = (row["notes"] + " " if row["notes"] else "") + "log not available"
        return row
    summary = parse_log_file(log_file)["summary"]
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


def fill_manual_fields(row: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    for key in ("resource_peak_vram_or_hbm_gb", "drop_frame_rate"):
        value = getattr(args, key)
        if value not in (None, ""):
            row[key] = round(float(value), 2)
    return row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an OpenTalking end-to-end benchmark turn.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000", help="Example: http://127.0.0.1:8000")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--backend", required=True, choices=["cuda", "ascend", "cpu", "mock"])
    parser.add_argument("--device-count", type=int, default=1)
    parser.add_argument("--model", required=True)
    parser.add_argument("--avatar-id", default="singer")
    parser.add_argument("--action", choices=["speak", "chat", "uploaded-pcm"], default="speak")
    parser.add_argument("--text", default="你好，请用一句话介绍 OpenTalking 的实时数字人能力。")
    parser.add_argument("--audio-file", type=Path)
    parser.add_argument("--tts-provider")
    parser.add_argument("--tts-voice")
    parser.add_argument("--tts-model")
    parser.add_argument("--cold-or-warm", default="warm", choices=["cold", "warm"])
    parser.add_argument("--wait-seconds", type=float, default=20.0)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--log-file", type=Path)
    parser.add_argument("--parse-only", action="store_true", help="Only parse --log-file and append a summary row.")
    parser.add_argument("--resource-peak-vram-or-hbm-gb")
    parser.add_argument("--drop-frame-rate")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--git-commit", default="")
    parser.add_argument("--omnirt-commit", default="")
    parser.add_argument("--config", action="append", default=[])
    parser.add_argument("--config-hash", default="")
    parser.add_argument("--notes", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base = args.api_base.rstrip("/")
    session_id = ""
    status = "completed"
    if not args.parse_only:
        try:
            create_payload = {
                "avatar_id": args.avatar_id,
                "model": args.model,
                "tts_provider": args.tts_provider,
                "tts_voice": args.tts_voice,
            }
            create_payload = {k: v for k, v in create_payload.items() if v not in (None, "")}
            created = _request_json("POST", f"{base}/sessions", create_payload, args.timeout)
            session_id = str(created["session_id"])

            if args.action == "chat":
                payload = {"prompt": args.text}
                endpoint = f"{base}/sessions/{session_id}/chat"
                _request_json("POST", endpoint, payload, args.timeout)
            elif args.action == "uploaded-pcm":
                if args.audio_file is None:
                    raise ValueError("--audio-file is required for uploaded-pcm")
                endpoint = f"{base}/sessions/{session_id}/speak_flashtalk_audio"
                _post_multipart_file(endpoint, "file", args.audio_file, args.timeout)
            else:
                payload = {
                    "text": args.text,
                    "tts_provider": args.tts_provider,
                    "voice": args.tts_voice,
                    "tts_model": args.tts_model,
                }
                payload = {k: v for k, v in payload.items() if v not in (None, "")}
                endpoint = f"{base}/sessions/{session_id}/speak"
                _request_json("POST", endpoint, payload, args.timeout)
            time.sleep(max(0.0, args.wait_seconds))
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as exc:
            status = "blocked"
            args.notes = (args.notes + " " if args.notes else "") + f"request failed: {exc}"

    row = build_row(args, status, session_id=session_id)
    row = parse_and_fill(row, args.log_file)
    row = fill_manual_fields(row, args)
    saved = append_summary(args.output_dir, row)
    print(json.dumps(saved, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
