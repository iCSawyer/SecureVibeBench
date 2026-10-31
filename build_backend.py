"""PEP 517 backend that fetches the pinned HF dataset during installation."""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import tarfile
import tempfile

from setuptools import build_meta as _backend


ROOT = Path(__file__).resolve().parent


def _prepare_resources() -> None:
    package = ROOT / "evaluation"
    release = json.loads((package / "resources.json").read_text())
    spec = importlib.util.spec_from_file_location("svb_build_bootstrap", package / "bootstrap.py")
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    snapshot = bootstrap.download_dataset(release=release)

    with tarfile.open(package / "mini-source.tar.gz", "r:gz") as source:
        mini = {}
        for member in source.getmembers():
            if not member.isfile() or not member.name.startswith("mini-swe-agent/"):
                raise ValueError(f"Invalid bundled agent source: {member.name}")
            mini[member.name] = source.extractfile(member).read()

    with tempfile.TemporaryDirectory(prefix=".svb-build-", dir=ROOT) as temporary:
        archive = Path(temporary) / "resources.tar.gz"
        with archive.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w") as tar:
                for name, expected in sorted(release["files_sha256"].items()):
                    relative = PurePosixPath(name)
                    if relative.is_absolute() or ".." in relative.parts:
                        raise ValueError(f"Unsafe resource path: {name}")
                    if name.startswith("dataset/evaluator/"):
                        path = snapshot / "habour/dev" / name.removeprefix("dataset/evaluator/")
                        content = path.read_bytes()
                    elif name.startswith("dataset/"):
                        content = (snapshot / "habour" / name.removeprefix("dataset/")).read_bytes()
                    else:
                        content = mini[name]
                    if hashlib.sha256(content).hexdigest() != expected:
                        raise ValueError(f"Resource checksum mismatch: {name}")
                    info = tarfile.TarInfo(name)
                    info.size, info.mode = len(content), 0o644
                    tar.addfile(info, io.BytesIO(content))
        # Compression output can vary with Python/zlib versions. File checksums
        # above pin the content; record the archive produced by this build.
        release["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
        archive.replace(package / "resources.tar.gz")
        (package / "resources.json").write_text(json.dumps(release, indent=2) + "\n")


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    _prepare_resources()
    return _backend.build_wheel(wheel_directory, config_settings, metadata_directory)


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    _prepare_resources()
    return _backend.build_editable(wheel_directory, config_settings, metadata_directory)


build_sdist = _backend.build_sdist
get_requires_for_build_sdist = _backend.get_requires_for_build_sdist
get_requires_for_build_wheel = _backend.get_requires_for_build_wheel
get_requires_for_build_editable = _backend.get_requires_for_build_editable
prepare_metadata_for_build_wheel = _backend.prepare_metadata_for_build_wheel
prepare_metadata_for_build_editable = _backend.prepare_metadata_for_build_editable
