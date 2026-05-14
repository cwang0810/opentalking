from __future__ import annotations

import io
import sys
import types
from pathlib import Path

import numpy as np
from PIL import Image

from opentalking.core.types.frames import AudioChunk
from opentalking.media.frame_avatar import FrameAvatarState
from opentalking.models.wav2lip.adapter import Wav2LipAdapter, Wav2LipPrediction


def _install_fake_omnirt(monkeypatch) -> type:
    root_mod = types.ModuleType("omnirt")
    models_mod = types.ModuleType("omnirt.models")
    wav2lip_mod = types.ModuleType("omnirt.models.wav2lip")
    runtime_mod = types.ModuleType("omnirt.models.wav2lip.runtime")
    server_mod = types.ModuleType("omnirt.server")
    realtime_mod = types.ModuleType("omnirt.server.realtime_avatar")

    class AvatarAudioSpec:
        def __init__(self, sample_rate=16000, channels=1, chunk_samples=14933):
            self.sample_rate = sample_rate
            self.channels = channels
            self.chunk_samples = chunk_samples

    class AvatarVideoSpec:
        def __init__(
            self,
            fps=25,
            width=416,
            height=704,
            frame_count=29,
            motion_frames_num=1,
            slice_len=28,
        ):
            self.fps = fps
            self.width = width
            self.height = height
            self.frame_count = frame_count
            self.motion_frames_num = motion_frames_num
            self.slice_len = slice_len

    class RealtimeAvatarSession:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class RealtimeAvatarService:
        def __init__(self, *, runtime=None, allowed_frame_roots=None):
            self.runtime = runtime
            self.allowed_frame_roots = allowed_frame_roots
            self.created = []

        def create_session(self, *, model, backend, image_bytes, prompt="", config=None):
            config = dict(config or {})
            width = int(config.get("width", 416))
            height = int(config.get("height", 704))
            max_long_edge = int(__import__("os").environ.get("OMNIRT_WAV2LIP_MAX_LONG_EDGE", "0") or "0")
            if model == "wav2lip" and max_long_edge > 0 and max(width, height) > max_long_edge:
                scale = max_long_edge / float(max(width, height))
                width = max(2, int(round(width * scale)))
                height = max(2, int(round(height * scale)))
                width -= width % 2
                height -= height % 2
            session = RealtimeAvatarSession(
                session_id="fake_session",
                trace_id="fake_trace",
                model=model,
                backend=backend,
                prompt=prompt,
                image_bytes=image_bytes,
                reference_mode=config.get("reference_mode", "image"),
                ref_frame_dir=config.get("ref_frame_dir"),
                ref_frame_metadata_path=config.get("ref_frame_metadata_path"),
                audio=AvatarAudioSpec(
                    sample_rate=int(config.get("sample_rate", 16000)),
                    channels=1,
                    chunk_samples=28 * int(config.get("sample_rate", 16000)) // int(config.get("fps", 25)),
                ),
                video=AvatarVideoSpec(
                    fps=int(config.get("fps", 25)),
                    width=width,
                    height=height,
                    frame_count=29,
                    motion_frames_num=1,
                    slice_len=28,
                ),
                wav2lip_postprocess_mode=config.get("wav2lip_postprocess_mode", "easy_improved"),
                preprocessed=bool(config.get("preprocessed")),
                mouth_metadata=config.get("mouth_metadata", {}),
            )
            self.created.append(session)
            return session

    def encode_jpeg_sequence(jpeg_frames):
        payload = bytearray(b"VIDX")
        payload.extend(len(jpeg_frames).to_bytes(4, "little"))
        for frame in jpeg_frames:
            payload.extend(len(frame).to_bytes(4, "little"))
            payload.extend(frame)
        return bytes(payload)

    def decode_jpeg_sequence(payload):
        assert payload[:4] == b"VIDX"
        count = int.from_bytes(payload[4:8], "little")
        offset = 8
        frames = []
        for _ in range(count):
            size = int.from_bytes(payload[offset : offset + 4], "little")
            offset += 4
            frames.append(payload[offset : offset + size])
            offset += size
        return frames

    class Prepared:
        def __init__(self, frame):
            self.base_frame = frame

    class State:
        def __init__(self, frame):
            self.frame = frame

        def frame_at(self, _index):
            return Prepared(self.frame)

    class Wav2LipRealtimeRuntime:
        instances = []

        def __init__(self, device="cpu"):
            self.device = device
            self.sessions = []
            self.rendered = []
            Wav2LipRealtimeRuntime.instances.append(self)

        def _session_state(self, session):
            self.sessions.append(session)
            frame = np.zeros((session.video.height, session.video.width, 3), dtype=np.uint8)
            return State(frame)

        def render_chunk(self, session, pcm_s16le):
            self.rendered.append((session, pcm_s16le))
            frames = []
            for value in (32, 96):
                image = Image.new("RGB", (session.video.width, session.video.height), (value, 8, 4))
                buffer = io.BytesIO()
                image.save(buffer, format="JPEG")
                frames.append(buffer.getvalue())
            return encode_jpeg_sequence(frames)

    realtime_mod.AvatarAudioSpec = AvatarAudioSpec
    realtime_mod.AvatarVideoSpec = AvatarVideoSpec
    realtime_mod.RealtimeAvatarSession = RealtimeAvatarSession
    realtime_mod.RealtimeAvatarService = RealtimeAvatarService
    realtime_mod.decode_jpeg_sequence = decode_jpeg_sequence
    runtime_mod.Wav2LipRealtimeRuntime = Wav2LipRealtimeRuntime

    monkeypatch.setitem(sys.modules, "omnirt", root_mod)
    monkeypatch.setitem(sys.modules, "omnirt.models", models_mod)
    monkeypatch.setitem(sys.modules, "omnirt.models.wav2lip", wav2lip_mod)
    monkeypatch.setitem(sys.modules, "omnirt.models.wav2lip.runtime", runtime_mod)
    monkeypatch.setitem(sys.modules, "omnirt.server", server_mod)
    monkeypatch.setitem(sys.modules, "omnirt.server.realtime_avatar", realtime_mod)
    return Wav2LipRealtimeRuntime


def test_wav2lip_adapter_uses_omnirt_runtime_and_preprocessed_metadata(monkeypatch) -> None:
    fake_runtime = _install_fake_omnirt(monkeypatch)
    monkeypatch.setenv("OMNIRT_WAV2LIP_MAX_LONG_EDGE", "768")
    root = Path(__file__).resolve().parents[2]
    adapter = Wav2LipAdapter()
    adapter.load_model("cpu")
    state = adapter.load_avatar(str(root / "examples" / "avatars" / "singer"))

    assert not isinstance(state, FrameAvatarState)
    session = fake_runtime.instances[-1].sessions[-1]
    assert session.reference_mode == "frames"
    assert session.preprocessed is True
    assert session.ref_frame_dir.endswith("examples/avatars/singer/frames")
    assert session.ref_frame_metadata_path.endswith("examples/avatars/singer/frames/mouth_metadata.json")
    assert session.wav2lip_postprocess_mode == "easy_improved"
    assert session.video.width == 574
    assert session.video.height == 768
    assert session.video.fps == 30

    chunk = AudioChunk(
        data=np.full(1600, 2400, dtype=np.int16),
        sample_rate=16000,
        duration_ms=100.0,
    )
    features = adapter.extract_features_for_stream(chunk, state)
    predictions = adapter.infer(features, state)

    assert fake_runtime.instances[-1].rendered[-1][1] == chunk.data.tobytes()
    assert len(predictions) == 2
    assert all(isinstance(item, Wav2LipPrediction) for item in predictions)

    frame = adapter.compose_frame(state, 0, predictions[0])

    assert frame.width == session.video.width
    assert frame.height == session.video.height
    assert frame.data.shape[:2] == (session.video.height, session.video.width)


def test_wav2lip_adapter_accepts_reference_only_avatar_with_omnirt(monkeypatch) -> None:
    _install_fake_omnirt(monkeypatch)
    root = Path(__file__).resolve().parents[2]
    adapter = Wav2LipAdapter()
    adapter.load_model("cpu")
    state = adapter.load_avatar(str(root / "examples" / "avatars" / "anchor"))

    assert not isinstance(state, FrameAvatarState)
    assert state.session.reference_mode == "image"

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


def test_wav2lip_adapter_legacy_fallback_is_explicit(monkeypatch) -> None:
    monkeypatch.setenv("OPENTALKING_WAV2LIP_LEGACY_LOCAL_FALLBACK", "1")
    root = Path(__file__).resolve().parents[2]
    adapter = Wav2LipAdapter()
    state = adapter.load_avatar(str(root / "examples" / "avatars" / "singer"))

    assert isinstance(state, FrameAvatarState)
    assert state.frames
