from __future__ import annotations

from pathlib import Path

from scripts.benchmark.parse_opentalking_logs import parse_log_file, summarize_events


def test_parse_opentalking_timing_log_fixture() -> None:
    fixture = Path("tests/fixtures/benchmark/opentalking_timing.txt")

    parsed = parse_log_file(fixture)

    assert len(parsed["speak_events"]) == 1
    assert len(parsed["uploaded_pcm_events"]) == 1
    assert len(parsed["flashtalk_chunks"]) == 2
    summary = parsed["summary"]
    assert summary["ttfa_ms"] == 420
    assert summary["ttfv_ms"] == 1120
    assert summary["e2e_ms"] == 1165
    assert summary["first_model_return_ms"] == 1010
    assert round(summary["model_generate_ms_avg"], 2) == 895.0
    assert round(summary["steady_fps"], 2) == 27.93


def test_uploaded_pcm_timing_can_stand_alone() -> None:
    parsed = parse_log_file(Path("tests/fixtures/benchmark/opentalking_timing.txt"))

    summary = summarize_events([], parsed["uploaded_pcm_events"], parsed["flashtalk_chunks"])
    assert summary["ttfa_ms"] == 20
    assert summary["ttfv_ms"] == 950
    assert summary["e2e_ms"] == 1850
    assert summary["first_model_return_ms"] == 930
