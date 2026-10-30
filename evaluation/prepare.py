"""Download and verify HF tasks and evaluator without running evaluation."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import errno
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

if __package__:
    from .run import add_dataset_arguments, verify_bundle
else:
    from run import add_dataset_arguments, verify_bundle


class HubRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(request, fp, code, msg, headers, newurl)
        if redirected is not None and urlsplit(request.full_url).netloc != urlsplit(newurl).netloc:
            redirected.remove_header("Authorization")
        return redirected


def prepare_dataset(args: argparse.Namespace) -> Path:
    """Bootstrap the HF bundle using only Python's standard library."""
    endpoint = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
    repo = quote(args.hf_repo, safe="/")
    revision = quote(args.hf_revision, safe="")
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    def fetch(url: str) -> bytes:
        opener = build_opener(HubRedirectHandler())
        with opener.open(Request(url, headers=headers), timeout=120) as response:
            return response.read()

    info = json.loads(fetch(f"{endpoint}/api/datasets/{repo}/revision/{revision}"))
    commit = info["sha"]
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("HF returned an invalid dataset commit")
    args.resolved_hf_commit = commit
    parent = args.cache_dir.resolve() / "materialized"
    checkout = parent / commit
    if checkout.exists():
        return verify_bundle(checkout)

    base_url = f"{endpoint}/datasets/{repo}/resolve/{commit}"
    manifest_bytes = fetch(f"{base_url}/habour/preview-manifest.json")
    manifest = json.loads(manifest_bytes)
    files = []
    for name in manifest["files_sha256"]:
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Unsafe path in the HF manifest: {name}")
        if relative.parts[:1] == ("habour",):
            files.append(name)

    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="." + commit + "-", dir=parent))
    try:
        (staging / "habour").mkdir()
        (staging / "habour/preview-manifest.json").write_bytes(manifest_bytes)

        def download(name: str) -> None:
            path = staging.joinpath(*PurePosixPath(name).parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(fetch(f"{base_url}/{quote(name, safe='/')}"))

        print(f"Downloading HF bundle {args.hf_repo}@{commit} ({len(files)} files)...", flush=True)
        with ThreadPoolExecutor(max_workers=8) as pool:
            for _ in pool.map(download, files):
                pass
        verify_bundle(staging)
        try:
            staging.rename(checkout)
        except OSError as error:
            if error.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return verify_bundle(checkout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_dataset_arguments(parser)
    args = parser.parse_args(argv)
    try:
        bundle = prepare_dataset(args)
    except Exception as error:
        print(f"Cannot prepare HF dataset: {error}", file=sys.stderr)
        return 1
    print(f"HF commit: {args.resolved_hf_commit}")
    print(f"Prepared dataset and evaluator: {bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
