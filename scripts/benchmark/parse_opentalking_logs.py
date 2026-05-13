#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.benchmark.common import percentile  # noqa: E402


KEY_VALUE_RE = re.compile(r"([A-Za-z0-9_]+)=([^ ]+)")
SPEAK_RE = re.compile(r"(Speak pipeline timing|speak_uploaded_pcm timing): (?P<body>.*)")
CHUNK_RE = re.compile(
    r"FlashTalk WS chunk: frames=(?P<frames>\d+) payload=(?P<payload_kb>\d+)KB "
    r"wait=(?P<wait_s>[0-9.]+)s parse=(?P<parse_s>[0-9.]+)s "
    r"decode=(?P<decode_s>[0-9.]+)s workers=(?P<workers>\d+)"
)


def _number(value: str) -> float | int | None | str:
    if value in {"n/a", "None", "null", "-"}:
        return None
    try:
        number = float(value)
    except ValueError:
        return value
    if number.is_integer():
        return int(number)
    return number


def parse_key_values(body: str) -> dict[str, Any]:
    return {match.group(1): _number(match.group(2).rstrip(",")) for match in KEY_VALUE_RE.finditer(body)}


def parse_log_text(text: str) -> dict[str, Any]:
    speak_events: list[dict[str, Any]] = []
    uploaded_pcm_events: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []

    for line_no, line in enumerate(text.splitlines(), start=1):
        speak_match = SPEAK_RE.search(line)
        if speak_match:
            event = parse_key_values(speak_match.group("body"))
            event["line_no"] = line_no
            if speak_match.group(1) == "speak_uploaded_pcm timing":
                uploaded_pcm_events.append(event)
            else:
                speak_events.append(event)
            continue

        chunk_match = CHUNK_RE.search(line)
        if chunk_match:
            chunk = {
                "line_no": line_no,
                "frames": int(chunk_match.group("frames")),
                "payload_kb": int(chunk_match.group("payload_kb")),
                "wait_ms": float(chunk_match.group("wait_s")) * 1000.0,
                "parse_ms": float(chunk_match.group("parse_s")) * 1000.0,
                "decode_ms": float(chunk_match.group("decode_s")) * 1000.0,
                "workers": int(chunk_match.group("workers")),
            }
            chunks.append(chunk)

    return {
        "speak_events": speak_events,
        "uploaded_pcm_events": uploaded_pcm_events,
        "flashtalk_chunks": chunks,
        "summary": summarize_events(speak_events, uploaded_pcm_events, chunks),
    }


def parse_log_file(path: Path) -> dict[str, Any]:
    return parse_log_text(path.read_text(encoding="utf-8", errors="replace"))


def summarize_events(
    speak_events: list[dict[str, Any]],
    uploaded_pcm_events: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    events = speak_events or uploaded_pcm_events
    first = events[-1] if events else {}
    waits = [float(chunk["wait_ms"]) for chunk in chunks]
    frames = sum(int(chunk["frames"]) for chunk in chunks)
    wait_seconds = sum(waits) / 1000.0

    def pick(*names: str) -> Any:
        for name in names:
            value = first.get(name)
            if value not in (None, ""):
                return value
        return None

    return {
        "ttfa_ms": pick("first_chunk_queued_ms", "first_chunk_ms"),
        "ttfv_ms": pick("first_webrtc_queue_ms", "first_webrtc_ms", "first_frame_from_api_wall_ms"),
        "e2e_ms": pick("first_frame_from_api_wall_ms", "speak_wall_ms", "wall_ms"),
        "first_model_return_ms": pick("first_flashtalk_return_ms", "first_ft_ms"),
        "model_generate_ms_avg": sum(waits) / len(waits) if waits else None,
        "model_generate_ms_p50": percentile(waits, 0.50),
        "model_generate_ms_p95": percentile(waits, 0.95),
        "steady_fps": frames / wait_seconds if wait_seconds > 0 else None,
        "speak_event_count": len(speak_events),
        "uploaded_pcm_event_count": len(uploaded_pcm_events),
        "flashtalk_chunk_count": len(chunks),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse OpenTalking benchmark timing logs.")
    parser.add_argument("log_file", type=Path)
    parser.add_argument("--summary-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    parsed = parse_log_file(args.log_file)
    payload = parsed["summary"] if args.summary_only else parsed
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
