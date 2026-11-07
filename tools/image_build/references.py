"""Retarget task contracts only after an identical Public manifest is verified."""

from __future__ import annotations

from pathlib import Path
import tomllib

from securevibebench_evaluation.harbor_native import write_config


def retarget(tasks, catalog, migration):
    verified = {
        (str(row["task"]), row["image_id"]): row
        for row in migration["images"]
        if row.get("anonymous_pull_verified") is True
        and row.get("manifest_preserved") is True
    }
    plans = []
    for image in catalog["images"]:
        identifier = str(image["task"])
        row = verified.get((identifier, image["id"]))
        if row is None:
            raise ValueError(
                "Canonical image has not passed anonymous acceptance: " + identifier
            )
        reference = row["reference"]
        if reference.split("@", 1)[1] != image["reference"].split("@", 1)[1]:
            raise ValueError("Migration changed the manifest digest: " + identifier)
        task = Path(tasks) / ("securevibebench-" + identifier) / "task.toml"
        config = tomllib.loads(task.read_text())
        contract = config["metadata"]["image"]
        if contract["id"] != image["id"] or contract["reference"] != image["reference"]:
            raise ValueError("Task and image catalog disagree: " + identifier)
        plans.append((task, config, image, row))
    for task, config, image, row in plans:
        config["metadata"]["image"]["reference"] = row["reference"]
        config["environment"]["docker_image"] = row["reference"]
        write_config(task, config)
        image["reference"] = row["reference"]
        image["visibility"] = "public"
        image["anonymous_manifest_verified"] = True
        image["canonical_registry"] = {
            "tag": row["tag"],
            "reference": row["reference"],
            "anonymous_pull_verified": True,
            "manifest_preserved": True,
        }
    return catalog
