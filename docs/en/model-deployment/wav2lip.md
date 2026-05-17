# Wav2Lip

## Support Status

| Item | Value |
|------|-------|
| Model ID | `wav2lip` |
| Backend | Current runnable path is `omnirt`; target direction is local-first |
| Evidence level | OmniRT path verified; local adapter still pending |
| Best for | First real talking-head model, lightweight lip sync |

## Recommended Hardware

A single NVIDIA 3090-class GPU or Ascend 910B evaluation environment. Validate `mock` first,
then switch to Wav2Lip.

## Weights

Primary Hugging Face sources:

- [Pypa/wav2lip384](https://huggingface.co/Pypa/wav2lip384)
- [rippertnt/wav2lip](https://huggingface.co/rippertnt/wav2lip)

```bash title="Terminal"
mkdir -p "$OMNIRT_MODEL_ROOT/wav2lip"
hf download Pypa/wav2lip384 wav2lip384.pth --local-dir "$OMNIRT_MODEL_ROOT/wav2lip"
hf download rippertnt/wav2lip s3fd.pth --local-dir "$OMNIRT_MODEL_ROOT/wav2lip"
```

For domestic mirrors, search ModelScope or Modelers for `wav2lip384` and `s3fd wav2lip`.

## Directory Layout

```text
$OMNIRT_MODEL_ROOT/wav2lip/
├── wav2lip384.pth
└── s3fd.pth
```

## Configuration

Current compatibility path:

```yaml title="configs/default.yaml"
models:
  wav2lip:
    backend: omnirt
```

Target local-first path after the adapter lands:

```yaml title="configs/default.yaml"
models:
  wav2lip:
    backend: local
```

## Start

```bash title="Terminal"
bash scripts/quickstart/start_omnirt_wav2lip.sh --device cuda
bash scripts/quickstart/start_all.sh --omnirt http://127.0.0.1:9000
```

Ascend evaluation:

```bash title="Terminal"
source /usr/local/Ascend/ascend-toolkit/set_env.sh
bash scripts/deploy_ascend_910b.sh
```

## `/models` Verification

```bash title="Terminal"
curl -s http://127.0.0.1:8000/models | jq '.statuses[] | select(.id=="wav2lip")'
```

Expected:

```json
{"id":"wav2lip","backend":"omnirt","connected":true,"reason":"omnirt"}
```

## Common Errors

| Symptom | Action |
|---------|--------|
| Missing checkpoint | Ensure `wav2lip384.pth` and `s3fd.pth` are under `$OMNIRT_MODEL_ROOT/wav2lip/`. |
| `reason=not_configured` | Configure `OMNIRT_ENDPOINT` or run `start_all.sh --omnirt ...`. |
| `reason=local_adapter_missing` | The local adapter is not complete yet; use `backend: omnirt`. |
| Session creation fails | Choose an avatar with `model_type: wav2lip`. |
