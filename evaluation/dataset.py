"""Download the pinned HF task release before network-restricted trials."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from pathlib import Path

from filelock import FileLock

HERE = Path(__file__).resolve().parent


def release():
    return json.loads((HERE / "dataset-lock.json").read_text())


def cache_root(lock=None):
    lock = lock or release()
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "securevibebench" / "datasets" / lock["revision"]


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_files(root, lock):
    """Check the release without importing evaluation dependencies."""
    manifest_path = root / "manifest.json"
    if checksum(manifest_path) != lock["manifest_sha256"]:
        raise ValueError("HF task manifest checksum mismatch")
    manifest = json.loads(manifest_path.read_text())
    for name, expected in manifest["files_sha256"].items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe HF task path: " + name)
        source = root / path
        if source.is_symlink() or checksum(source) != expected:
            raise ValueError("HF task checksum mismatch: " + name)
    expected_files = set(manifest["files_sha256"]) | {"manifest.json"}
    actual_files = {
        str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()
    }
    if expected_files != actual_files:
        raise ValueError("HF task file set changed: " + str(root))
    configs = list((root / "data").glob("*/task.toml"))
    if len(configs) != lock["task_count"] or len(configs) != manifest["task_count"]:
        raise ValueError("HF task count mismatch")
    availability = json.loads((root / "availability.json").read_text())
    supported = {
        row["task"] for row in availability["tasks"] if row["status"] == "supported"
    }
    if supported != {path.parent.name for path in configs}:
        raise ValueError("HF task availability mismatch")
    return root


def verify(root, lock):
    verify_files(root, lock)
    from .images import read_task

    for path in (root / "data").glob("*/task.toml"):
        config = read_task(path.parent)
        if json.loads((root / "manifest.json").read_text()).get("scoring_policy") == "functional-f2p-p2p-v1":
            from .functional import require_contract
            require_contract(path.parent, config)
    return root


def bundled_archive():
    return HERE / "bundled" / "tasks.tar.gz"


def extract(archive, destination):
    with tarfile.open(archive, "r:gz") as bundle:
        seen = set()
        for member in bundle.getmembers():
            path = Path(member.name)
            if (
                not member.isfile()
                or path.is_absolute()
                or ".." in path.parts
                or member.name in seen
            ):
                raise ValueError("Unsafe HF archive member: " + member.name)
            seen.add(member.name)
        bundle.extractall(destination, filter="data")


def snapshot(*, local_only=False):
    """Cache one verified immutable release; offline mode never contacts HF."""
    lock = release()
    root = cache_root(lock)
    root.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(root) + ".lock"):
        if root.exists():
            return verify(root, lock)
        archive = bundled_archive()
        if not archive.is_file():
            from huggingface_hub import hf_hub_download

            try:
                archive = Path(
                    hf_hub_download(
                        lock["repo_id"],
                        lock["archive"]["filename"],
                        repo_type="dataset",
                        revision=lock["revision"],
                        local_files_only=local_only,
                    )
                )
            except Exception as exc:
                if local_only:
                    raise ValueError(
                        "HF task cache is missing; reinstall the package or run "
                        "securevibebench pull before going offline"
                    ) from exc
                raise
        if checksum(archive) != lock["archive"]["sha256"]:
            raise ValueError("HF task archive checksum mismatch")
        with tempfile.TemporaryDirectory(
            prefix=".svb-tasks-", dir=root.parent
        ) as temporary:
            staged = Path(temporary) / "release"
            staged.mkdir()
            extract(archive, staged)
            verify(staged, lock)
            shutil.move(staged, root)
    return root


def resolve_tasks(root=None, *, local_only=False):
    return (
        Path(root).resolve()
        if root is not None
        else snapshot(local_only=local_only) / "data"
    )
