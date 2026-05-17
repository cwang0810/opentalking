# MuseTalk

## 支持状态

| 项 | 值 |
|----|----|
| 模型 ID | `musetalk` |
| Backend | `omnirt`、`direct_ws` 或后续 `local` |
| 证据等级 | 已文档化；仓库内未附带本地 runtime |
| 推荐用途 | 已有 MuseTalk 服务或准备接入本地 adapter 的团队 |

## 推荐硬件

单 GPU 或远端模型服务。具体显存与性能取决于实际 MuseTalk runtime。

## 权重下载

上游入口：

- [TMElyralab/MuseTalk](https://github.com/TMElyralab/MuseTalk)
- [MuseTalk on Hugging Face](https://huggingface.co/TMElyralab/MuseTalk)
- [ModelScope 搜索 MuseTalk](https://modelscope.cn/models?name=MuseTalk)
- [魔乐社区搜索 MuseTalk](https://modelers.cn/models?name=MuseTalk)

## 目录结构

OpenTalking 不规定 MuseTalk 权重目录；由 OmniRT 或你的 `direct_ws` 服务管理。若实现本地
adapter，再在 adapter 文档中固定目录。

## 配置项

OmniRT 路径：

```yaml title="configs/default.yaml"
models:
  musetalk:
    backend: omnirt
```

本地 adapter 未实现前，不建议使用：

```yaml title="configs/default.yaml"
models:
  musetalk:
    backend: local
```

## 启动命令

指向已提供 MuseTalk 的 OmniRT：

```bash title="终端"
bash scripts/quickstart/start_all.sh --omnirt http://127.0.0.1:9000
```

## `/models` 验证

```bash title="终端"
curl -s http://127.0.0.1:8000/models | jq '.statuses[] | select(.id=="musetalk")'
```

OmniRT 提供该模型时应返回 `connected=true`。若强制 `local`，当前预期是：

```json
{"id":"musetalk","backend":"local","connected":false,"reason":"local_adapter_missing"}
```

## 常见错误

| 现象 | 处理 |
|------|------|
| `reason=omnirt_unavailable` | 检查 OmniRT 是否报告 `/v1/audio2video/musetalk`。 |
| `reason=local_adapter_missing` | 切换到 `omnirt`/`direct_ws`，或实现本地 adapter。 |
| Avatar 不匹配 | 使用 `model_type: musetalk` 的 avatar。 |
