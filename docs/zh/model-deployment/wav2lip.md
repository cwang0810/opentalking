# Wav2Lip

## 支持状态

| 项 | 值 |
|----|----|
| 模型 ID | `wav2lip` |
| Backend | 当前可运行路径为 `omnirt`；目标方向是 local-first |
| 证据等级 | OmniRT 路径已验证；本地 adapter 仍在补齐中 |
| 推荐用途 | 第一个真实 talking-head 模型、轻量唇形同步 |

## 推荐硬件

单张 NVIDIA 3090 级 GPU 或 Ascend 910B 评估环境。`mock` 通过后再切换到 Wav2Lip。

## 权重下载

Hugging Face 主源：

- [Pypa/wav2lip384](https://huggingface.co/Pypa/wav2lip384)
- [rippertnt/wav2lip](https://huggingface.co/rippertnt/wav2lip)

```bash title="终端"
mkdir -p "$OMNIRT_MODEL_ROOT/wav2lip"
hf download Pypa/wav2lip384 wav2lip384.pth --local-dir "$OMNIRT_MODEL_ROOT/wav2lip"
hf download rippertnt/wav2lip s3fd.pth --local-dir "$OMNIRT_MODEL_ROOT/wav2lip"
```

国内可搜索 ModelScope 或魔乐社区的 `wav2lip384`、`s3fd wav2lip`。

## 目录结构

```text
$OMNIRT_MODEL_ROOT/wav2lip/
├── wav2lip384.pth
└── s3fd.pth
```

## 配置项

当前可运行兼容路径：

```yaml title="configs/default.yaml"
models:
  wav2lip:
    backend: omnirt
```

目标 local-first 路径在本地 adapter 补齐后使用：

```yaml title="configs/default.yaml"
models:
  wav2lip:
    backend: local
```

## 启动命令

```bash title="终端"
bash scripts/quickstart/start_omnirt_wav2lip.sh --device cuda
bash scripts/quickstart/start_all.sh --omnirt http://127.0.0.1:9000
```

Ascend 评估：

```bash title="终端"
source /usr/local/Ascend/ascend-toolkit/set_env.sh
bash scripts/deploy_ascend_910b.sh
```

## `/models` 验证

```bash title="终端"
curl -s http://127.0.0.1:8000/models | jq '.statuses[] | select(.id=="wav2lip")'
```

期望：

```json
{"id":"wav2lip","backend":"omnirt","connected":true,"reason":"omnirt"}
```

## 常见错误

| 现象 | 处理 |
|------|------|
| checkpoint 缺失 | 确认 `wav2lip384.pth` 与 `s3fd.pth` 位于 `$OMNIRT_MODEL_ROOT/wav2lip/`。 |
| `reason=not_configured` | 配置 `OMNIRT_ENDPOINT` 或用 `start_all.sh --omnirt ...`。 |
| `reason=local_adapter_missing` | 当前本地 adapter 未补齐，切回 `backend: omnirt`。 |
| 会话创建失败 | 选择 `model_type: wav2lip` 的 avatar。 |
