#!/usr/bin/env python3
"""Export digest-based Harbor tasks from a verified image distribution."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import tomllib

from securevibebench_evaluation.harbor_native import write_config
from securevibebench_evaluation.images import read_task


def export_task(source, target, image):
    """Keep task files; move build recipes and acceptance evidence out of runtime."""
    config = tomllib.loads((source / "task.toml").read_text())
    metadata = config["metadata"]
    config["metadata"] = {
        key: value
        for key, value in metadata.items()
        if key
        in (
            "localid",
            "repo_url",
            "vic",
            "base_commit",
            "repo_cwd",
            "functional_script_id",
            "source_dataset",
            "reward_policy",
            "hf_revision",
        )
    }
    config["metadata"]["image"] = {
        "reference": image["registry"]["digest_reference"],
        "id": image["image_id"],
        "platform": "linux/amd64",
        "agents": ["mini-swe-agent"],
        "mini_version": image["native_mini_version"],
        "baseline_sha256": image["reference_baseline_sha256"],
    }
    config["task"]["version"] = "3.0.0" if metadata.get("reward_policy") == "functional-f2p-p2p-v1" else "2.0.0"
    config["environment"].update(
        docker_image=image["registry"]["digest_reference"], network_mode="no-network"
    )
    config["environment"].pop("allowed_hosts", None)
    target.mkdir(parents=True, exist_ok=False)
    shutil.copy2(source / "instruction.md", target / "instruction.md")
    shutil.copytree(source / "tests", target / "tests")
    write_config(target / "task.toml", config)
    read_task(target)


def export_run(run, output):
    """Export the selected tasks after Public publication and offline acceptance."""
    identifiers = json.loads((run / "selection.json").read_text())["selected"]
    images = []
    for identifier in identifiers:
        task = run / "tasks" / identifier
        state = json.loads((task / "status.json").read_text())
        registry = state.get("registry", {})
        if (
            state["state"] != "completed"
            or registry.get("visibility") != "public"
            or registry.get("anonymous_pull_verified") is not True
            or state.get("verification", {}).get("native_setup_offline") is not True
            or state.get("image_audit", {}).get("credentials_present") is not False
        ):
            raise ValueError(
                "Task has not passed Public image acceptance: " + identifier
            )
        baseline = task / "work/baseline.json"
        expected = state["offline_gold_baseline_sha256"]
        if hashlib.sha256(baseline.read_bytes()).hexdigest() != expected:
            raise ValueError("Reference baseline checksum mismatch: " + identifier)
        evidence = task / "bundle/evidence"
        version = json.loads((evidence / "native-install/result.json").read_text())[
            "agent_info"
        ]["version"]
        images.append(
            {
                "task": identifier,
                "image_id": state["frozen_image"],
                "base_image": state["base_image"],
                "base_image_id": state["base_image_id"],
                "reference_baseline_sha256": expected,
                "image_audit": state["image_audit"],
                "verification": state["verification"],
                "registry": registry,
                "toolchain": state["toolchain"],
                "native_mini_version": version,
            }
        )
    if not images or len(set(identifiers)) != len(identifiers):
        raise ValueError("Select distinct accepted tasks")
    if output.exists():
        raise FileExistsError("Choose a new output directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".svb-public-catalog-", dir=output.parent
    ) as temporary:
        staging = Path(temporary)
        for image in images:
            name = "securevibebench-" + image["task"]
            export_task(
                run / "tasks" / image["task"] / "bundle/tasks" / name,
                staging / name,
                image,
            )
        contracts = []
        for image in images:
            name = "securevibebench-" + image["task"]
            contract = tomllib.loads((staging / name / "task.toml").read_text())[
                "metadata"
            ]["image"]
            evidence = run / "tasks" / image["task"] / "bundle/evidence"
            contracts.append(
                {
                    **contract,
                    "task": image["task"],
                    "visibility": "public",
                    "anonymous_manifest_verified": True,
                    "registry": image["registry"],
                    "reference_source": json.loads(
                        (evidence / "gold/source.json").read_text()
                    ),
                    "starting_source": json.loads(
                        (evidence / "start/source.json").read_text()
                    ),
                }
            )
        (staging / "image-catalog.json").write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "task_count": len(contracts),
                    "images": contracts,
                },
                indent=2,
            )
            + "\n"
        )
        staging.replace(output)


def export(bundle, output):
    manifest = json.loads((bundle / "manifest.json").read_text())
    if output.exists():
        raise FileExistsError("Choose a new output directory")
    images = manifest["images"]
    if not images or any(
        item["registry"]["visibility"] != "private"
        or not item["verification"]["native_setup_offline"]
        for item in images
    ):
        raise ValueError("Distribution must contain verified private images")
    for item in images:
        name = "securevibebench-" + item["task"]
        export_task(bundle / "tasks" / name, output / name, item)
    (output / "image-catalog.json").write_text(
        json.dumps({"schema_version": 1, "images": images}, indent=2) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--bundle", type=Path)
    inputs.add_argument("--run", type=Path, help="Completed Public image run")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.run:
        export_run(args.run.resolve(), args.output.resolve())
    else:
        export(args.bundle.resolve(), args.output.resolve())
