#!/usr/bin/env python3
"""Generate and evaluate code on one task or all 105 SecureVibeBench tasks."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import math
import os
from pathlib import Path
import re
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
    parser.add_argument("--model", required=True, help="Model identifier, e.g. provider/model")
    parser.add_argument("--task", action="append", default=[], metavar="ID",
                        help="Repeat to select tasks; default is all 105 tasks")
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
    return parser


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
        try:
            mini_version = version("mini-swe-agent")
        except PackageNotFoundError as error:
            raise ValueError("mini-swe-agent is missing; reinstall securevibebench with its dependencies") from error
    agent = config["agents"][0]
    agent["model_name"] = args.model
    agent.setdefault("kwargs", {})["version"] = mini_version
    agent["kwargs"]["source_dir"] = str(bundle.parent / "mini-swe-agent")
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


def write_summary(job_dir: Path, native_result: dict) -> Path:
    """Present metrics already computed by Harbor without introducing a score."""
    stats = native_result.get("stats") or {}
    summary = {
        "job_dir": str(job_dir),
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


async def execute(config: dict) -> int:
    from harbor.job import Job
    from harbor.models.job.config import JobConfig

    job = await Job.create(JobConfig.model_validate(config))
    result = await job.run()
    job_dir = job.job_dir
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
        bundle = prepare_dataset(args)
        config = build_config(args, bundle=bundle)
        if args.print_config:
            print(json.dumps(config, ensure_ascii=False, indent=2))
            return 0
        return asyncio.run(execute(config))
    except (ValueError, ImportError, OSError, RuntimeError) as error:
        print(f"Cannot start rollout: {error}", file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    """Compatibility entry point for svb-evaluate."""
    return evaluate(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
