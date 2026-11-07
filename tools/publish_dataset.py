#!/usr/bin/env python3
"""Publish digest-backed tasks and availability metadata on HF full-habour."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tarfile
import tomllib

from huggingface_hub import HfApi, CommitOperationAdd, CommitOperationDelete

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from securevibebench_evaluation.images import read_task

REPO = "iCSawyer/SecureVibeBench"
BRANCH = "full-habour"
ARTIFACTS = {
    "manifest.json",
    "tasks.tar.gz",
    "availability.json",
    "image-catalog.json",
    "framework/lock.json",
    "framework/harbor-egress-control.tar.gz",
}
TASK_FILES = ("instruction.md", "task.toml", "tests/test.sh")


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def task_id(path):
    match = re.fullmatch(r"securevibebench-([0-9]+)", path.name)
    if not match:
        raise ValueError("Unexpected task directory: " + str(path))
    return match[1]


def stage(source, all_tasks, catalog, output, framework=None):
    """Export only runnable image tasks; list all other IDs as unsupported."""
    if output.exists():
        raise FileExistsError("Choose a new staging directory")
    known = {}
    for path in sorted(all_tasks.glob("*/task.toml")):
        config = tomllib.loads(path.read_text())
        known[task_id(path.parent)] = config["metadata"]
    if not known:
        raise ValueError("The benchmark task inventory is empty")
    registry = json.loads(catalog.read_text())
    entries = {str(item["task"]): item for item in registry["images"]}
    if len(entries) != len(registry["images"]) or registry["task_count"] != len(
        entries
    ):
        raise ValueError("Invalid image catalog count")
    tasks = {task_id(path.parent): path.parent for path in source.glob("*/task.toml")}
    if not tasks or tasks.keys() != entries.keys() or not tasks.keys() <= known.keys():
        raise ValueError(
            "Image catalog, source tasks, and benchmark inventory disagree"
        )
    for identifier, task in tasks.items():
        if entries[identifier].get("visibility") != "public" or entries[identifier].get("anonymous_manifest_verified") is not True:
            raise ValueError("HF task requires verified anonymous Public image access: " + identifier)
        config = read_task(task)
        image = config["metadata"]["image"]
        if any(
            image[key] != entries[identifier][key]
            for key in ("reference", "id", "platform", "agents", "baseline_sha256")
        ):
            raise ValueError("Image contract differs from catalog: " + identifier)
    output.mkdir(parents=True)
    for task in tasks.values():
        for name in TASK_FILES:
            destination = output / "data" / task.name / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(task / name, destination)
    availability = {
        "schema_version": 1,
        "benchmark_task_count": len(known),
        "supported_task_count": len(tasks),
        "unsupported_task_count": len(known) - len(tasks),
        "tasks": [],
    }
    for identifier in sorted(known, key=int):
        supported = identifier in tasks
        row = {
            "task": "securevibebench-" + identifier,
            "localid": identifier,
            "project": Path(known[identifier]["repo_cwd"]).name,
            "status": "supported" if supported else "unsupported",
        }
        if supported:
            image = entries[identifier]
            row.update(
                path="data/" + row["task"],
                image_reference=image["reference"],
                image_id=image["id"],
                image_visibility=entries[identifier]["visibility"],
                agents=image["agents"],
            )
        else:
            row.update(
                reason="missing_prepared_image",
                message="Temporarily unsupported: no published prepared image digest.",
            )
        availability["tasks"].append(row)
    if framework is not None:
        record = json.loads((framework / "lock.json").read_text())
        archive = framework / record["archive"]
        if (
            archive.name != "harbor-egress-control.tar.gz"
            or checksum(archive) != record["sha256"]
        ):
            raise ValueError("Invalid shared framework image archive")
        (output / "framework").mkdir()
        shutil.copy2(framework / "lock.json", output / "framework/lock.json")
        shutil.copy2(archive, output / "framework" / archive.name)
    write_json(output / "availability.json", availability)
    shutil.copy2(catalog, output / "image-catalog.json")
    files = {
        str(path.relative_to(output)): checksum(path)
        for path in sorted(output.rglob("*"))
        if path.is_file()
    }
    manifest = {
        "schema_version": 3,
        "task_layout": "digest-image-v1",
        "task_count": len(tasks),
        "benchmark_task_count": len(known),
        "unsupported_task_count": len(known) - len(tasks),
        "harbor_version": "0.25.0",
        "minimum_package_version": "0.3.0",
        "default_agent": "mini-swe-agent",
        "image_visibility": "private",
        "availability": "availability.json",
        "files_sha256": files,
    }
    write_json(output / "manifest.json", manifest)
    with (
        (output / "tasks.tar.gz").open("wb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as archive,
    ):
        for name in sorted([*files, "manifest.json"]):
            path = output / name
            info = archive.gettarinfo(str(path), arcname=name)
            info.uid = info.gid = info.mtime = 0
            info.uname = info.gname = ""
            with path.open("rb") as stream:
                archive.addfile(info, stream)
    return manifest


def verify_stage(output):
    manifest = json.loads((output / "manifest.json").read_text())
    expected = set(manifest["files_sha256"]) | {"manifest.json", "tasks.tar.gz"}
    actual = {
        str(path.relative_to(output)) for path in output.rglob("*") if path.is_file()
    }
    if actual != expected:
        raise ValueError("Staged file set changed")
    for name, value in manifest["files_sha256"].items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe dataset path")
        path = output / relative
        if path.is_symlink() or checksum(path) != value:
            raise ValueError("Staged checksum mismatch: " + name)
    availability = json.loads((output / "availability.json").read_text())
    supported = {
        row["task"] for row in availability["tasks"] if row["status"] == "supported"
    }
    runnable = {path.parent.name for path in (output / "data").glob("*/task.toml")}
    if supported != runnable or len(supported) != manifest["task_count"]:
        raise ValueError("Availability does not match runnable tasks")
    for path in (output / "data").glob("*/task.toml"):
        read_task(path.parent)
    expected_members = expected - {"tasks.tar.gz"}
    with tarfile.open(output / "tasks.tar.gz", "r:gz") as archive:
        members = archive.getmembers()
        if (
            len(members) != len(expected_members)
            or {item.name for item in members} != expected_members
        ):
            raise ValueError("Staged archive file set changed")
        for member in members:
            if not member.isfile():
                raise ValueError("Staged archive must contain regular files")
            with archive.extractfile(member) as stream:
                if hashlib.sha256(stream.read()).hexdigest() != checksum(
                    output / member.name
                ):
                    raise ValueError("Staged archive checksum mismatch: " + member.name)
    return manifest


def publish(output, expected_head):
    """Update the reviewed branch head; preserve README and unrelated files."""
    manifest = verify_stage(output)
    api = HfApi()
    if api.repo_info(REPO, repo_type="dataset", revision=BRANCH).sha != expected_head:
        raise ValueError(
            "Remote branch advanced; inspect its new head before publishing"
        )
    existing = set(
        api.list_repo_files(REPO, repo_type="dataset", revision=expected_head)
    )
    files = {
        str(path.relative_to(output)): path
        for path in output.rglob("*")
        if path.is_file()
    }
    if any(not (name.startswith("data/") or name in ARTIFACTS) for name in files):
        raise ValueError("Refuse to upload documents or unrelated files")
    deleted = sorted(
        name for name in existing - files.keys() if name.startswith("data/")
    )
    operations = [CommitOperationDelete(path_in_repo=name) for name in deleted]
    operations += [
        CommitOperationAdd(path_in_repo=name, path_or_fileobj=path)
        for name, path in sorted(files.items())
    ]
    plan = {
        "repo_id": REPO,
        "branch": BRANCH,
        "parent_commit": expected_head,
        "added_or_updated": sorted(files),
        "deleted": deleted,
        "preserved": sorted(existing - files.keys() - set(deleted)),
    }
    write_json(output.parent / "upload-plan.json", plan)
    commit = api.create_commit(
        REPO,
        repo_type="dataset",
        revision=BRANCH,
        parent_commit=expected_head,
        operations=operations,
        commit_message="Use prepared digest images; mark remaining tasks unsupported",
    )
    return {
        "repo_id": REPO,
        "branch": BRANCH,
        "revision": commit.oid,
        "task_count": manifest["task_count"],
        "benchmark_task_count": manifest["benchmark_task_count"],
        "unsupported_task_count": manifest["unsupported_task_count"],
        "archive": {
            "filename": "tasks.tar.gz",
            "sha256": checksum(output / "tasks.tar.gz"),
        },
        "manifest_sha256": checksum(output / "manifest.json"),
        "url": commit.commit_url,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--all-tasks", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--framework", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument(
        "--expected-head", help="Reviewed full-habour commit; required for upload"
    )
    args = parser.parse_args()
    if not args.output.exists():
        stage(args.source, args.all_tasks, args.catalog, args.output, args.framework)
    if args.publish:
        if not args.expected_head:
            parser.error("--publish requires --expected-head")
        record = publish(args.output, args.expected_head)
        write_json(Path("tools/image_build/publication-lock.json"), record)
        write_json(Path("evaluation/dataset-lock.json"), record)
        write_json(args.output.parent / "publication.json", record)
        print(json.dumps(record, indent=2))
    else:
        print(json.dumps(verify_stage(args.output), indent=2))


if __name__ == "__main__":
    main()
