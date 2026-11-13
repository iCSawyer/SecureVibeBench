# Change Log

## 0.4.0 — F2P/P2P scoring (unreleased, `habour` branch)

- Replace the active Boolean, pass-list, and count-based functional scorers with `functional-f2p-p2p-v1`. Historical scores are not directly comparable.
- Require a nonempty F2P set and actual PASS for every F2P/P2P case in one complete candidate run. Missing, skipped, duplicate, or errored required cases cannot pass.
- Qualify each task with at least four independent offline measurements: two starting-source runs and two functional-reference runs. Bind evidence to the prepared image, actual source trees, test assets, case IDs, and verifier hashes.
- Keep the original PoC security check independent. Report `functional`, `security`, and `reward = functional * security`; no SAST score is added to this reward.
- Distinguish 105 prepared images from the changing qualified task subset. Mark other tasks `needs-tests`, reject them before scoring, and provide no historical-scoring fallback. `generate --eval` checks qualification before model calls.
- Separate image manifest digest, Docker config ID, and Git source tree identity. Retain embedded historical baselines as preparation evidence only; new functional scoring reads the task contract and four pinned verifier modules.
- Reuse independently reviewed contracts only for identical requirements and base/reference revisions; qualify each target image with fresh measurements and retain reuse provenance.
- Bundle a pinned native Harbor verifier under each qualified task's `tests/`. Protect grader and test assets while allowing exact manifest-declared production targets under test or fuzzer paths.
- Retain source-patch generation, `generate --eval`, independent submission scoring, Python 3.12+, pip installation, and optional uv.
- Keep qualified task data on HF `full-habour`, one example in GitHub, and maintainer qualification evidence and agent trajectories under `runs/`. P2P represents task acceptance coverage, not every upstream test.
- Reject publication of declared cases excluded from F2P/P2P. Retain evidence for corrected test fixtures, task statements, and functional reference defects; keep the original VIC as provenance.
- Add resumable maintainer author/reviewer/qualification tools with input checks, contract-bound reviews, recorded quota waits, and retained execution logs.

The notes below describe earlier development states. Their former runtime preparation and scoring behavior do not apply to the 0.4.0 workflow.

## HF task storage and branch cleanup

- Store full task definitions, availability, provenance, and the shared network image archive on HF full-habour.
- Pin and verify the HF release; cache it before trials and reuse it with no network under --local-images.
- Keep one example in GitHub and remove branch workflows.

## 0.3.0 — Prepared image evaluation (habour branch)

- Use fixed GHCR digests and verify Docker image IDs before trials.
- Include 21 prepared image task definitions and Harbor's network policy image.
- Keep setup, compilation, patch collection, and verification offline; allow only configured model APIs during agent execution.
- Replace runtime preparation and dataset fetching with `pull`, `generate`, `eval`, and `package`.
- Move image and dataset build helpers to maintainer tooling. Retain native Harbor submission generation and independent patch scoring.

## Earlier development notes (`habour` branch, superseded where noted)

- Install GMP and MPFR development headers during binutils/GDB preparation so the fixed-source GDB build can configure offline.

- Pin libavc GoogleTest and disable remote dependency updates during tests. Preserve igraph version metadata before removing Git history.
- Remove obsolete submodule Git databases while keeping cached sources. Serialize binutils cleanup and preserve the original optional Wireshark fuzz dependency set.

- Separate MRuby host code generation from its instrumented target build. Cap bare CMake, Ninja, and Hermes lit parallelism.
- Clean generated build caches when ordinary and fuzz toolchains differ. Serialize CUPS build/install goals and retain real GhostPDL smoke-test failures.
- Cache fixed libavc and igraph inputs with SHA-256 checks. Report every upstream file test fixture, including failures after the aggregate test stops.

- Record shared runtime hashes from each image build context so later source edits do not change its provenance.

- Support explicit count-based functional results for newly prepared images, with non-regressing pass/total counts and no increase in failures or unknowns. Keep existing list and Boolean rules.
- Make task build directories repeatable and resolve repository-relative entries before offline reference tests.

- Download and verify the pinned HF task data during regular and editable installation; bundle the snapshot for offline cache recovery. Docker images remain acquired before trials.

- Consolidate accepted task images under `ghcr.io/icsawyer/securevibebench`, preserve manifest digests, and verify anonymous Docker pulls.

- Add 20 images to the existing Public GHCR package with task-specific tags; expand the pinned HF catalog to 41 supported tasks.

- Verify anonymous access to all 21 prepared GHCR images and remove the package login requirement from user instructions.

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
