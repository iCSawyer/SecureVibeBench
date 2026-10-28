# 模型生成与评估

从 HF 下载 Harbor 任务和同包原版评估器，使用官方 mini-swe-agent 生成代码，再由 Harbor 执行评估。任务指令、测试和 benchmark 判分逻辑保持不变。

## 运行

需要 [uv](https://docs.astral.sh/uv/getting-started/installation/)、Git、Docker daemon、Docker Compose，以及模型 provider 的 API 凭据。uv 会准备 Python 3.12 和锁定依赖。在仓库根目录执行：

```bash
export OPENAI_API_KEY='<your-api-key>'
bash evaluation/run.sh '<provider/model>' --task 992
```

按 provider 改用对应的凭据变量，例如 `ANTHROPIC_API_KEY`。每次运行先按 `uv.lock` 同步依赖；首次会下载官方 mini-swe-agent `2.4.6` 到 `evaluation/mini-swe-agent/`，在宿主与任务容器中以 editable 模式安装。已有源码及本地修改会保留。环境、缓存和结果均放在被 Git 忽略的 `dev/` 中。

`--task` 可重复；省略时运行全部 105 个任务。默认并发和每任务尝试次数均为 1。其他常用参数：

| 参数 | 用途 |
| --- | --- |
| `--base-url URL` | 自定义模型端点，需能从 Docker 容器访问 |
| `--api-key-name NAME` | 保存 API key 的环境变量名 |
| `--api-format FORMAT` | `openai_chat_completions`、`openai_responses` 或 `anthropic_messages` |
| `--env-file PATH` | 加载凭据；已有环境变量优先 |
| `--n-concurrent N` / `--attempts N` | 并发数 / 每任务尝试次数 |
| `--step-limit N` / `--cost-limit N` | 模型步数 / 费用上限，费用 `0` 表示不限 |
| `--print-config` | 下载并校验 HF 包、打印配置，不调用模型或 Docker |

完整参数见 `bash evaluation/run.sh --help`。

## 数据与结果

默认来源为 [iCSawyer/SecureVibeBench 的 `habour-preview` 分支](https://huggingface.co/datasets/iCSawyer/SecureVibeBench/tree/habour-preview)。入口固定本次下载的 commit 并校验任务和评估器；根目录 `data/` 只作格式示例。HF 原默认数据与现有 `load_dataset("iCSawyer/SecureVibeBench")` 调用保持兼容。

最终结果位于 `dev/runs/<job>/summary.json`，终端也会打印。汇总直接保留 Harbor 原指标：`functional` 和 `security` 独立显示，并列出错误计数，不新增综合分数，也不为缺失结果补分。同目录包含原始 `result.json`、产物索引 `index.jsonl`，以及各 trial 的轨迹、补丁和原始评估报告。

功能测试、PoV 和 SAST 默认继承 HF 包配置。SAST 需要原流程的 Semgrep 配置及 `SEMGREP_APP_TOKEN` 等凭据；可用 `--run-sast FALSE` 关闭本次 SAST。SAST 原始结果保留，不额外定义评分。

## mini-swe-agent 与 uv

两者兼容。旧 ARVO 镜像的 glibc 较老，部分新依赖缺少匹配 wheel，源码构建会要求 Rust 等工具。安装适配只处理依赖：先选择兼容 wheel，再单独安装 editable mini-swe-agent 源码；生成逻辑使用 Harbor 官方集成，benchmark 评估逻辑保持原样。
