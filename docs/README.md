# Usage Guide

Requirements: Python 3.12+, Linux x86_64, Docker Engine with Compose, and a running Docker daemon. We recommend [uv](https://docs.astral.sh/uv/getting-started/installation/); pip also works. uv is not a host package dependency.

## Install

```bash
# Run in an isolated environment managed by uv
uvx securevibebench --help

# Or install into an active virtual environment
uv pip install securevibebench

# Or use pip
pip install securevibebench
```

Create a virtual environment first if needed: `uv venv` or `python -m venv .venv`, then `source .venv/bin/activate`.

Installation downloads the pinned 105-task dataset and original evaluator from Hugging Face. mini-swe-agent is installed inside task containers when evaluation starts; it is not installed on the host. Docker images and container tools are prepared automatically.

## Source installation and development

From a source checkout:

```bash
python tools/install.py
```

The installer uses uv when available, otherwise the current Python's pip. Use `--installer pip` to choose pip explicitly.

For editable source and development tools:

```bash
uv sync
# Or with pip, in an active virtual environment
python tools/install.py --dev --installer pip
```

The uv path creates `.venv`; activate it with `source .venv/bin/activate`. The pip path installs into the current environment.

## Evaluate

```bash
export OPENAI_API_KEY='<your-api-key>'
securevibebench eval --model 'openai/<model-name>' --task 992
```

Omit `--task 992` to run all tasks, or repeat `--task` to select several. Without a persistent install, use `uvx securevibebench eval ...`. Other providers use their own prefix and credential variable, such as `anthropic/<model-name>` and `ANTHROPIC_API_KEY`.

For an OpenAI-compatible endpoint:

```bash
export MODEL_API_KEY='<your-endpoint-api-key>'
securevibebench eval --model 'openai/<model-name>' --task 992 \
  --base-url 'http://<model-server>:8000/v1' \
  --api-key-name MODEL_API_KEY \
  --api-format openai_chat_completions
```

The endpoint must be reachable from task containers. Set the key to `unused` if authentication is disabled. SAST is disabled by default. To enable it, pass `--run-sast TRUE` and provide Semgrep configuration and credentials such as `SEMGREP_APP_TOKEN`. See `securevibebench eval --help` for options.

## Agent installation cache

Each task container needs uv, a managed Python, and mini-swe-agent. The first task downloads and installs them, then saves the result to `.cache/securevibebench/agent-toolchain/` in the current working directory; later tasks restore that archive instead of downloading again (about 25 seconds instead of several minutes). Archives are keyed by the container's `$HOME`, CPU architecture, and C library, so images that cannot share one get their own. If a restore fails, the task installs from scratch. Delete the directory to force a fresh install.

## Interrupt and resume

Progress is printed as one line per task phase. Ctrl-C, `SIGTERM`, or `SIGHUP` stops the run, removes its task and evaluator containers, and keeps finished tasks in `summary.json` (`"status": "interrupted"`). Continue later with the saved settings; finished tasks are not rerun:

```bash
securevibebench eval --resume runs/<job>
```

Resuming also removes containers left by a run that was killed outright (for example with `SIGKILL`).

## Results

Results are written to `runs/<job>/summary.json` under the current working directory, alongside trajectories, patches, and original reports. The summary is updated after every finished task. Functional and PoV security scores remain independent and retain the original scoring rules.

Since v0.2.1 the functional-test parser reads parallel `ctest -j` output per test. The Wireshark tasks interleave output from concurrent tests, and the original parser could pair a test with another test's status, misreporting passes and failures. Functional results for those tasks can therefore differ from v0.2.0 and v0.1; other tasks are unaffected. Locally cached baselines are rebuilt automatically.

Runtime caches live next to `runs/` in the current working directory: resources and functional-test baselines in `.cache/securevibebench/resources/`, and the agent toolchain in `.cache/securevibebench/agent-toolchain/`. The dataset downloaded during installation is cached in `~/.cache/securevibebench/huggingface/` (respects `XDG_CACHE_HOME`). The package's `resources.json` records upstream commits and checksums. No `dev/` directory is required.

## Developer checks

```bash
uv run python -m unittest discover -s tests -v
uv build --sdist
uv run twine check dist/*.tar.gz
```

With pip, use `python -m unittest discover -s tests -v`, `python -m build --sdist`, and `python -m twine check dist/*.tar.gz` instead. Pushing a `v<version>` tag publishes the source archive to PyPI through `.github/workflows/package.yml`. Development dependencies are installed by `tools/install.py --dev`. To refresh release resources, run `python tools/bundle_resources.py` (requires Git).
