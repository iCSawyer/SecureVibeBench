#!/usr/bin/env python3
"""Generate and evaluate code on one task or all 105 SecureVibeBench tasks."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import sys


HERE = Path(__file__).resolve().parent


def user_cache_dir() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "securevibebench"


def positive_int(value: str) -> int:
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="Model identifier, e.g. provider/model")
    parser.add_argument("--task", action="append", default=[], metavar="ID",
                        help="Repeat to select tasks; default is all 105 tasks")
    parser.add_argument("--resume", type=Path, metavar="JOB_DIR",
                        help="Continue an interrupted job, e.g. runs/<job>; finished tasks are kept")
    # Retain existing rollout controls without crowding the Quick Start interface.
    parser.add_argument("--n-concurrent", type=positive_int, default=1, help=argparse.SUPPRESS)
    parser.add_argument("--attempts", type=positive_int, default=1, help=argparse.SUPPRESS)
    parser.add_argument("--jobs-dir", type=Path, default=Path.cwd() / "runs", help=argparse.SUPPRESS)
    parser.add_argument("--job-name", help=argparse.SUPPRESS)
    parser.add_argument("--cache-dir", type=Path, default=user_cache_dir() / "resources", help=argparse.SUPPRESS)
    parser.add_argument("--base-url", help="Optional OpenAI-compatible or provider API endpoint")
    parser.add_argument("--api-key-name", help="Environment variable NAME containing the API key")
    parser.add_argument("--api-format", choices=["openai_chat_completions", "openai_responses",
                                               "anthropic_messages"])
    parser.add_argument("--step-limit", type=positive_int, help=argparse.SUPPRESS)
    parser.add_argument("--cost-limit", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--run-sast", choices=["TRUE", "FALSE"], default="FALSE",
                        help="Run static security checks (default: FALSE; requires Semgrep credentials)")
    parser.add_argument("--env-file", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--print-config", action="store_true",
                        help=argparse.SUPPRESS)
    parser.set_defaults(usage_error=parser.error)
    return parser


def check_arguments(args: argparse.Namespace) -> argparse.Namespace:
    if args.resume is None and args.model is None:
        args.usage_error("the following arguments are required: --model (or --resume JOB_DIR)")
    return args


def prepare_dataset(args: argparse.Namespace) -> Path:
    """Use the dataset installed by pip, without an additional network download."""
    from securevibebench_evaluation.resources import manifest, materialize

    record = manifest()
    args.hf_repo = record["hf_repo"]
    args.resolved_hf_commit = record["hf_commit"]
    return materialize(args.cache_dir) / "dataset"


def build_config(args: argparse.Namespace, *, bundle: Path, mini_version: str | None = None) -> dict:
    import yaml
    from harbor.models.job.config import JobConfig

    bundle = bundle.resolve()
    config = yaml.safe_load((bundle / "harbor.yaml").read_text())
    # The release bundles the published tasks and evaluator without changing scores.
    template = yaml.safe_load((HERE / "harbor.yaml").read_text())
    config["agents"] = template["agents"]
    config["retry"] = template["retry"]
    if not args.model.strip():
        raise ValueError("--model must not be empty")
    if mini_version is None:
        from securevibebench_evaluation.resources import manifest
        # The agent runs inside Docker; its pinned source determines the version.
        mini_version = manifest()["mini_tag"].removeprefix("v")
    agent = config["agents"][0]
    agent["model_name"] = args.model
    agent.setdefault("kwargs", {})["version"] = mini_version
    agent["kwargs"]["source_dir"] = str(bundle.parent / "mini-swe-agent")
    agent["kwargs"]["toolchain_cache_dir"] = str(user_cache_dir() / "agent-toolchain")
    for source, target in (("base_url", "base_url"), ("api_key_name", "model_api_key_name"),
                           ("api_format", "model_api_format")):
        value = getattr(args, source)
        if value is not None:
            agent[target] = value
    if args.base_url and not args.base_url.startswith(("http://", "https://")):
        raise ValueError("--base-url must start with http:// or https://")
    if args.api_key_name and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", args.api_key_name):
        raise ValueError("--api-key-name expects an environment variable name")
    if args.step_limit is not None:
        agent["kwargs"]["config"] = {"agent": {"step_limit": args.step_limit}}
    if args.cost_limit is not None:
        if not math.isfinite(args.cost_limit) or args.cost_limit < 0:
            raise ValueError("--cost-limit must be finite and nonnegative")
        agent["kwargs"]["cost_limit"] = str(args.cost_limit)
    config["jobs_dir"] = str(args.jobs_dir.resolve())
    config["n_concurrent_trials"] = args.n_concurrent
    config["n_attempts"] = args.attempts
    if args.job_name:
        if args.job_name in (".", "..") or any(x in args.job_name for x in ("/", "\\")):
            raise ValueError("--job-name must be one directory name")
        config["job_name"] = args.job_name
    original_verifier = config["verifier"]
    if original_verifier.get("import_path") != "dev.harbor_verifier:SecureVibeBenchVerifier":
        raise ValueError("Unsupported published evaluator; refusing to substitute local benchmark logic")
    original_verifier["import_path"] = "securevibebench_evaluation.hf_verifier:HuggingFaceVerifier"
    verifier_options = original_verifier.setdefault("kwargs", {})
    verifier_options.update({
        "bundle_dir": str(bundle),
        "verifier_sha256": hashlib.sha256((bundle / "evaluator/harbor_verifier.py").read_bytes()).hexdigest(),
        "hf_repo": args.hf_repo,
        "hf_commit": getattr(args, "resolved_hf_commit", None),
        "baseline_dir": str(bundle.parent / "baselines"),
    })
    if args.run_sast is not None:
        verifier_options["run_sast"] = args.run_sast
    if args.task:
        config["datasets"] = []
        config["tasks"] = []
        seen = set()
        for ref in args.task:
            localid = ref.removeprefix("securevibebench-")
            if not re.fullmatch(r"[1-9][0-9]*", localid):
                raise ValueError(f"Invalid task ID: {ref!r}")
            if localid in seen:
                continue
            seen.add(localid)
            path = bundle / "data" / f"securevibebench-{localid}"
            if not (path / "task.toml").is_file():
                raise ValueError(f"Unknown task ID: {ref!r}")
            config["tasks"].append({"path": str(path)})
    else:
        config["datasets"] = [{"path": str(bundle / "data")}]
    # Use Harbor's real model to validate flags/fields and serialize Paths/enums.
    return JobConfig.model_validate(config).model_dump(mode="json")


def index_results(job_dir: Path) -> Path:
    """Index existing artifacts and native results without recalculating scores."""
    records = []
    for path in sorted(job_dir.glob("*/result.json")):
        result = json.loads(path.read_text())
        trial = path.parent
        originals = sorted(trial.glob("verifier/original/*/vul/*"))
        def artifacts(pattern: str) -> list[str]:
            return [str(p.relative_to(job_dir)) for directory in originals
                    for p in sorted(directory.glob(pattern)) if p.is_file()]
        agent_info = result.get("agent_info") or {}
        rewards = (result.get("verifier_result") or {}).get("rewards")
        records.append({
            "trial": trial.name,
            "task": result.get("task_name"),
            "task_checksum": result.get("task_checksum"),
            "agent": agent_info,
            "rewards": rewards,
            "exception": result.get("exception_info"),
            "result": str(path.relative_to(job_dir)),
            "mini_trajectory": str((trial / "agent/mini-swe-agent.trajectory.json").relative_to(job_dir))
                if (trial / "agent/mini-swe-agent.trajectory.json").is_file() else None,
            "atif_trajectory": str((trial / "agent/trajectory.json").relative_to(job_dir))
                if (trial / "agent/trajectory.json").is_file() else None,
            "patch": artifacts("result.patch"),
            "pov_results": artifacts("arvo_result.json"),
            "functional_results": artifacts("*_functional_result.json"),
            "sast_results": artifacts("semgrep_results_*.json"),
        })
    target = job_dir / "index.jsonl"
    target.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records))
    return target


def write_summary(job_dir: Path, native_result: dict, status: str = "complete") -> Path:
    """Present metrics already computed by Harbor without introducing a score."""
    stats = native_result.get("stats") or {}
    summary = {
        "job_dir": str(job_dir),
        "status": status,
        "n_total_trials": native_result.get("n_total_trials"),
        "n_completed_trials": stats.get("n_completed_trials"),
        "n_errored_trials": stats.get("n_errored_trials"),
        "n_retries": stats.get("n_retries"),
        "cost_usd": stats.get("cost_usd"),
        "n_input_tokens": stats.get("n_input_tokens"),
        "n_output_tokens": stats.get("n_output_tokens"),
        "evaluations": {
            name: {key: group.get(key) for key in ("n_trials", "n_errors", "metrics", "exception_stats")}
            for name, group in (stats.get("evals") or {}).items()
        },
        "native_result": "result.json",
        "artifact_index": "index.jsonl",
    }
    target = job_dir / "summary.json"
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return target


def unfinished_trials(job_dir: Path) -> list[Path]:
    """Trial directories without a final result, or whose result records an interruption."""
    trials = []
    for trial in sorted(path for path in job_dir.iterdir() if path.is_dir()):
        try:
            result = json.loads((trial / "result.json").read_text())
        except (OSError, ValueError):
            trials.append(trial)
            continue
        if (result.get("exception_info") or {}).get("exception_type") == "CancelledError":
            trials.append(trial)
    return trials


def remove_trial_containers(trials: list[Path]) -> int:
    """Remove containers left by interrupted trials; the Docker daemon may be shared.

    Only containers of the trial's own Compose project, or containers bind-mounting
    the trial directory (the original evaluator's), are selected.
    """
    if not trials:
        return 0
    import docker
    from harbor.environments.docker.docker import _sanitize_docker_compose_project_name

    trial_dirs = [trial.resolve() for trial in trials]
    projects = {_sanitize_docker_compose_project_name(f"{trial.name}__env") for trial in trial_dirs}
    try:
        client = docker.from_env().api
        client.ping()
    except docker.errors.DockerException as error:
        print(f"Cannot check for leftover containers: {error}", file=sys.stderr)
        return 0
    images, removed = set(), 0
    for container in client.containers(all=True):
        project = (container.get("Labels") or {}).get("com.docker.compose.project")
        mounted = any(Path(mount.get("Source") or "/").is_relative_to(trial)
                      for mount in container.get("Mounts") or [] for trial in trial_dirs)
        if project not in projects and not mounted:
            continue
        if project in projects and container.get("Image", "").startswith(project):
            images.add(container["Image"])
        client.remove_container(container["Id"], force=True)
        removed += 1
    for project in projects:
        for network in client.networks(filters={"label": f"com.docker.compose.project={project}"}):
            client.remove_network(network["Id"])
    for image in images:
        try:
            client.remove_image(image)
        except docker.errors.APIError:
            pass
    return removed


def native_result(job_dir: Path) -> dict:
    try:
        return json.loads((job_dir / "result.json").read_text())
    except (OSError, ValueError):
        return {}


def resume_config(job_dir: Path) -> dict:
    """Reload a saved job so Harbor reruns only its unfinished trials."""
    from harbor.models.job.config import JobConfig

    job_dir = job_dir.resolve()
    if not (job_dir / "config.json").is_file():
        raise ValueError(f"Not a job directory (config.json is missing): {job_dir}")
    config = JobConfig.model_validate_json((job_dir / "config.json").read_text())
    config.jobs_dir, config.job_name = job_dir.parent, job_dir.name
    bundle = Path(config.verifier.kwargs.get("bundle_dir", ""))
    if not (bundle / "harbor.yaml").is_file():
        raise ValueError(f"Resources used by this job are missing: {bundle}; "
                         "reinstall the securevibebench version that started it")
    return config.model_dump(mode="json")


def prepare_resume(job_dir: Path) -> None:
    trials = unfinished_trials(job_dir)
    removed = remove_trial_containers(trials)
    if removed:
        print(f"Removed {removed} container(s) left by the interrupted run")
    # Harbor itself discards trial directories without result.json.
    for trial in trials:
        if (trial / "result.json").is_file():
            shutil.rmtree(trial)


def report_progress(job, job_dir: Path) -> None:
    """Print one plain line per trial phase, also readable when output is redirected."""
    from rich import get_console
    from harbor.trial.hooks import TrialEvent

    console, started = get_console(), {}
    total = len(job)

    def say(message: str) -> None:
        console.print(f"[{datetime.now():%H:%M:%S}] {message}", markup=False, highlight=False,
                      soft_wrap=True)

    def phase(text: str):
        async def hook(event) -> None:
            started.setdefault(event.trial_name, datetime.now())
            say(f"{event.task_name.rsplit('/', 1)[-1]}: {text}")
        return hook

    async def finished(event) -> None:
        minutes, seconds = divmod(int((datetime.now() - started.get(event.trial_name, datetime.now()))
                                      .total_seconds()), 60)
        result, name = event.result, event.task_name.rsplit("/", 1)[-1]
        error = result.exception_info.exception_type if result.exception_info is not None else None
        if error == "CancelledError":
            say(f"{name}: interrupted after {minutes}m{seconds:02d}s")
            return
        if result.verifier_result is not None:
            outcome = " ".join(f"{key}={value}" for key, value in result.verifier_result.rewards.items())
        else:
            outcome = f"error: {error}" if error else "no result"
        # Rewrite the summary after every trial so an interruption keeps finished results.
        index_results(job_dir)
        write_summary(job_dir, native_result(job_dir), status="running")
        done = sum(path.is_dir() for path in job_dir.iterdir()) - len(unfinished_trials(job_dir))
        say(f"{name}: done in {minutes}m{seconds:02d}s, {outcome} [{done}/{total} finished]")

    job.add_hook(TrialEvent.START, phase("starting environment"))
    job.add_hook(TrialEvent.AGENT_START, phase("agent running"))
    job.add_hook(TrialEvent.VERIFICATION_START, phase("verifying"))
    job.add_hook(TrialEvent.END, finished)
    say(f"Job {job_dir} ({total} task(s)); detailed log: {job_dir / 'job.log'}")


async def execute(config: dict) -> int:
    from harbor.job import Job
    from harbor.models.job.config import JobConfig

    job = await Job.create(JobConfig.model_validate(config))
    job_dir = job.job_dir
    report_progress(job, job_dir)
    # Ctrl-C already cancels this task; SIGTERM/SIGHUP would otherwise kill the
    # process before trials stop their containers.
    loop, main_task = asyncio.get_running_loop(), asyncio.current_task()
    signals = (signal.SIGTERM, signal.SIGHUP)
    for signum in signals:
        loop.add_signal_handler(signum, lambda: main_task.cancelling() or main_task.cancel())
    try:
        result = await job.run()
    except asyncio.CancelledError:
        index_results(job_dir)
        summary_path = write_summary(job_dir, native_result(job_dir), status="interrupted")
        removed = remove_trial_containers(unfinished_trials(job_dir))
        print(f"\nInterrupted; removed {removed} leftover container(s).")
        print(f"Results of finished tasks: {summary_path}")
        print(f"Resume with: securevibebench eval --resume {job_dir}")
        return 130
    finally:
        for signum in signals:
            loop.remove_signal_handler(signum)
    index = index_results(job_dir)
    summary_path = write_summary(job_dir, result.model_dump(mode="json"))
    print(f"Harbor job: {job_dir}")
    print(f"Artifact index: {index}")
    print(f"Final evaluation results: {summary_path}")
    print(summary_path.read_text())
    return int(result.stats.n_errored_trials > 0)


def evaluate(args: argparse.Namespace) -> int:
    """Run evaluation using parsed CLI options."""
    try:
        if args.env_file is not None:
            from dotenv import load_dotenv
            if not args.env_file.is_file():
                raise ValueError(f"Environment file not found: {args.env_file}")
            load_dotenv(args.env_file, override=False)
        if args.resume is not None:
            if args.model is not None or args.task:
                raise ValueError("--resume reuses the job's saved settings; omit --model and --task")
            config = resume_config(args.resume)
        else:
            bundle = prepare_dataset(args)
            config = build_config(args, bundle=bundle)
        if args.print_config:
            print(json.dumps(config, ensure_ascii=False, indent=2))
            return 0
        if args.resume is not None:
            prepare_resume(args.resume.resolve())
        return asyncio.run(execute(config))
    except KeyboardInterrupt:
        return 130
    except (ValueError, ImportError, OSError, RuntimeError) as error:
        print(f"Cannot start rollout: {error}", file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    """Compatibility entry point for svb-evaluate."""
    return evaluate(check_arguments(build_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
