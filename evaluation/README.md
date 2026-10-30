# Model Generation and Evaluation

Download Harbor tasks and their original evaluator from Hugging Face, generate code with official mini-swe-agent, and run evaluation through Harbor. Task instructions, tests, and benchmark scoring remain unchanged.

## Prepare the Environment and Dataset

Install Python 3.8+ (available as `python3`) and Git. From the repository root, run:

```bash
bash evaluation/prepare.sh
```

The script first downloads and verifies the complete HF task bundle and evaluator using only the system Python standard library. Installation proceeds only after the download and verification succeed. The script then installs uv into `dev/tools/uv/` if needed (using curl or wget), automatically clones official mini-swe-agent `v2.4.6`, and uses uv to prepare Python 3.12 and locked dependencies, including editable mini-swe-agent. The system Python only bootstraps the dataset download; uv manages the project environment and dependencies. Installation requires no sudo and does not modify shell profiles. Preparation requires no model API key and does not start task containers or call a model.

Use `--hf-repo`, `--hf-revision`, and `--cache-dir` to select the dataset source and cache location. For example:

```bash
bash evaluation/prepare.sh --hf-revision habour-preview
```

The default HF cache is `dev/cache/huggingface/`. Subsequent runs reuse cached files but still contact HF to resolve the selected revision to its current commit. Use the `HF_TOKEN` environment variable to authenticate for private or gated datasets. Pass the same dataset and cache options to `run.sh` when using a custom source or cache.

Install Git, Docker Engine, and Docker Compose using your system's installation method. The script checks Docker, Compose, and daemon access and reports any missing requirements. Dataset preparation can complete without Docker; before evaluation, start the daemon and ensure your user can access it.

## Run Evaluation

After preparation, configure your model provider's API credentials and run:

```bash
export OPENAI_API_KEY='<your-api-key>'
bash evaluation/run.sh '<provider/model>' --task 992
```

Use the credential variable required by your provider, such as `ANTHROPIC_API_KEY`. Each run synchronizes dependencies against `uv.lock`. If the official mini-swe-agent source is missing, setup clones version `2.4.6` into `evaluation/mini-swe-agent/`. It is installed in editable mode on the host and inside task containers. Existing source and local edits are preserved. Environments, caches, and results are stored in the gitignored `dev/` directory.

Repeat `--task` to select multiple tasks, or omit it to run all 105 tasks. Concurrency and attempts per task both default to 1. Common options:

| Option | Purpose |
| --- | --- |
| `--base-url URL` | Custom model endpoint, reachable from Docker containers |
| `--api-key-name NAME` | Name of the environment variable containing the API key |
| `--api-format FORMAT` | `openai_chat_completions`, `openai_responses`, or `anthropic_messages` |
| `--env-file PATH` | Load credentials; existing environment variables take precedence |
| `--n-concurrent N` / `--attempts N` | Concurrency / attempts per task |
| `--step-limit N` / `--cost-limit N` | Agent step limit / cost limit; a cost limit of `0` is unlimited |
| `--print-config` | Download and verify the HF bundle and print the configuration without calling a model or Docker |

See `bash evaluation/run.sh --help` for all options.

## Dataset and Results

The default source is the [`habour-preview` branch of iCSawyer/SecureVibeBench](https://huggingface.co/datasets/iCSawyer/SecureVibeBench/tree/habour-preview). The entry point pins the downloaded commit and verifies the tasks and evaluator. The root `data/` directory contains a format example. The original HF default dataset remains compatible with existing `load_dataset("iCSawyer/SecureVibeBench")` calls.

Final results are saved to `dev/runs/<job>/summary.json` and printed in the terminal. The summary preserves Harbor's metrics: `functional` and `security` are reported independently alongside error counts. It adds no aggregate score and does not substitute scores for missing results. The same job directory contains the original `result.json`, the artifact index `index.jsonl`, and each trial's trajectories, patches, and original evaluation reports.

Functional tests, PoV checks, and SAST inherit the HF bundle's defaults. SAST requires the original workflow's Semgrep configuration and credentials such as `SEMGREP_APP_TOKEN`. Use `--run-sast FALSE` to disable SAST for a run. Original SAST results are retained without adding a separate score.

## mini-swe-agent and uv

mini-swe-agent works with uv. Older ARVO images use older glibc versions, and some newer dependencies lack compatible wheels; building them from source can require tools such as Rust. The installation adapter handles dependency compatibility by selecting compatible wheels before separately installing editable mini-swe-agent source. Generation uses Harbor's official integration, and benchmark evaluation logic remains unchanged.
