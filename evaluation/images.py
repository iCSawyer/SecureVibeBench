"""Validate pinned task images and stage network-restricted Harbor tasks."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tomllib

from .harbor_native import configure_dns, digest, select_cpus, write_config

HERE = Path(__file__).resolve().parent
SHA256 = r"sha256:[0-9a-f]{64}"
REFERENCE = re.compile(r"[^\s@]+@" + SHA256)


def read_task(task: Path):
    """Read the image contract without consulting host build tools."""
    from harbor.models.task.config import TaskConfig

    config = tomllib.loads((task / "task.toml").read_text())
    TaskConfig.model_validate(config)
    image = config.get("metadata", {}).get("image", {})
    reference = config.get("environment", {}).get("docker_image", "")
    if not REFERENCE.fullmatch(reference) or reference != image.get("reference"):
        raise ValueError("Task requires a registry digest: " + str(task))
    if (
        not re.fullmatch(SHA256, image.get("id", ""))
        or image.get("platform") != "linux/amd64"
    ):
        raise ValueError("Task requires a Linux amd64 image ID: " + str(task))
    if config["environment"].get("network_mode") != "no-network":
        raise ValueError("Task setup must use no-network: " + str(task))
    verifier = config.get("verifier", {})
    if (
        verifier.get("environment_mode") != "separate"
        or verifier.get("network_mode") != "no-network"
        or verifier.get("environment", {}).get("network_mode") != "no-network"
    ):
        raise ValueError("Task requires a separate offline verifier: " + str(task))
    agent = config.get("agent", {})
    if agent.get("network_mode") != "allowlist" or not agent.get("allowed_hosts"):
        raise ValueError("Task requires a model API allowlist: " + str(task))
    for name in ("instruction.md", "tests/test.sh"):
        if not (task / name).is_file() or (task / name).is_symlink():
            raise ValueError("Missing regular task file: " + name)
    # The verifier and source tree are supplied by this immutable image.
    if (task / "environment/Dockerfile").exists():
        raise ValueError("Image tasks must not include a build recipe: " + str(task))
    return config


def task_statuses(root=None):
    """List the full inventory without making unsupported tasks runnable."""
    from .dataset import resolve_tasks

    root = resolve_tasks(root)
    candidates = [root / "availability.json", root.parent / "availability.json"]
    for path in candidates:
        if path.is_file():
            records = json.loads(path.read_text())["tasks"]
            return records
    return [
        {
            "task": path.parent.name,
            "localid": path.parent.name.removeprefix("securevibebench-"),
            "status": "supported",
            "project": "",
        }
        for path in sorted(root.glob("*/task.toml"))
    ]


def select_tasks(values=None, root=None):
    from .dataset import resolve_tasks

    root = resolve_tasks(root)
    selected = [
        part.strip() for value in (values or ["full"]) for part in value.split(",")
    ]
    if any(not part for part in selected):
        raise ValueError("Task IDs must not be empty")
    if "full" in selected:
        if selected != ["full"]:
            raise ValueError("Use --task full alone")
        result = [path.parent for path in sorted(root.glob("*/task.toml"))]
    else:
        result = []
        for value in selected:
            name = "securevibebench-" + value if value.isdigit() else value
            if not re.fullmatch(r"securevibebench-[0-9]+", name):
                raise ValueError("Use task IDs or full: " + value)
            path = root / name
            if path not in result:
                result.append(path)
    if not result:
        raise ValueError("No image tasks found: " + str(root))
    for path in result:
        if not (path / "task.toml").is_file():
            status = next(
                (item for item in task_statuses(root) if item["task"] == path.name),
                None,
            )
            if status and status["status"] == "unsupported":
                raise ValueError(
                    "Task temporarily unsupported (no prepared image digest): "
                    + path.name
                )
            raise ValueError("No prepared image task: " + path.name)
        read_task(path)
    return result


def inspect_image(reference):
    result = subprocess.run(
        ["docker", "image", "inspect", reference], capture_output=True, text=True
    )
    if result.returncode:
        if (
            "no such image" not in result.stderr.lower()
            and "no such object" not in result.stderr.lower()
        ):
            raise RuntimeError(
                "Docker image inspection failed: " + result.stderr.strip()
            )
        return None
    return json.loads(result.stdout)[0]


def validate_image(info, identifier):
    if (
        info["Id"] != identifier
        or info.get("Os") != "linux"
        or info.get("Architecture") != "amd64"
    ):
        raise ValueError("Docker image identity or platform mismatch: " + identifier)


def framework_tag():
    """Use the native Harbor cache key for its network policy image."""
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    from harbor.environments.docker.docker import DockerEnvironment
    from harbor.environments.docker.utils import (
        docker_build_context_hash,
        _compute_image_name,
    )

    context = DockerEnvironment._EGRESS_CONTROL_SIDECAR_CONTEXT_PATH
    key = docker_build_context_hash(
        context=context,
        dockerfile_path=context / "Dockerfile",
        build_args={},
        platform="linux/amd64",
    )
    return _compute_image_name(
        "harbor-prebuilt:harbor-docker-egress-control-sidecar", key
    )


def ensure_framework(logs, *, local_only=False):
    record = json.loads((HERE / "framework/lock.json").read_text())
    if framework_tag() != record["local_tag"]:
        raise ValueError("Harbor network image does not match the installed package")
    info = inspect_image(record["local_tag"])
    if info:
        validate_image(info, record["image_id"])
    else:
        from .dataset import snapshot

        archive = snapshot(local_only=local_only) / "framework" / record["archive"]
        if digest(archive) != record["sha256"]:
            raise ValueError("Harbor network image archive checksum mismatch")
        with (logs / "framework-load.log").open("w") as log:
            subprocess.run(
                ["docker", "load", "-i", str(archive)],
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
            )
        validate_image(inspect_image(record["local_tag"]), record["image_id"])
    return {"image_id": record["image_id"], "local_tag": record["local_tag"]}


def acquire(tasks, logs, *, local_only=False, agent=None):
    """Resolve every image before starting any trial; never build an image."""
    configs = [read_task(task) for task in tasks]
    if agent:
        for task, config in zip(tasks, configs):
            if agent not in config["metadata"]["image"].get("agents", []):
                raise ValueError(
                    "Image does not declare offline setup for "
                    + agent
                    + ": "
                    + task.name
                )
    logs.mkdir(parents=True, exist_ok=False)
    report = {"local_only": local_only, "images": []}
    report_path = logs / "images.json"
    try:
        for task, config in zip(tasks, configs):
            record = config["metadata"]["image"]
            reference = record["reference"]
            info = inspect_image(reference)
            if info is None:
                # docker load may preserve the image ID without the registry alias.
                info = inspect_image(record["id"])
            pulled = False
            if info is None:
                if local_only:
                    raise ValueError(
                        "Missing local image for "
                        + task.name
                        + "; run securevibebench pull first"
                    )
                with (logs / (task.name + "-pull.log")).open("w") as log:
                    subprocess.run(
                        ["docker", "pull", "--platform", "linux/amd64", reference],
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        check=True,
                    )
                info = inspect_image(reference)
                pulled = True
            if info is None:
                raise ValueError("Docker did not load image: " + reference)
            validate_image(info, record["id"])
            report["images"].append(
                {
                    "task": task.name,
                    "reference": reference,
                    "image_id": info["Id"],
                    "pulled": pulled,
                }
            )
        report["framework"] = ensure_framework(logs, local_only=local_only)
        report["state"] = "completed"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
        raise
    finally:
        report_path.write_text(json.dumps(report, indent=2) + "\n")
    return report


def stage_task(task, destination, *, scoring=False, allow_hosts=()):
    config = read_task(task)
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copy2(task / "instruction.md", destination / "instruction.md")
    shutil.copytree(task / "tests", destination / "tests")
    # Docker already verified the registry digest and config ID in acquire().
    # The local ID prevents Harbor or Compose from pulling during execution.
    config["environment"]["docker_image"] = config["metadata"]["image"]["id"]
    if scoring:
        config["agent"]["network_mode"] = "no-network"
        config["agent"].pop("allowed_hosts", None)
    else:
        for host in allow_hosts:
            if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", host):
                raise ValueError("Use an exact model API hostname")
        config["agent"]["allowed_hosts"] = sorted(
            set(config["agent"]["allowed_hosts"]) | set(allow_hosts)
        )
    environment = destination / "environment"
    cpus = config["environment"].get("cpus", 2)
    if scoring:
        # Offline verification does not need a reachable DNS resolver.
        environment.mkdir()
        placement = ",".join(map(str, select_cpus(environment, cpus)))
        (environment / "docker-compose.yaml").write_text(
            'services:\n  main:\n    cpuset: "' + placement + '"\n'
        )
    else:
        configure_dns(environment, cpus)
    write_config(destination / "task.toml", config)
    return config
