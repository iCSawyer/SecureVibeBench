# Change Log

## Roadmap

- [ ] **Cascaded LLM-as-a-judge.** Add an LLM judge as a final stage after the functional checks. Its verdicts would be reported separately so they don't change the existing scores.

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
