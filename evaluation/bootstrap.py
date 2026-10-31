"""Source installation and release-resource helpers using the standard library."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


HERE = Path(__file__).resolve().parent


def default_cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "securevibebench" / "huggingface"


class HubRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(request, fp, code, msg, headers, newurl)
        if redirected is not None and urlsplit(request.full_url).netloc != urlsplit(newurl).netloc:
            redirected.remove_header("Authorization")
        return redirected


def snapshot_files(record: dict) -> dict[str, str]:
    files = {}
    for name, digest in record["files_sha256"].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Unsafe HF manifest path: {name}")
        if relative.parts[:1] == ("habour",):
            files[name] = digest
    for required in ("habour/harbor.yaml", "habour/dev/harbor_verifier.py"):
        if required not in files:
            raise ValueError(f"HF manifest is missing {required}")
    return files


def verify_snapshot(snapshot: Path, task_count: int) -> None:
    record = json.loads((snapshot / "habour/preview-manifest.json").read_text())
    for name, digest in snapshot_files(record).items():
        path = snapshot / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"HF file checksum mismatch: {name}")
    found = len(list((snapshot / "habour/data").glob("*/task.toml")))
    if found == 0 or found != record["task_count"] or found != task_count:
        raise ValueError("HF task count does not match the pinned release")


def download_dataset(cache_dir: Path | None = None, *, release: dict | None = None) -> Path:
    if release is None:
        release = json.loads((HERE / "resources.json").read_text())
    commit = release["hf_commit"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid pinned HF commit")
    parent = (default_cache_dir() if cache_dir is None else cache_dir).expanduser().resolve()
    checkout = parent / commit
    if checkout.exists():
        verify_snapshot(checkout, release["task_count"])
        print(f"HF dataset verified: {checkout}", flush=True)
        return checkout

    endpoint = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
    repo = quote(release["hf_repo"], safe="/")
    base_url = f"{endpoint}/datasets/{repo}/resolve/{commit}"
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    def fetch(name: str) -> bytes:
        opener = build_opener(HubRedirectHandler())
        request = Request(f"{base_url}/{quote(name, safe='/')}", headers=headers)
        with opener.open(request, timeout=120) as response:
            return response.read()

    print(f"Downloading HF dataset {release['hf_repo']}@{commit}...", flush=True)
    manifest_bytes = fetch("habour/preview-manifest.json")
    files = snapshot_files(json.loads(manifest_bytes))
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".hf-dataset-", dir=parent))
    try:
        (staging / "habour").mkdir()
        (staging / "habour/preview-manifest.json").write_bytes(manifest_bytes)

        def download(item: tuple[str, str]) -> None:
            name, expected = item
            content = fetch(name)
            if hashlib.sha256(content).hexdigest() != expected:
                raise ValueError(f"HF file checksum mismatch: {name}")
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

        with ThreadPoolExecutor(max_workers=8) as pool:
            for _ in pool.map(download, files.items()):
                pass
        verify_snapshot(staging, release["task_count"])
        try:
            staging.rename(checkout)
        except OSError as error:
            if error.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                raise
            verify_snapshot(checkout, release["task_count"])
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    print(f"HF dataset verified: {checkout}", flush=True)
    return checkout


def install(root: Path, *, dev: bool = False, installer: str = "auto") -> None:
    uv = shutil.which("uv") if installer != "pip" else None
    if installer == "uv" and uv is None:
        raise RuntimeError("uv is unavailable; install it or choose --installer pip")
    if uv is not None:
        command = [uv, "sync"]
        if not dev:
            command += ["--no-dev", "--no-editable"]
    else:
        command = [sys.executable, "-m", "pip", "install"]
        if dev:
            command += ["-e", str(root)]
            config = tomllib.loads((root / "pyproject.toml").read_text())
            command += config["dependency-groups"]["dev"]
        else:
            command += [str(root)]
    subprocess.run(command, cwd=root, check=True)


def main(argv: list[str] | None = None, *, download_only: bool = False) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    if download_only:
        parser.add_argument("--cache-dir", type=Path, default=default_cache_dir())
    else:
        parser.add_argument("--dev", action="store_true", help="Install editable source and development tools")
        parser.add_argument("--installer", choices=["auto", "uv", "pip"], default="auto",
                            help="Prefer uv when available; otherwise use pip")
    args = parser.parse_args(argv)
    try:
        if download_only:
            download_dataset(args.cache_dir)
        else:
            install(HERE.parent, dev=args.dev, installer=args.installer)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Installation preparation failed: {error}", file=sys.stderr)
        return 1
    return 0
