from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from opentalking.avatar.loader import load_avatar_bundle
from opentalking.core.interfaces.avatar_asset import AvatarManifest
from opentalking.core.types.frames import AudioChunk, VideoFrameData
from opentalking.media.frame_avatar import (
    FrameAvatarState,
    load_frame_avatar_state,
    numpy_bgr_to_videoframe,
    resize_reference_image_to_video,
)
from opentalking.models.registry import register_model


@dataclass
class Wav2LipFeatures:
    vector: np.ndarray
    frame_count: int
    frame_energy: np.ndarray


@dataclass(frozen=True)
class Wav2LipPrediction:
    base_frame_index: int
    openness: float


def _load_reference_frame(avatar_path: Path, manifest: AvatarManifest) -> np.ndarray:
    for name in ("reference.png", "reference.jpg", "reference.jpeg", "preview.png"):
        candidate = avatar_path / name
        if candidate.is_file():
            image = Image.open(candidate).convert("RGB")
            image = resize_reference_image_to_video(
                image,
                width=int(manifest.width),
                height=int(manifest.height),
            )
            return np.asarray(image, dtype=np.uint8)[:, :, ::-1].copy()
    raise FileNotFoundError(f"Expected reference image under {avatar_path}")


def _load_wav2lip_avatar_state(avatar_path: Path, manifest: AvatarManifest) -> FrameAvatarState:
    try:
        state = load_frame_avatar_state(avatar_path, manifest)
    except (FileNotFoundError, ValueError):
        frame = _load_reference_frame(avatar_path, manifest)
        state = FrameAvatarState(
            manifest=manifest,
            frames=[frame],
            avatar_path=avatar_path.resolve(),
            frame_paths=[],
        )
    metadata = manifest.metadata or {}
    state.extra.update(
        {
            "animation": metadata.get("animation") if isinstance(metadata.get("animation"), dict) else {},
            "idle_mode": str(metadata.get("idle_mode") or "static").strip().lower(),
            "wav2lip_prev_open": 0.0,
            "wav2lip_prev_frame_pos": 0.0,
        }
    )
    return state


def _frame_count(audio_chunk: AudioChunk, fps: float) -> int:
    pcm = np.asarray(audio_chunk.data, dtype=np.int16).reshape(-1)
    if pcm.size and audio_chunk.sample_rate > 0:
        duration_s = pcm.size / float(audio_chunk.sample_rate)
    else:
        duration_s = max(0.001, float(audio_chunk.duration_ms) / 1000.0)
    return max(1, int(np.ceil(duration_s * max(1.0, fps))))


def _frame_energy(audio_chunk: AudioChunk, frame_count: int, fps: float) -> np.ndarray:
    pcm = np.asarray(audio_chunk.data, dtype=np.int16).reshape(-1)
    if pcm.size == 0:
        return np.zeros(frame_count, dtype=np.float32)
    samples_per_frame = max(1.0, float(audio_chunk.sample_rate) / max(1.0, fps))
    energies: list[float] = []
    for idx in range(frame_count):
        start = int(round(idx * samples_per_frame))
        end = int(round((idx + 1) * samples_per_frame))
        segment = pcm[start:end]
        if segment.size == 0:
            energies.append(0.0)
            continue
        rms = float(np.sqrt(np.mean(segment.astype(np.float32) ** 2)))
        energies.append(min(1.0, rms / 3600.0))
    if not energies:
        return np.zeros(frame_count, dtype=np.float32)
    energy = np.asarray(energies, dtype=np.float32)
    peak = float(np.max(energy))
    if peak > 0.25:
        energy = np.clip(energy / peak, 0.0, 1.0).astype(np.float32)
    return energy


def _point_to_xy(point: Any, width: int, height: int) -> tuple[float, float] | None:
    if not isinstance(point, (list, tuple)) or len(point) < 2:
        return None
    try:
        return float(point[0]) * width, float(point[1]) * height
    except (TypeError, ValueError):
        return None


def _animation_center(animation: dict[str, Any], width: int, height: int) -> tuple[float, float]:
    center = _point_to_xy(animation.get("mouth_center"), width, height)
    if center is not None:
        return center
    return width * 0.5, height * 0.62


def _draw_audio_mouth(frame_bgr: np.ndarray, animation: dict[str, Any], openness: float) -> np.ndarray:
    open_amount = float(np.clip(openness, 0.0, 1.0))
    if open_amount <= 0.02:
        return frame_bgr

    height, width = frame_bgr.shape[:2]
    cx, cy = _animation_center(animation, width, height)
    rx = float(animation.get("mouth_rx") or 0.045) * width
    ry = float(animation.get("mouth_ry") or 0.018) * height
    rx = max(6.0, rx * (1.0 + 0.16 * open_amount))
    ry = max(3.0, ry * (0.7 + 3.2 * open_amount))

    rgb = Image.fromarray(frame_bgr[:, :, ::-1], mode="RGB").convert("RGBA")
    overlay = Image.new("RGBA", rgb.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    inner_points = animation.get("inner_mouth")
    polygon: list[tuple[float, float]] = []
    if isinstance(inner_points, list):
        for point in inner_points:
            xy = _point_to_xy(point, width, height)
            if xy is None:
                continue
            x, y = xy
            polygon.append((x, cy + (y - cy) * (1.0 + 3.0 * open_amount)))
    if len(polygon) >= 3:
        draw.polygon(polygon, fill=(18, 8, 10, 185))
    else:
        draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=(18, 8, 10, 185))

    highlight_y = cy - ry * 0.75
    draw.arc(
        (cx - rx * 1.06, highlight_y - ry * 0.5, cx + rx * 1.06, highlight_y + ry * 0.6),
        start=8,
        end=172,
        fill=(130, 70, 76, int(80 + 70 * open_amount)),
        width=max(1, int(min(width, height) * 0.004)),
    )
    composed = Image.alpha_composite(rgb, overlay).convert("RGB")
    return np.asarray(composed, dtype=np.uint8)[:, :, ::-1].copy()


@register_model("wav2lip")
class Wav2LipAdapter:
    """Lightweight in-process Wav2Lip-compatible adapter.

    This adapter intentionally avoids heavyweight neural checkpoints. It drives
    prepared Wav2Lip-style avatar frames, or a single reference image fallback,
    with audio-energy mouth motion so the local backend remains runnable.
    """

    model_type = "wav2lip"

    def __init__(self) -> None:
        self._device = "cpu"

    def load_model(self, device: str = "cuda") -> None:
        self._device = device

    def load_avatar(self, avatar_path: str) -> FrameAvatarState:
        bundle = load_avatar_bundle(Path(avatar_path), strict=False)
        return _load_wav2lip_avatar_state(bundle.path, bundle.manifest)

    def warmup(self) -> None:
        return None

    def extract_features(self, audio_chunk: AudioChunk) -> Wav2LipFeatures:
        fps = 25.0
        count = _frame_count(audio_chunk, fps)
        energy = _frame_energy(audio_chunk, count, fps)
        return Wav2LipFeatures(vector=energy.reshape(-1, 1), frame_count=count, frame_energy=energy)

    def extract_features_for_stream(
        self,
        audio_chunk: AudioChunk,
        avatar_state: FrameAvatarState,
    ) -> Wav2LipFeatures:
        fps = float(max(1, int(avatar_state.manifest.fps)))
        count = _frame_count(audio_chunk, fps)
        energy = _frame_energy(audio_chunk, count, fps)
        return Wav2LipFeatures(vector=energy.reshape(-1, 1), frame_count=count, frame_energy=energy)

    def infer(
        self,
        features: Wav2LipFeatures,
        avatar_state: FrameAvatarState,
    ) -> list[Wav2LipPrediction]:
        extra = avatar_state.extra
        frame_index_start = int(extra.get("frame_index_start", 0) or 0)
        prev_open = float(extra.get("wav2lip_prev_open", 0.0) or 0.0)
        predictions: list[Wav2LipPrediction] = []
        frame_total = max(1, len(avatar_state.frames))
        for offset, energy in enumerate(np.asarray(features.frame_energy, dtype=np.float32).reshape(-1)):
            target = float(np.clip(energy, 0.0, 1.0))
            prev_open = (prev_open * 0.55) + (target * 0.45)
            base_idx = (frame_index_start + offset) % frame_total
            predictions.append(
                Wav2LipPrediction(
                    base_frame_index=base_idx,
                    openness=prev_open,
                )
            )
        extra["wav2lip_prev_open"] = prev_open
        return predictions

    def compose_frame(
        self,
        avatar_state: FrameAvatarState,
        frame_idx: int,
        prediction: Any,
    ) -> VideoFrameData:
        if not isinstance(prediction, Wav2LipPrediction):
            return self.idle_frame(avatar_state, frame_idx)
        base = avatar_state.frames[prediction.base_frame_index % len(avatar_state.frames)].copy()
        animation = avatar_state.extra.get("animation")
        if isinstance(animation, dict):
            base = _draw_audio_mouth(base, animation, prediction.openness)
        return numpy_bgr_to_videoframe(base, self._timestamp_ms(avatar_state, frame_idx))

    def idle_frame(self, avatar_state: FrameAvatarState, frame_idx: int) -> VideoFrameData:
        idle_mode = str(avatar_state.extra.get("idle_mode") or "static").strip().lower()
        if idle_mode == "loop" and len(avatar_state.frames) > 1:
            frame = avatar_state.frames[frame_idx % len(avatar_state.frames)].copy()
        else:
            frame = avatar_state.frames[0].copy()
        return numpy_bgr_to_videoframe(frame, self._timestamp_ms(avatar_state, frame_idx))

    @staticmethod
    def _timestamp_ms(avatar_state: FrameAvatarState, frame_idx: int) -> float:
        fps = max(1.0, float(avatar_state.manifest.fps))
        return frame_idx * (1000.0 / fps)
