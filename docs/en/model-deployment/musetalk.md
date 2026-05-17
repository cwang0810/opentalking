# MuseTalk

## Support Status

| Item | Value |
|------|-------|
| Model ID | `musetalk` |
| Backend | `omnirt`, `direct_ws`, or future `local` |
| Evidence level | Documented; no local runtime is shipped in this repository |
| Best for | Teams with an existing MuseTalk service or a planned local adapter |

## Recommended Hardware

Single GPU or remote model service. Exact VRAM and performance depend on the MuseTalk runtime.

## Weights

Upstream sources:

- [TMElyralab/MuseTalk](https://github.com/TMElyralab/MuseTalk)
- [MuseTalk on Hugging Face](https://huggingface.co/TMElyralab/MuseTalk)
- [ModelScope search for MuseTalk](https://modelscope.cn/models?name=MuseTalk)
- [Modelers search for MuseTalk](https://modelers.cn/models?name=MuseTalk)

## Directory Layout

OpenTalking does not prescribe the MuseTalk weight directory. OmniRT or your `direct_ws`
service owns it. If a local adapter is added, document its directory there.

## Configuration

OmniRT path:

```yaml title="configs/default.yaml"
models:
  musetalk:
    backend: omnirt
```

Do not use this until a local adapter exists:

```yaml title="configs/default.yaml"
models:
  musetalk:
    backend: local
```

## Start

Point OpenTalking at an OmniRT service that exposes MuseTalk:

```bash title="Terminal"
bash scripts/quickstart/start_all.sh --omnirt http://127.0.0.1:9000
```

## `/models` Verification

```bash title="Terminal"
curl -s http://127.0.0.1:8000/models | jq '.statuses[] | select(.id=="musetalk")'
```

When OmniRT provides the model, it should report `connected=true`. If forced to `local`,
the current expected state is:

```json
{"id":"musetalk","backend":"local","connected":false,"reason":"local_adapter_missing"}
```

## Common Errors

| Symptom | Action |
|---------|--------|
| `reason=omnirt_unavailable` | Check that OmniRT reports `/v1/audio2video/musetalk`. |
| `reason=local_adapter_missing` | Switch to `omnirt`/`direct_ws`, or implement a local adapter. |
| Avatar mismatch | Use an avatar with `model_type: musetalk`. |
