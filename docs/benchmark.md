# Benchmark

本文是 OpenTalking 的可发布基准测试页。公开页面只使用脱敏后的硬件标签，不出现内部机器编号、内网地址、账号、个人目录或临时绝对路径。每个已发布数字都必须能追溯到本地 `summary.json` / `summary.csv` 和原始日志。

## 测试范围

Benchmark 分两层：

- **模型层**：只测 audio2video / talking-head 模型服务的延迟、吞吐和资源占用。
- **端到端**：测 OpenTalking API + LLM + TTS + 数字人生成 + WebRTC 媒体队列。

硬件标签如下：

| 标签 | 硬件 | 后端 | 用途 |
| --- | --- | --- | --- |
| `cuda-1x3090` | 1x RTX 3090 | CUDA | GPU 单卡模型层测试 |
| `cuda-8x3090` | 8x RTX 3090 | CUDA | GPU 模型层和端到端测试 |
| `ascend-1x910b` | 1x Ascend 910B | Ascend | NPU 单卡模型层测试 |
| `ascend-8x910b` | 8x Ascend 910B | Ascend | NPU 模型服务测试 |
| `cuda-to-ascend` | OpenTalking API + Ascend 模型服务 | CUDA + Ascend | 跨后端端到端测试 |

原始日志放在 `outputs/benchmark/<run-id>/`。公开文档只引用 repo 内相对路径，并且路径名也使用脱敏标签。

## 指标定义

| 指标 | 含义 | 日志来源 |
| --- | --- | --- |
| `TTFA` | OpenTalking 首个音频块进入处理链路的时间 | `first_chunk_queued_ms` / `first_chunk_ms` |
| `TTFV` | 首个视频帧或 WebRTC 媒体进入队列的时间 | `first_webrtc_queue_ms` / `first_webrtc_ms` / `first_frame_from_api_wall_ms` |
| `E2E latency` | 用户请求到首个可播放媒体的端到端延迟 | `first_frame_from_api_wall_ms` 或 wrapper wall time |
| `First model return` | audio2video 模型首个 chunk 返回时间 | `first_flashtalk_return_ms` / `first_ft_ms` |
| `Steady FPS` | 生成帧数除以模型等待时间 | `FlashTalk WS chunk` 日志 |
| `VRAM/HBM peak` | GPU 显存或 Ascend HBM 峰值 | `nvidia-smi` / `npu-smi info` 采样 |
| `Drop frame rate` | 长稳测试中的丢帧比例 | browser/WebRTC stats 或服务端队列计数 |

冷启动数据包含服务启动、模型加载和首个请求；热态数据要求服务已启动并至少完成一次 warmup。

## 采集方式

每个硬件/后端组合使用独立目录：

```bash
mkdir -p outputs/benchmark/20260513-cuda-8x3090
mkdir -p outputs/benchmark/20260513-ascend-8x910b
mkdir -p outputs/benchmark/20260513-cuda-to-ascend-8x910b
```

### 模型层

QuickTalk 使用已有 CLI：

```bash
python scripts/benchmark/collect_model_bench.py quicktalk \
  --output-dir outputs/benchmark/20260513-cuda-8x3090 \
  --host cuda-8x3090 \
  --backend cuda \
  --device-count 1 \
  --model quicktalk \
  --cold-or-warm warm \
  --asset-root /path/to/quicktalk/assets \
  --template-video /path/to/template.mp4 \
  --audio /path/to/benchmark.wav \
  --video-output outputs/benchmark/20260513-cuda-8x3090/quicktalk.mp4 \
  --device cuda:0
```

OmniRT 或常驻模型服务先 smoke `/models`，真实生成后再解析日志：

```bash
python scripts/benchmark/collect_model_bench.py endpoint-smoke \
  --output-dir outputs/benchmark/20260513-ascend-8x910b \
  --host ascend-8x910b \
  --backend ascend \
  --device-count 8 \
  --model flashtalk \
  --cold-or-warm warm \
  --endpoint http://127.0.0.1:9000

python scripts/benchmark/collect_model_bench.py log \
  --output-dir outputs/benchmark/20260513-ascend-8x910b \
  --host ascend-8x910b \
  --backend ascend \
  --device-count 8 \
  --model flashtalk \
  --cold-or-warm warm \
  --raw-log outputs/benchmark/20260513-ascend-8x910b/omnirt-flashtalk.log
```

### 端到端

在 GPU 主机运行 OpenTalking，并指向本地 CUDA OmniRT 或远端 Ascend 模型服务：

```bash
OMNIRT_ENDPOINT=http://<ascend-model-host>:9000 \
bash scripts/quickstart/start_opentalking.sh --api-port 8017
```

固定 prompt、avatar、TTS/LLM provider 后执行一次请求，并解析 API 日志：

```bash
python scripts/benchmark/collect_e2e_bench.py \
  --api-base http://127.0.0.1:8017 \
  --output-dir outputs/benchmark/20260513-cuda-to-ascend-8x910b \
  --host cuda-to-ascend \
  --backend ascend \
  --device-count 8 \
  --model flashtalk \
  --avatar-id singer \
  --action speak \
  --text "你好，请用一句话介绍 OpenTalking 的实时数字人能力。" \
  --wait-seconds 30 \
  --log-file outputs/benchmark/20260513-cuda-to-ascend-8x910b/opentalking-api.log
```

如果请求已经执行，只是日志稍后拉回，可以只解析日志并追加 summary：

```bash
python scripts/benchmark/collect_e2e_bench.py \
  --parse-only \
  --output-dir outputs/benchmark/20260513-cuda-to-ascend-8x910b \
  --host cuda-to-ascend \
  --backend ascend \
  --device-count 8 \
  --model flashtalk \
  --action uploaded-pcm \
  --log-file outputs/benchmark/20260513-cuda-to-ascend-8x910b/opentalking-api.log
```

`--action uploaded-pcm` 只用于固定音频的模型路径控制实验，不等价于包含 LLM/TTS/browser WebRTC 的完整端到端数据。

### 稳定性

发布主路径需要：

- 至少 3 次短测，报告 p50 / p95。
- 至少 1 次 30 分钟连续会话。
- 保存 OpenTalking 日志、模型服务日志、进程表、资源采样、`summary.json` 和 `summary.csv`。
- 未测或失败项必须标为 `blocked`、`pending` 或 `not_run`，不能从结果表隐藏。

Ascend 路径如果包含 T5/text-cache 预处理，默认使用单张 NPU 做 T5/text-cache，不使用 CPU T5 作为 benchmark 数据。

## 结果

用下面命令从 summary 文件刷新表格：

```bash
python scripts/benchmark/render_report.py \
  --summary-json outputs/benchmark/<run-id>/summary.json \
  --output docs/benchmark.md \
  --replace-marker
```

<!-- BENCHMARK_RESULTS_START -->
## GPU / CUDA 结果

| host | backend | device_count | model | mode | cold_or_warm | status | ttfa_ms | ttfv_ms | e2e_ms | steady_fps | first_model_return_ms | model_generate_ms_p50 | model_generate_ms_p95 | resource_peak_vram_or_hbm_gb | drop_frame_rate | raw_log_path |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cuda-1x3090 | cuda | 1 | quicktalk | model-only hot generation | warm | completed | - | 17.43 | - | 53.43 | 17.43 | 3587.86 | 3621.76 | - | - | outputs/benchmark/20260513-cuda-1x3090/raw/quicktalk_fps_summary.json |
| cuda-1x3090 | cuda | 1 | musetalk | speak pipeline control | warm | completed | 1390 | 2208 | 2209 | 28.68 | 2208 | 785 | 1157.5 | 5.06 | - | outputs/benchmark/20260513-cuda-1x3090-musetalk/raw/opentalking_8019_musetalk.log |
| cuda-1x3090 | cuda | 1 | wav2lip | speak pipeline control | warm | completed | 1413 | 3549 | 3550 | 10.17 | 3549 | 2390 | 3902.5 | 7.93 | - | outputs/benchmark/20260513-cuda-1x3090-wav2lip/raw/opentalking_8021_wav2lip_allowed.log |
| cuda-8x3090 | cuda | 8 | musetalk | model-only endpoint smoke | warm | completed | - | - | - | - | 167.35 | - | - | - | - | - |
| cuda-8x3090 | cuda | 8 | wav2lip | model-only endpoint smoke | warm | completed | - | - | - | - | 93.94 | - | - | - | - | - |
| cuda-8x3090 | cuda | 8 | quicktalk / wav2lip / musetalk | full generation + browser WebRTC | warm | pending | - | - | - | - | - | - | - | - | - | outputs/benchmark/20260513-cuda-8x3090/raw/nvidia_smi_after.csv |

## NPU / Ascend 结果

| host | backend | device_count | model | mode | cold_or_warm | status | ttfa_ms | ttfv_ms | e2e_ms | steady_fps | first_model_return_ms | model_generate_ms_p50 | model_generate_ms_p95 | resource_peak_vram_or_hbm_gb | drop_frame_rate | raw_log_path |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ascend-8x910b | ascend | 8 | flashtalk | model-only WS chunks | warm | completed | - | - | - | 24.87 | 1180 | 1120 | 1157 | 52.69 | - | outputs/benchmark/20260513-ascend-8x910b/raw/flashtalk_8765.log |
| ascend-1x910b | ascend | 1 | flashtalk | model-only WS chunks | warm | completed | - | - | - | 5.44 | 5183 | 5140 | 5150 | 54.78 | - | outputs/benchmark/20260513-ascend-1x910b/raw/flashtalk_8766_1x_single_rank.log |
| cuda-to-ascend-1x | ascend | 1 | flashtalk | uploaded PCM control | warm | completed | 0 | 5183 | 15543 | 5.44 | 5183 | 5140 | 5150 | 54.78 | - | outputs/benchmark/20260513-cuda-to-ascend-1x910b/raw/opentalking_8018_1x.log |
| cuda-to-ascend | ascend | 8 | flashtalk | uploaded PCM control | warm | completed | 0 | 1180 | 3484 | 24.87 | 1180 | 1120 | 1157 | 52.69 | - | outputs/benchmark/20260513-cuda-to-ascend-8x910b/raw/opentalking_8017_current.log |
| cuda-to-ascend | ascend | 8 | flashtalk | text speak with TTS | warm | blocked | - | - | - | - | - | - | - | - | - | outputs/benchmark/20260513-cuda-to-ascend-8x910b/raw/opentalking_8017_current.log |
| cuda-to-ascend | ascend | 8 | flashtalk | 30-minute stability | warm | pending | - | - | - | - | - | - | - | - | - | - |
<!-- BENCHMARK_RESULTS_END -->

2026-05-13 实测说明：

- 本次补充了 GPU 单卡 QuickTalk 热态生成数据，取历史单卡 FPS benchmark 的 hot runs 3-6。
- GPU 单卡 `musetalk` / `wav2lip` 已补充 OpenTalking speak pipeline 控制实验。该控制实验中 LLM 未配置，系统 fallback 文本驱动 Edge TTS 和模型生成；表中的 `model_generate_ms_*` 与 `steady_fps` 来自真实 WS chunk。
- `wav2lip` 单卡测试需要使用 OmniRT endpoint 白名单内的 avatar root；第一次使用临时同步目录触发 `ref_frame_dir is outside allowed frame roots`，已保留原始失败日志但不作为结果表数据。
- Ascend 单卡 FlashTalk 需要单 rank 兼容 guard：单卡路径中的 broadcast/HCCL 调用需要在 `WORLD_SIZE=1` 时 no-op；修正后 uploaded PCM 控制实验完成。
- 本次有真实 8 卡 GPU endpoint smoke 和 8 卡 Ascend FlashTalk warm-path 数据。
- Ascend FlashTalk 启动完成后进行了 warmup，模型服务进入常驻 WebSocket 模式。
- 完成的端到端行是 uploaded PCM 控制实验：它验证了 OpenTalking API 调用 Ascend FlashTalk 的链路，但不包含 LLM、TTS 或真实浏览器 WebRTC receiver。
- 文本 `/speak` 链路本次被标为 `blocked`：请求进入后 session readiness 与 worker 队列没有对齐，没有产生可发布的 TTS/模型 timing。

## 发布检查

- [ ] 运行前确认 GPU / NPU 资源空闲度。
- [ ] 保存 OpenTalking commit、OmniRT commit、模型版本和配置 hash。
- [ ] 保存原始日志到 `outputs/benchmark/<run-id>/`。
- [ ] 冷启动和热态数据分开标注。
- [ ] 失败、阻塞、未测项保留在结果表中。
- [ ] 发布前扫描文档，确认没有账号、内网地址、内部机器编号、个人目录或临时绝对路径。
