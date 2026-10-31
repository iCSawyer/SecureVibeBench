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

Installation downloads the pinned 105-task dataset and original evaluator from Hugging Face. pip/uv installs mini-swe-agent as a dependency. Docker images and container tools are prepared when evaluation starts.

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

## Results

Results are written to `runs/<job>/summary.json` under the current working directory, alongside trajectories, patches, and original reports. Functional and PoV security scores remain independent and retain the original scoring rules.

Downloaded data is cached in `~/.cache/securevibebench/huggingface/`; installed resources are extracted to `~/.cache/securevibebench/resources/`. Both respect `XDG_CACHE_HOME`. The package's `resources.json` records upstream commits and checksums. No `dev/` directory is required.

## Developer checks

```bash
uv run python -m unittest discover -s tests -v
uv build --sdist
uv run twine check dist/*.tar.gz
```

With pip, use `python -m unittest discover -s tests -v`, `python -m build --sdist`, and `python -m twine check dist/*.tar.gz` instead. Publish the source archive (`dist/*.tar.gz`) to PyPI. Development dependencies are installed by `tools/install.py --dev`. To refresh release resources, run `python tools/bundle_resources.py` (requires Git).
