## 0.3.0 — Prepared image evaluation (habour branch)

- Use fixed GHCR digests and verify Docker image IDs before trials.
- Include 21 prepared image task definitions and Harbor's network policy image.
- Keep setup, compilation, patch collection, and verification offline; allow only configured model APIs during agent execution.
- Replace runtime preparation and dataset fetching with `pull`, `generate`, `eval`, and `package`.
- Move image and dataset build helpers to maintainer tooling. Retain native Harbor submission generation and independent patch scoring.

# Change Log

## Unreleased (`habour` branch)

- Redact known credential values from completed native generation artifacts while preserving trajectories.
- Pass named host environment variables with native Harbor references, and clean libplist sanitizer objects before ordinary tests.
- Link the Lua dependency enabled by lwan reference preparation into its fuzz binaries.

- Forward repeatable `generate --agent-kwarg KEY=VALUE` options to native Harbor.
- Keep sampled offline functional scripts free of repeated APT setup and host Docker launchers; reuse prepared radare2 regression data and package only corpus directories.

- Make repeated HarfBuzz corpus setup idempotent and clean htslib sanitizer objects before ordinary tests.
- Respect configured CPU/memory budgets during preparation probes and assign Zeek an 8 CPU / 32 GiB budget for its historical C++ build.

- Cache rawspeed GoogleTest sources during online preparation and reuse them during offline testing.
- Give preparation probes unique names and apply Docker CPU placement to keep legacy build parallelism within the task budget.

- Preserve nonzero reference-test exits when the original parser records a positive baseline pass set. Do not require all starting-source tests to pass before code generation. Keep compilation gates and original scoring unchanged.
- Record build-failure exit codes and include failed command output in build logs.

- Download the full dataset as one verified archive to avoid per-file HF rate limits. Move duplicated runtime, parser, and scoring assets into the installed package while retaining original staging assets in local archives.
- Use separate temporary files for concurrent first-time toolchain downloads.

- Download agent dependencies through Harbor at generation time. Use a general wheel-only uv policy for historical images, without fixing mini dependency versions or adding a Rust toolchain.

- Delegate mini-swe-agent installation, version selection, dependencies, and configuration to Harbor. Remove the custom dependency lock, preinstallation, and mini setup probe. Use Harbor phase policies for online setup, model-only execution, and offline scoring.

- Fold environment preparation into `generate` and `eval`; remove the separate `prepare` command. Reuse valid local images and support `--offline` to forbid downloads.

- Restore `securevibebench generate` as a thin native Harbor wrapper. Add `--eval` to score only the successful current generation; `securevibebench eval` reads Harbor jobs or external patch submissions directly. Host uv is optional, and preparation installs the container Python 3.12 runtime automatically.

- Default generation now invokes Harbor's built-in mini-swe-agent with a user-provided model. Codex and Claude Code remain optional native agents.
- Added explicit online preparation, fixed agent dependencies, model-only runtime networking, and separate offline verification.
- Added manual source-patch submissions and native Harbor scoring without model calls.
- Full task definitions move to the HF `full-habour` branch; this repository keeps one task in `example/`.
- Merged the Harbor guide into `docs/README.md`. Removed the previous custom agent/evaluator from the active package and installation path.
- Preparation removes original Git history before agent execution.

## Roadmap

- [ ] **Cascaded LLM-as-a-judge.** Add an LLM judge as a final stage after the functional checks. Its verdicts would be reported separately so they don't change the existing scores.

## v0.2.2

- Minor changes: the README install commands use `pip install -U`, the roadmap moved into this change log, and repository files were reorganized. Evaluation is unchanged.

## v0.2.1

- **Bug fix: functional evaluation of task 10172 and the other Wireshark tasks.** Their test scripts run `ctest -j`, which interleaves output from concurrent tests. The parser could attach a test name to another test's status and also counted summaries such as `OK (skipped=2)` as tests. For example, a 10172 patch that passed every test scored `functional = 0`. The parser now reads each test's output on its own. Functional scores for these tasks can differ from v0.2.0 and v0.1; other tasks are unaffected. The dataset is pinned to HF `habour-preview` commit `5fa48dd`.
- Interrupting a run with Ctrl-C, `SIGTERM`, or `SIGHUP` now removes its containers and keeps finished tasks in `summary.json`. Continue the run with `securevibebench eval --resume runs/<job>`.
- `summary.json` is updated after each task, and progress prints one line per task phase.
- The agent toolchain is cached across tasks. Runtime caches (resources, baselines, agent toolchain) now live in `.cache/securevibebench/` under the working directory, next to `runs/`.
- mini-swe-agent runs only inside task containers and is no longer installed on the host.
- Added `securevibebench --version`.

## v0.2.0

- First PyPI release: `pip install securevibebench` installs all 105 tasks and the original evaluator from Hugging Face. The tasks use the Harbor format.
- A single command, `securevibebench eval`, generates code with mini-swe-agent and evaluates it, and works with custom OpenAI-compatible endpoints.
- SAST is disabled by default; enable it with `--run-sast TRUE`.
- Task instructions, tests, and scoring logic are unchanged from v0.1, but results can differ because the agent and evaluation workflow changed.
