#!/usr/bin/env python3
"""Run official Harbor mini-swe-agent rollouts followed by original evaluation.

This entry point configures Harbor; it does not implement an agent or benchmark
scoring. setup.sh installs the locked editable mini-swe-agent. Each job pins that
installed version so all its task containers use the same agent release.
"""

from __future__ import annotations

import argparse
import asyncio
import errno
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEV = ROOT / "dev"

def positive_int(value: str) -> int:
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Model identifier, e.g. provider/model")
    parser.add_argument("--hf-repo", default="iCSawyer/SecureVibeBench")
    parser.add_argument("--hf-revision", default="habour-preview",
                        help="HF branch, tag or commit; resolved to an immutable commit before downloading")
    parser.add_argument("--cache-dir", type=Path, default=DEV / "cache" / "huggingface")
    parser.add_argument("--task", action="append", default=[], metavar="ID",
                        help="Repeat to select tasks; default is all 105 tasks")
    parser.add_argument("--n-concurrent", type=positive_int, default=1)
    parser.add_argument("--attempts", type=positive_int, default=1)
    parser.add_argument("--jobs-dir", type=Path, default=DEV / "runs")
    parser.add_argument("--job-name", help="Optional native Harbor job name")
    parser.add_argument("--base-url", help="Optional OpenAI-compatible or provider API endpoint")
    parser.add_argument("--api-key-name", help="Environment variable NAME containing the API key")
    parser.add_argument("--api-format", choices=["openai_chat_completions", "openai_responses",
                                               "anthropic_messages"])
    parser.add_argument("--step-limit", type=positive_int, help="Optional mini-swe-agent step limit")
    parser.add_argument("--cost-limit", type=float, help="Optional mini-swe-agent cost limit; 0 is unlimited")
    parser.add_argument("--run-sast", choices=["TRUE", "FALSE"],
                        help="Override the downloaded evaluator's optional SAST flag (published default: TRUE)")
    parser.add_argument("--env-file", type=Path, help="Load credentials into process environment, not job config")
    parser.add_argument("--print-config", action="store_true",
                        help="Download/validate HF files and print Harbor config; no agent, Docker, or inference")
    return parser


def verify_bundle(snapshot: Path) -> Path:
    bundle = snapshot / "habour"
    manifest = json.loads((bundle / "preview-manifest.json").read_text())
    verified = 0
    for name, expected in manifest["files_sha256"].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Unsafe path in the HF manifest: {name}")
        if relative.parts[:1] != ("habour",):
            continue
        path = snapshot.joinpath(*relative.parts)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"HF file checksum mismatch: {name}")
        verified += 1
    if verified == 0:
        raise ValueError("The HF bundle manifest does not describe any task files")
    for required in ("harbor.yaml", "dev/harbor_verifier.py"):
        if "habour/" + required not in manifest["files_sha256"]:
            raise ValueError(f"HF manifest is missing its evaluator/config: {required}")
    task_count = len(list((bundle / "data").glob("*/task.toml")))
    if task_count == 0 or task_count != manifest["task_count"]:
        raise ValueError("HF task count does not match the published manifest")
    return bundle


def prepare_dataset(args: argparse.Namespace) -> Path:
    """Download, checksum and materialize immutable HF files for Harbor.

    Hub snapshots may symlink files into a shared blobs directory. Harbor's
    task path validation correctly rejects such links outside each task, so
    make an identical regular-file checkout before passing tasks to Harbor.
    """
    from huggingface_hub import HfApi, snapshot_download

    info = HfApi().dataset_info(args.hf_repo, revision=args.hf_revision)
    args.resolved_hf_commit = info.sha
    snapshot = Path(snapshot_download(
        repo_id=args.hf_repo, repo_type="dataset", revision=info.sha,
        allow_patterns=["habour/**"], cache_dir=str(args.cache_dir.resolve()),
    ))
    source = verify_bundle(snapshot)
    parent = args.cache_dir.resolve() / "materialized"
    checkout = parent / info.sha
    if not checkout.exists():
        parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix="." + info.sha + "-", dir=parent))
        try:
            shutil.copytree(source, staging / "habour", symlinks=False,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            verify_bundle(staging)
            try:
                staging.rename(checkout)
            except OSError as error:
                # Another job may have materialized the same immutable commit.
                if error.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                    raise
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    return verify_bundle(checkout)


def build_config(args: argparse.Namespace, *, bundle: Path, mini_version: str | None = None) -> dict:
    import yaml
    from harbor.models.job.config import JobConfig

    bundle = bundle.resolve()
    config = yaml.safe_load((bundle / "harbor.yaml").read_text())
    # Only agent/rollout setup comes from this local template. The dataset and
    # evaluator (including default flags) are obtained from the same HF bundle.
    template = yaml.safe_load((HERE / "harbor.yaml").read_text())
    config["agents"] = template["agents"]
    config["retry"] = template["retry"]
    if not args.model.strip():
        raise ValueError("--model must not be empty")
    if mini_version is None:
        try:
            mini_version = version("mini-swe-agent")
        except PackageNotFoundError as error:
            raise ValueError("mini-swe-agent is missing; run bash evaluation/setup.sh first") from error
    agent = config["agents"][0]
    agent["model_name"] = args.model
    agent.setdefault("kwargs", {})["version"] = mini_version
    agent["kwargs"]["source_dir"] = str(HERE / "mini-swe-agent")
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
        "verifier_sha256": hashlib.sha256((bundle / "dev/harbor_verifier.py").read_bytes()).hexdigest(),
        "hf_repo": args.hf_repo,
        "hf_commit": getattr(args, "resolved_hf_commit", None),
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
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
    except (ValueError, ImportError, FileNotFoundError) as error:
        print(f"Cannot start rollout: {error}", file=sys.stderr)
        print("Use the uv environment created by evaluation/setup.sh.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
