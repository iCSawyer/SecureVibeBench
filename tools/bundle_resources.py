#!/usr/bin/env python3
"""Maintainer tool: bundle pinned upstream resources before building a release."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import importlib.util
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parents[1]
HF_REPO = "iCSawyer/SecureVibeBench"
HF_COMMIT = "5fa48dd35fe29565adaa020dd2d333b650f3e621"
HF_TASK_COUNT = 105
MINI_REPO = "https://github.com/SWE-agent/mini-swe-agent.git"
MINI_TAG = "v2.4.6"
MINI_COMMIT = "a83fcae82d2a08f0ee0c688f9d137b3566c097f8"


def bundle(snapshot: Path, mini: Path, output: Path) -> None:
    upstream = json.loads((snapshot / "habour/preview-manifest.json").read_text())
    files: dict[str, bytes] = {}
    for name, expected in upstream["files_sha256"].items():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Unsafe upstream path: {name}")
        if name.startswith("habour/data/") or name in ("habour/LICENSE", "habour/harbor.yaml"):
            target = "dataset/" + name.removeprefix("habour/")
        elif name == "habour/dev/harbor_verifier.py":
            target = "dataset/evaluator/harbor_verifier.py"
        else:
            continue
        content = (snapshot / name).read_bytes()
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"Upstream checksum mismatch: {name}")
        files[target] = content

    commit = subprocess.check_output(["git", "-C", str(mini), "rev-parse", "HEAD"], text=True).strip()
    if commit != MINI_COMMIT:
        raise ValueError(f"Expected mini-swe-agent commit {MINI_COMMIT}, got {commit}")
    subprocess.run(["git", "-C", str(mini), "diff", "--exit-code", "HEAD"], check=True)
    names = subprocess.check_output(["git", "-C", str(mini), "ls-files", "-z"], text=True).split("\0")
    for name in names:
        if name in ("pyproject.toml", "README.md", "LICENSE.md") or name.startswith("src/"):
            files["mini-swe-agent/" + name] = (mini / name).read_bytes()

    output.mkdir(parents=True, exist_ok=True)
    archive = output / "resources.tar.gz"
    for filename, contents in (
        ("resources.tar.gz", files),
        ("mini-source.tar.gz", {name: value for name, value in files.items() if name.startswith("mini-swe-agent/")}),
    ):
        with (output / filename).open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w") as tar:
                for name, content in sorted(contents.items()):
                    info = tarfile.TarInfo(name)
                    info.size, info.mode = len(content), 0o644
                    tar.addfile(info, io.BytesIO(content))
    record = {
        "hf_repo": HF_REPO, "hf_commit": HF_COMMIT,
        "mini_repository": MINI_REPO, "mini_tag": MINI_TAG, "mini_commit": MINI_COMMIT,
        "task_count": upstream["task_count"],
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "files_sha256": {name: hashlib.sha256(content).hexdigest() for name, content in sorted(files.items())},
    }
    (output / "resources.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"Bundled {record['task_count']} tasks and mini-swe-agent {MINI_TAG}: {archive.stat().st_size:,} bytes")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hf-snapshot", type=Path, help="Existing snapshot of the pinned HF commit")
    parser.add_argument("--mini-source", type=Path, help="Existing clean checkout of the pinned mini-swe-agent commit")
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="svb-release-") as temporary:
        snapshot = args.hf_snapshot
        if snapshot is None:
            spec = importlib.util.spec_from_file_location("svb_bootstrap", ROOT / "evaluation/bootstrap.py")
            bootstrap = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(bootstrap)
            snapshot = bootstrap.download_dataset(release={
                "hf_repo": HF_REPO, "hf_commit": HF_COMMIT, "task_count": HF_TASK_COUNT,
            })
        mini = args.mini_source
        if mini is None:
            mini = Path(temporary) / "mini-swe-agent"
            subprocess.run(["git", "clone", "--depth", "1", "--branch", MINI_TAG, MINI_REPO, str(mini)], check=True)
        bundle(snapshot.resolve(), mini.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
