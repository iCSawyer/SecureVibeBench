"""Materialize release data locally; runtime never downloads tasks or agent source."""

from __future__ import annotations

import errno
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile


HERE = Path(__file__).resolve().parent


def manifest() -> dict:
    return json.loads((HERE / "resources.json").read_text())


def verify_resources(root: Path, record: dict) -> None:
    files = record["files_sha256"]
    required = ("dataset/harbor.yaml", "dataset/evaluator/harbor_verifier.py",
                "mini-swe-agent/pyproject.toml", "mini-swe-agent/README.md",
                "mini-swe-agent/LICENSE.md", "mini-swe-agent/src/minisweagent/__init__.py")
    if not all(name in files for name in required):
        raise ValueError("Packaged resource manifest is incomplete")
    for name, expected in files.items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Unsafe packaged resource path: {name}")
        path = root.joinpath(*relative.parts)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Packaged resource checksum mismatch: {name}")
    tasks = list((root / "dataset/data").glob("*/task.toml"))
    if not tasks or len(tasks) != record["task_count"]:
        raise ValueError("Packaged task count does not match the release manifest")


def materialize(cache_dir: Path) -> Path:
    """Keep package files read-only, and share a verified cache across invocations."""
    record = manifest()
    parent = cache_dir.expanduser().resolve()
    checkout = parent / record["archive_sha256"]
    if checkout.exists():
        verify_resources(checkout, record)
        return checkout
    archive = HERE / "resources.tar.gz"
    if hashlib.sha256(archive.read_bytes()).hexdigest() != record["archive_sha256"]:
        raise ValueError("Packaged resource archive checksum mismatch; reinstall securevibebench")
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".securevibebench-", dir=parent))
    try:
        with tarfile.open(archive, "r:gz") as tar:
            # Release archives contain regular files only, with every path listed.
            members = tar.getmembers()
            if {member.name for member in members} != set(record["files_sha256"]):
                raise ValueError("Packaged archive does not match its resource manifest")
            if not all(member.isfile() for member in members):
                raise ValueError("Packaged archive contains a non-file resource")
            tar.extractall(staging, filter="data")
        verify_resources(staging, record)
        try:
            staging.rename(checkout)
        except OSError as error:
            if error.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                raise
            verify_resources(checkout, record)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return checkout
