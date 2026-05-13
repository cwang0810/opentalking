from __future__ import annotations

from pathlib import Path

import numpy as np

from opentalking.core.types.frames import AudioChunk
from opentalking.media.frame_avatar import FrameAvatarState
from opentalking.models.wav2lip.adapter import Wav2LipAdapter, Wav2LipPrediction


def test_wav2lip_adapter_loads_preprocessed_avatar_and_renders_frames() -> None:
    root = Path(__file__).resolve().parents[2]
    adapter = Wav2LipAdapter()
    adapter.load_model("cpu")
    state = adapter.load_avatar(str(root / "examples" / "avatars" / "singer"))

    assert isinstance(state, FrameAvatarState)
    assert state.frames

    chunk = AudioChunk(
        data=np.full(16000, 2400, dtype=np.int16),
        sample_rate=16000,
        duration_ms=1000.0,
    )
    features = adapter.extract_features_for_stream(chunk, state)
    predictions = adapter.infer(features, state)

    assert features.frame_count == 30
    assert len(predictions) == 30
    assert all(isinstance(item, Wav2LipPrediction) for item in predictions)

    frame = adapter.compose_frame(state, 0, predictions[0])

    assert frame.width == state.manifest.width
    assert frame.height == state.manifest.height
    assert frame.data.shape[:2] == (state.manifest.height, state.manifest.width)


def test_wav2lip_adapter_accepts_reference_only_avatar() -> None:
    root = Path(__file__).resolve().parents[2]
    adapter = Wav2LipAdapter()
    state = adapter.load_avatar(str(root / "examples" / "avatars" / "anchor"))

    assert len(state.frames) == 1

    chunk = AudioChunk(
        data=np.zeros(1600, dtype=np.int16),
        sample_rate=16000,
        duration_ms=100.0,
    )
    features = adapter.extract_features_for_stream(chunk, state)
    prediction = adapter.infer(features, state)[0]
    frame = adapter.compose_frame(state, 0, prediction)

    assert frame.width == state.manifest.width
    assert frame.height == state.manifest.height
