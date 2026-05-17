# QuickTalk

## 支持状态

| 项 | 值 |
|----|----|
| 模型 ID | `quicktalk` |
| Backend | `local` |
| 证据等级 | 已内置，已验证 |
| 推荐用途 | 本地实时 adapter、开发参考、QuickTalk 资产验证 |

## 推荐硬件

本地 CUDA GPU。`mock` 路径通过后，再接入 QuickTalk 资产包和模板视频。

## 权重下载

QuickTalk 资产由本地 adapter 使用，OpenTalking 不托管权重下载入口。准备包含 `hdModule`
的资产包，并在配置或 avatar manifest 中指向它。

## 目录结构

```text
$OMNIRT_MODEL_ROOT/quicktalk/hdModule/
└── checkpoints/
    ├── 256.onnx
    ├── repair.npy
    ├── chinese-hubert-large/
    └── auxiliary_min/ 或 auxiliary/
```

## 配置项

```env title=".env"
OPENTALKING_QUICKTALK_ASSET_ROOT=/absolute/path/to/models/quicktalk/hdModule
OPENTALKING_QUICKTALK_TEMPLATE_VIDEO=/absolute/path/to/template.mp4
OPENTALKING_QUICKTALK_WORKER_CACHE=1
OPENTALKING_TORCH_DEVICE=cuda:0
```

Avatar manifest 也应声明：

```json title="manifest.json"
{
  "model_type": "quicktalk",
  "metadata": {
    "asset_root": "/absolute/path/to/models/quicktalk/hdModule",
    "template_video": "/absolute/path/to/template.mp4"
  }
}
```

## 启动命令

```bash title="终端"
OPENTALKING_QUICKTALK_BACKEND=local bash scripts/quickstart/start_all.sh
```

## `/models` 验证

```bash title="终端"
curl -s http://127.0.0.1:8000/models | jq '.statuses[] | select(.id=="quicktalk")'
```

期望：

```json
{"id":"quicktalk","backend":"local","connected":true,"reason":"local_runtime"}
```

## 常见错误

| 现象 | 处理 |
|------|------|
| `connected=false` | 检查 QuickTalk 依赖、资产路径和 `OPENTALKING_TORCH_DEVICE`。 |
| 首轮等待较长 | 开启 `OPENTALKING_QUICKTALK_WORKER_CACHE=1`。 |
| Avatar 加载失败 | manifest 中 `asset_root`、`template_video` 必须是可访问绝对路径。 |
