"""Build offline native-Harbor jobs from source-patch submissions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

from .harbor_native import write_config, agent_backend_error
from .images import acquire, read_task, select_tasks, stage_task


def submission_tasks(run: Path):
    found = []
    for directory in sorted(run.iterdir()):
        if not directory.is_dir():
            continue
        if not re.fullmatch(r"securevibebench-[0-9]+", directory.name):
            raise ValueError("Unknown submission directory: " + directory.name)
        patch = directory / "submission.patch"
        if not patch.is_file() or patch.is_symlink():
            raise ValueError("Missing regular submission.patch: " + directory.name)
        if patch.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("Submission patch exceeds 32 MiB")
        found.append((directory.name, patch))
    if not found:
        raise ValueError("No submissions found")
    return found


def stage_submissions(run: Path, tasks: Path, destination: Path):
    found = submission_tasks(run)
    for name, _ in found:
        from .functional import require_contract
        require_contract(tasks / name, read_task(tasks / name))
    destination.mkdir(parents=True, exist_ok=False)
    records = []
    for name, patch in found:
        target = destination / name
        source = tasks / name
        config = stage_task(source, target, scoring=True)
        # Submission scoring performs no API connectivity check or agent execution.
        repo = shlex.quote(config["metadata"]["repo_cwd"])
        config["verifier"]["collect"] = [
            {
                "command": "mkdir -p /logs/artifacts && "
                "cp /solution/submission.patch /logs/artifacts/agent.patch"
            }
        ]
        write_config(target / "task.toml", config)
        solution = target / "solution"
        solution.mkdir()
        shutil.copyfile(patch, solution / "submission.patch")
        (solution / "solve.sh").write_text(
            "#!/bin/bash\nset -euo pipefail\ncd "
            + repo
            + "\nif test -s /solution/submission.patch; then git apply --check /solution/submission.patch; git apply /solution/submission.patch; fi\n"
        )
        records.append(
            {
                "task": name,
                "patch_sha256": hashlib.sha256(patch.read_bytes()).hexdigest(),
                "prepared_image": config["environment"]["docker_image"],
                "scoring_policy": config["metadata"]["reward_policy"],
                "functional_contract_sha256": hashlib.sha256(
                    (source / "tests/functional.json").read_bytes()
                ).hexdigest(),
            }
        )
    (destination.parent / "submission-manifest.json").write_text(
        json.dumps(records, indent=2) + "\n"
    )
    return records


def input_kind(path):
    if not path.is_dir():
        return None
    if any((path / "submission").glob("*/submission.patch")):
        return "generated"
    if any(path.glob("*/submission.patch")):
        return "patches"
    for result in path.glob("*/result.json"):
        if json.loads(result.read_text()).get("task_name"):
            return "harbor"
    return None


def resolve_submission(path):
    """Accept a submission, native job, or an unambiguous submissions root."""
    kind = input_kind(path)
    if kind:
        return (path / "submission", "patches") if kind == "generated" else (path, kind)
    if not path.is_dir():
        raise ValueError("Submission directory does not exist: " + str(path))
    candidates = [(p, input_kind(p)) for p in sorted(path.iterdir()) if p.is_dir()]
    candidates = [(p, kind) for p, kind in candidates if kind]
    if len(candidates) != 1:
        raise ValueError(
            "Specify one submission or Harbor job directory; found %d candidates under %s"
            % (len(candidates), path)
        )
    source, kind = candidates[0]
    return (source / "submission", "patches") if kind == "generated" else (source, kind)


def score(run: Path, tasks: Path, output: Path, jobs: int = 1, *, local_only=False):
    if output.exists():
        raise FileExistsError("Use a new output directory: " + str(output))
    source, kind = resolve_submission(run)
    output.mkdir(parents=True, exist_ok=False)
    if kind == "harbor":
        packaged = output / "submission"
        package_job(source, packaged)
        run = packaged
    else:
        run = source
    found = submission_tasks(run)
    selected = select_tasks([name for name, _ in found], tasks)
    from .functional import preflight
    try:
        contracts = preflight(selected)
    except (OSError, ValueError) as error:
        (output / "preflight.json").write_text(json.dumps(
            {"state": "needs-qualification", "reason": str(error)}, indent=2) + "\n")
        raise
    (output / "preflight.json").write_text(json.dumps(
        {"state": "qualified", "tasks": [item["task"] for item in contracts]}, indent=2) + "\n")
    acquire(selected, output / "images", local_only=local_only)
    inputs = output / "inputs"
    records = stage_submissions(run, tasks, inputs)
    command = [
        str(Path(sys.executable).with_name("harbor")),
        "run",
        "-p",
        str(inputs),
        "-a",
        "oracle",
        "-n",
        str(jobs),
        "--jobs-dir",
        str(output / "jobs"),
        "--job-name",
        "evaluation",
    ]
    (output / "command.json").write_text(json.dumps(command, indent=2) + "\n")
    from os import environ

    environment = {**environ, "LITELLM_LOCAL_MODEL_COST_MAP": "True"}
    empty_env = output / "empty.env"
    empty_env.write_text("")
    command += ["--env-file", str(empty_env)]
    (output / "command.json").write_text(json.dumps(command, indent=2) + "\n")
    with (output / "harbor.log").open("w") as log:
        result = subprocess.run(
            command, stdout=log, stderr=subprocess.STDOUT, env=environment
        )
    results = []
    for path in (output / "jobs/evaluation").glob("*/result.json"):
        data = json.loads(path.read_text())
        results.append(
            {
                "task": data.get("task_name"),
                "rewards": (data.get("verifier_result") or {}).get("rewards"),
                "exception": data.get("exception_info"),
                "harbor_result": str(path),
            }
        )
    summary = {
        "source": str(source),
        "source_kind": kind,
        "submitted": len(records),
        "completed_records": len(results),
        "harbor_exit_code": result.returncode,
        "results": results,
        "network": "no-network",
        "scoring_policy": "functional-f2p-p2p-v1",
    }
    (output / "eval.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    expected = {item["task"] for item in records}
    actual = [str(item["task"]).rsplit("/", 1)[-1] for item in results]
    failed = (
        len(actual) != len(expected)
        or set(actual) != expected
        or any(item["exception"] or not item["rewards"] for item in results)
    )
    return result.returncode or int(failed)


def package_job(job: Path, destination: Path):
    """Export completed Harbor trajectories as a source-only submission directory."""
    records = []
    for result_path in sorted(job.glob("*/result.json")):
        result = json.loads(result_path.read_text())
        name = str(result.get("task_name", "")).rsplit("/", 1)[-1]
        if not re.fullmatch(r"securevibebench-[0-9]+", name):
            raise ValueError("Unexpected task name in Harbor result")
        if result.get("exception_info") or agent_backend_error(result_path.parent):
            raise ValueError("Cannot package an unsuccessful agent trial: " + name)
        patch = result_path.parent / "artifacts/logs/artifacts/agent.patch"
        if not patch.is_file() or patch.is_symlink():
            raise ValueError("Missing regular collected source patch: " + name)
        if patch.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("Collected source patch exceeds 32 MiB: " + name)
        records.append((name, patch, result_path))
    if not records or len({name for name, _, _ in records}) != len(records):
        raise ValueError("Select completed trials with one attempt per task")
    destination.mkdir(parents=True, exist_ok=False)
    manifest = []
    for name, patch, result_path in records:
        folder = destination / name
        folder.mkdir()
        shutil.copyfile(patch, folder / "submission.patch")
        manifest.append(
            {
                "task": name,
                "patch_sha256": hashlib.sha256(
                    (folder / "submission.patch").read_bytes()
                ).hexdigest(),
                "harbor_result_sha256": hashlib.sha256(
                    result_path.read_bytes()
                ).hexdigest(),
            }
        )
    (destination / "submission.json").write_text(
        json.dumps({"format": "securevibebench-patch-v1", "tasks": manifest}, indent=2)
        + "\n"
    )
    return manifest
