# QuickTalk

## Support Status

| Item | Value |
|------|-------|
| Model ID | `quicktalk` |
| Backend | `local` |
| Evidence level | Built in, verified |
| Best for | Local realtime adapter, development reference, QuickTalk asset validation |

## Recommended Hardware

Local CUDA GPU. Validate `mock` first, then connect QuickTalk assets and a template video.

## Weights

QuickTalk assets are consumed by the local adapter. OpenTalking does not host the download
source. Prepare an asset bundle with `hdModule` and point configuration or the avatar
manifest to it.

## Directory Layout

```text
$OMNIRT_MODEL_ROOT/quicktalk/hdModule/
└── checkpoints/
    ├── 256.onnx
    ├── repair.npy
    ├── chinese-hubert-large/
    └── auxiliary_min/ or auxiliary/
```

## Configuration

```env title=".env"
OPENTALKING_QUICKTALK_ASSET_ROOT=/absolute/path/to/models/quicktalk/hdModule
OPENTALKING_QUICKTALK_TEMPLATE_VIDEO=/absolute/path/to/template.mp4
OPENTALKING_QUICKTALK_WORKER_CACHE=1
OPENTALKING_TORCH_DEVICE=cuda:0
```

Avatar manifest:

```json title="manifest.json"
{
  "model_type": "quicktalk",
  "metadata": {
    "asset_root": "/absolute/path/to/models/quicktalk/hdModule",
    "template_video": "/absolute/path/to/template.mp4"
  }
}
```

## Start

```bash title="Terminal"
OPENTALKING_QUICKTALK_BACKEND=local bash scripts/quickstart/start_all.sh
```

## `/models` Verification

```bash title="Terminal"
curl -s http://127.0.0.1:8000/models | jq '.statuses[] | select(.id=="quicktalk")'
```

Expected:

```json
{"id":"quicktalk","backend":"local","connected":true,"reason":"local_runtime"}
```

## Common Errors

| Symptom | Action |
|---------|--------|
| `connected=false` | Check QuickTalk dependencies, asset paths, and `OPENTALKING_TORCH_DEVICE`. |
| Long first turn | Enable `OPENTALKING_QUICKTALK_WORKER_CACHE=1`. |
| Avatar load failure | `asset_root` and `template_video` must be reachable absolute paths. |
