#!/usr/bin/env python3
"""Verify a task bundle and import its prebuilt evaluation environments."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=Path("."))
    parser.add_argument(
        "--pull",
        action="store_true",
        help="Download the declared image digests before going offline",
    )
    args = parser.parse_args()
    root = args.bundle.resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    for name, expected in manifest["files_sha256"].items():
        path = (root / name).resolve()
        if (
            not path.is_relative_to(root)
            or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            raise ValueError("Bundle checksum mismatch: " + name)
    for item in manifest["framework_images"]:
        found = subprocess.run(
            ["docker", "image", "inspect", item["image_id"]],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if found.returncode:
            subprocess.run(
                ["docker", "load", "-i", str(root / item["archive"]["filename"])],
                check=True,
            )
        subprocess.run(
            ["docker", "tag", item["image_id"], item["local_tag"]], check=True
        )
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    import sys

    sys.path.insert(0, str(root / "recipe/cpython_image"))
    from complete_bundle import framework_tag

    if framework_tag() not in {
        item["local_tag"] for item in manifest["framework_images"]
    }:
        raise ValueError("Install the bundled matching Harbor wheels")
    from securevibebench_evaluation.images import read_task
    from securevibebench_evaluation.harbor_native import configure_dns

    for item in manifest["images"]:
        reference = item["registry"]["digest_reference"]
        if args.pull:
            subprocess.run(["docker", "pull", reference], check=True)
        info = json.loads(
            subprocess.check_output(
                ["docker", "image", "inspect", item["image_id"]], text=True
            )
        )[0]
        if (
            info["Id"] != item["image_id"]
            or info["Os"] != "linux"
            or info["Architecture"] != "amd64"
        ):
            raise ValueError("Image identity mismatch")
        subprocess.run(
            ["docker", "tag", item["image_id"], item["registry"]["tag"]], check=True
        )
        task = root / "tasks" / ("securevibebench-" + item["task"])
        read_task(task)
        configure_dns(task / "environment", manifest["resources_per_task"]["cpus"])
        print("Verified task", item["task"])
    print(
        "Ready: securevibebench eval /path/to/submission --tasks "
        + str(root / "tasks")
        + " --local-images"
    )


if __name__ == "__main__":
    main()
