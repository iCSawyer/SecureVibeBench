# Image-based native Harbor evaluation

This workflow is experimental on the `habour` branch. It uses prepared images for every trial. The pinned HF task release currently covers 104 tasks; this is a subset of the 105-task benchmark. `full` means all tasks in the selected image catalog. No HF or GitHub publication is performed by these commands.

## 1. Environment installation

Requirements: Linux x86-64, Python 3.12+, Docker Engine with Compose, and permission to use Docker.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Use `pip install -e .` when working from the checkout: edits to Python source take effect without reinstalling. Reinstall after changing package metadata, dependencies, or command entry points. Use `pip install .` for a regular installation. uv is optional: `uv sync --locked` and `source .venv/bin/activate` can replace the venv and pip commands.

### Task availability

`securevibebench list` shows the complete 105-task inventory: 104 tasks have prepared image digests and 1 are temporarily unsupported. Use `--json` for structured status. `--task full` selects only supported tasks. Selecting an unsupported task fails before any pull or trial. HF `full-habour` contains only runnable tasks under `data/`; `availability.json` records all task statuses.

### Image access and offline runs

The published GHCR images are public and can be pulled without GitHub authentication. No package token or `docker login` step is required.

For a normal run, `generate` and `eval` download missing task files and images automatically. No separate preparation command is required.

For an offline run, download the selected images first:

```bash
securevibebench pull --task 992 32345
# Use --task full instead to prepare every supported task.
securevibebench eval my-submission --local-images
```

`pull` retrieves immutable registry digests and verifies each Docker image ID and platform. Its output directory contains pull logs and `images.json`. The HF release also includes a checksum-verified archive of Harbor's network policy image. Preparation caches the release and loads that image locally. This prevents Harbor from building its firewall image during a trial.

`generate` and `eval` perform the same image check before starting any trial. They pull missing images by default. Add `--local-images` to prohibit registry access and fail early if an image is missing. Images imported with `docker load` are accepted when their exact image IDs match the task contract.

No evaluation command installs OS packages, clones task repositories, or builds a task image. Image production is a separate maintainer workflow in [tools/arvo_images/README.md](../tools/arvo_images/README.md).

### Task and image contract

Full task definitions, availability, image provenance, and the shared network image archive are hosted on HF `full-habour`. `evaluation/dataset-lock.json` pins the exact HF commit, archive checksum, and manifest checksum. GitHub and the Python package contain no full task dataset. `example/` contains one task. Use `--tasks PATH` for another native image task root. A task contains:

```text
securevibebench-ID/
  instruction.md
  task.toml
  tests/test.sh
```

`task.toml` declares an immutable registry digest, its expected Docker config ID, platform, and agents whose offline setup was verified. The image contains the starting source snapshot, compiler dependencies, test runtime, and reference baseline. Original repository history is removed during image production. A new one-commit repository supplies `svb-start` for patch collection and replay.

A task cannot provide a Dockerfile as a fallback. Trial definitions are copied to the run directory, where the registry reference is replaced with the verified local image ID. Host DNS and CPU placement are configured in this copy. Cached task definitions remain unchanged. All selected tasks are checked before a generation job starts.

The default task cache is `$XDG_CACHE_HOME/securevibebench/datasets/<revision>/data`, or `~/.cache/securevibebench/datasets/<revision>/data` when XDG_CACHE_HOME is unset.

`pip install .` and `pip install -e .` download the pinned HF release during package construction, verify the archive and file checksums, and populate this cache. A failed download or checksum check aborts installation. The verified archive is included in regular wheels and retained in editable checkouts; it can restore a missing cache without HF access. Installing a prebuilt wheel gets this snapshot with the wheel, without a separate HF request.

`--local-images` prohibits HF and registry access. Docker images are acquired by `pull`, `generate`, or `eval`; use `pull` while online before running evaluation offline. Help does not download task data.

### Network phases

| Phase | Network |
| --- | --- |
| Maintainer image production | Online preparation, then offline acceptance tests |
| Image acquisition before trials | Registry access; prohibited by `--local-images` |
| Agent setup | No network; native Harbor adapter uses the prepared image and cache |
| Agent execution | Model and authentication API hosts in the task allowlist |
| Patch collection | No network |
| Submission replay, compilation, functional tests, PoC | No network in separate fresh verifier containers |

The default API hosts are `api.openai.com`, `api.anthropic.com`, `chatgpt.com`, and `auth.openai.com`. Use repeated `--allow-model-host HOST` for another model endpoint. Use exact hostnames, without URLs, ports, paths, or wildcards. These changes apply only to that run's agent phase. They do not open setup or verification.

The model API exception applies to generation only. `eval` is fully offline after image acquisition. `--local-images` covers the wrapper's registry behavior; host-level isolation is still required if you need to prohibit unrelated host traffic. Harbor's native Docker network policy enforces the container phases.

## 2. Generate with native Harbor

### One task

```bash
export OPENAI_API_KEY='<your-api-key>'
securevibebench generate --agent mini-swe-agent --model 'openai/<model>' \
  --task 992 --local-images --output submissions/mini-992 --eval
```

`generate` invokes native `harbor run`, disables verification during generation, and packages its collected source patch. `--eval` then evaluates only this run's submission in fresh containers. Failure during generation skips scoring. A valid zero reward is a benchmark outcome, not an infrastructure error.

The output contains `images/images.json`, staged `tasks/`, `command.json`, `harbor.log`, native trajectories under `jobs/generation/`, `submission/`, and `summary.json`. With `--eval`, results are in `evaluation/eval.json`. A missing `--output` creates a new directory under `submissions/`. Logs and trajectories are retained; artifact redaction removes credential values.

### One, multiple, or all tasks

```bash
securevibebench generate --model 'openai/<model>' --task 992 --local-images
securevibebench generate --model 'openai/<model>' --task 992 32345 --jobs 2 --local-images
securevibebench generate --model 'openai/<model>' --task 992,32345 --jobs 2 --local-images
securevibebench generate --model 'openai/<model>' --task full --jobs 2 --local-images --eval
```

`--task full`, or omission of `--task`, selects all tasks under `--tasks`. The default root is the verified HF cache of supported tasks. `--tasks example --task full` selects the single example. Unknown IDs fail before any trial. `--jobs` controls native Harbor concurrency. CPU and memory budgets remain in each task definition.

### Agent and model configuration

`--agent` accepts native Harbor agent names. An image must declare that agent in `metadata.image.agents`. All current images declare mini-swe-agent only. The CLI rejects other agents before trials instead of trying a network installation. To support Codex or Claude Code, prepare and verify their native setup in a new image, then update the task's digest, ID, and agent declaration. The CLI does not copy host binaries into task containers.

Harbor manages mini's installer, configuration, prompts, and execution. The frozen image and the pinned Harbor version preserve its prepared installation. This project does not maintain a separate mini installer. A native adapter that needs uncached dependencies fails offline and retains its logs.

For another API gateway:

```bash
export MODEL_API_KEY='<your-api-key>'
securevibebench generate --model 'openai/<model>' --task 992 --local-images \
  --allow-model-host model.example.org --base-url https://model.example.org/v1 \
  --api-key-name MODEL_API_KEY --api-format openai_chat_completions
```

Forward native agent options with repeated `--ak KEY=VALUE`. `--agent-env NAME` forwards a set host variable by reference. Never put credential values in agent options. For mini's native OpenRouter backend:

```bash
export OPENROUTER_API_KEY='<your-api-key>'
securevibebench generate --agent mini-swe-agent \
  --model 'openrouter/<provider>/<model>' --task 992 --local-images \
  --allow-model-host openrouter.ai --agent-env OPENROUTER_API_KEY \
  --ak 'config={"model":{"model_class":"openrouter","model_kwargs":{"model":"<provider>/<model>"}}}' \
  --ak 'session_id_headers=[]' --eval
```

The backend model ID excludes the routing prefix `openrouter/`. Model availability and billing are controlled by your provider.

### Direct Harbor use

The staged tasks in a generation run use local image IDs and include host DNS configuration. You can use them with native Harbor, preserving their phase policies and collection hook:

```bash
harbor run -p submissions/mini-992/tasks -a mini-swe-agent -m 'openai/<model>' \
  --disable-verification --jobs-dir runs/native --job-name my-run
securevibebench eval runs/native/my-run --local-images
```

Keep the task image and Harbor network image available. Do not enable force-build or override network policies. Direct Harbor job patches must meet the collection requirements below.

## 3. Evaluate generated or external submissions

### Use generated submissions or native jobs

```bash
securevibebench eval submissions/mini-992 --local-images
securevibebench eval runs/native/my-run --local-images
securevibebench eval --local-images
```

With no path, `eval` checks `submissions/`. It accepts a patch submission there, or one unambiguous child. If there are multiple candidates, specify one. It does not choose the newest run.

A native job needs one completed trial per task and `artifacts/logs/artifacts/agent.patch` from the collection hook. Infrastructure errors and detected Codex tool startup errors prevent packaging. Duplicate attempts are rejected. Generation rewards are not required. The original job remains unchanged. Keep one completed attempt per task; collect multiple attempts into separate submissions.

An optional explicit export is available:

```bash
securevibebench package --job runs/native/my-run --output submissions/portable
securevibebench eval submissions/portable --local-images
```

### Build an external submission

Use this layout:

```text
my-submission/
  securevibebench-992/submission.patch
  securevibebench-32345/submission.patch
```

Each patch must be a regular file, not a symbolic link, named exactly `submission.patch`, at most 32 MiB per task. A subset of supported tasks is accepted. Empty patches are valid. No manifest or `submission.json` is required for external patches. Paths in the patch are relative to the task repository. Make the patch against the image's `svb-start` source snapshot:

Run inside the task repository in the prepared task container:

```bash
git add -N .
git diff --binary svb-start -- . > /tmp/submission.patch
```

Copy `/tmp/submission.patch` from the container into the matching task directory on the host before running `eval`. Keep this output outside the repository so it is not included in the patch.

Use the image snapshot as the base; a patch against the upstream project HEAD or the vulnerability fix commit can fail to apply. The evaluator runs `git apply --check` before applying a nonempty patch. Include added, modified, and deleted source files. Keep test cases, PoCs, reference data, build dependencies, and evaluation configuration unchanged. Do not include credentials, build output, or the patch file itself. Submit only supported tasks from the same pinned task release. Direct child directories under the submission root must follow the `securevibebench-ID` naming rule.

```bash
securevibebench eval my-submission --jobs 2 --local-images --output runs/my-score
```

The wrapper runs native Harbor's oracle adapter to apply each submitted patch, then the separate verifier recompiles and runs functional and security checks without network. It does not use a model API. Image checks, patch hashes, Harbor command, raw logs, trajectories, verifier exit codes, and `eval.json` remain in the result directory.

Functional and security rewards are separate. Each fixed image embeds its scoring policy. List results must retain the reference pass set; Boolean results must match the reference status. Tasks marked `count-results-no-regression-v1` must not reduce the pass count or total count, or increase failures or unknowns. Count-only output does not identify individual cases.

Some historical reference tests fail or are skipped; inspect `image-catalog.json` and image-production evidence. A completed empty-patch environment check is not evidence that an agent solved the task.
