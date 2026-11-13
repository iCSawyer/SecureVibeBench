"""Validate and stage the versioned functional contract before starting trials."""

import hashlib
import json
from pathlib import Path
import shutil

from .harbor_assets.differential import FRAMEWORK, POLICY, checksum, validate_spec

ASSETS = Path(__file__).with_name("harbor_assets")
ENTRYPOINT = ("#!/bin/bash\nset -euo pipefail\n"
              "exec /opt/svb/python/bin/python3 -I /tests/_svb/differential_runtime.py verify\n")


def require_contract(task, config=None):
    path = Path(task) / "tests/functional.json"
    if not path.is_file() or path.is_symlink():
        raise ValueError("Task needs F2P/P2P qualification: " + Path(task).name
                         + ". Its image is prepared, but no qualified functional.json is available.")
    spec = validate_spec(json.loads(path.read_text()), path.parent, framework=ASSETS)
    declared = {case["id"] for case in spec["cases"]}
    obligations = set(spec["FAIL_TO_PASS"]) | set(spec["PASS_TO_PASS"])
    if declared != obligations:
        raise ValueError("Task has unresolved functional cases; finish F2P/P2P qualification: "
                         + Path(task).name)
    bundled = path.parent / "_svb"
    if bundled.is_symlink() or not bundled.is_dir() or {file.name for file in bundled.iterdir()} != set(FRAMEWORK):
        raise ValueError("Task has an incomplete or changed native verifier bundle")
    for name in FRAMEWORK:
        file = bundled / name
        if file.is_symlink() or not file.is_file() or checksum(file) != spec["framework_sha256"][name]:
            raise ValueError("Task has a changed staged verifier: " + name)
    if (path.parent / "test.sh").read_text() != ENTRYPOINT:
        raise ValueError("Task does not launch the qualified native verifier")
    if spec["task"] != Path(task).name:
        raise ValueError("Functional contract belongs to another task")
    if config is not None:
        metadata = config["metadata"]
        if spec["image_id"] != metadata["image"]["id"]:
            raise ValueError("Functional qualification belongs to another image")
        if spec["reference_commit"] != metadata.get("vic"):
            raise ValueError("Functional qualification belongs to another reference commit")
        if metadata.get("reward_policy") != POLICY:
            raise ValueError("Task metadata does not declare the qualified scoring policy")
    return spec


def task_fingerprint(task):
    """Identify the exact task statement, metadata, and qualified test proof."""
    task = Path(task)
    files = {}
    for name in ("task.toml", "instruction.md", "tests/functional.json"):
        path = task / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Task fingerprint requires a regular file: " + name)
        files[name] = checksum(path)
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def preflight(tasks):
    from .images import read_task

    return [require_contract(task, read_task(task)) for task in tasks]


def stage_verifier(task):
    """Make the staged task self-contained for native Harbor execution."""
    destination = Path(task) / "tests"
    framework = destination / "_svb"
    if framework.is_symlink():
        raise ValueError("The staged verifier directory must not be a symbolic link")
    if framework.exists():
        shutil.rmtree(framework)
    framework.mkdir()
    for name in FRAMEWORK:
        shutil.copyfile(ASSETS / name, framework / name)
    (destination / "test.sh").write_text(ENTRYPOINT)


def scoring_status(task, config=None):
    try:
        if config is None:
            from .images import read_task
            config = read_task(task)
        spec = require_contract(task, config)
    except (OSError, ValueError, TypeError, KeyError) as error:
        return {"scoring_status": "needs-tests", "scoring_reason": str(error)}
    return {"scoring_status": "qualified", "scoring_policy": POLICY,
            "fail_to_pass": len(spec["FAIL_TO_PASS"]), "pass_to_pass": len(spec["PASS_TO_PASS"])}
