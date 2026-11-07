#!/usr/bin/env python3
"""Export digest-based Harbor tasks from a verified image distribution."""

import argparse
import json
from pathlib import Path
import shutil
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
    config["task"]["version"] = "2.0.0"
    config["environment"].update(
        docker_image=image["registry"]["digest_reference"], network_mode="no-network"
    )
    config["environment"].pop("allowed_hosts", None)
    target.mkdir(parents=True, exist_ok=False)
    shutil.copy2(source / "instruction.md", target / "instruction.md")
    (target / "tests").mkdir()
    shutil.copy2(source / "tests/test.sh", target / "tests/test.sh")
    write_config(target / "task.toml", config)
    read_task(target)


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
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.bundle.resolve(), args.output.resolve())
