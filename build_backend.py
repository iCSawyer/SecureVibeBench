"""Build packages with the checksum-verified, pinned HF task release."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from filelock import FileLock
from setuptools import build_meta

from evaluation import dataset

get_requires_for_build_wheel = build_meta.get_requires_for_build_wheel
get_requires_for_build_editable = build_meta.get_requires_for_build_editable
get_requires_for_build_sdist = build_meta.get_requires_for_build_sdist
prepare_metadata_for_build_wheel = build_meta.prepare_metadata_for_build_wheel
prepare_metadata_for_build_editable = build_meta.prepare_metadata_for_build_editable


def prepare_dataset():
    """Bundle one immutable archive and populate the installing user's cache."""
    lock = dataset.release()
    archive = dataset.bundled_archive()
    archive.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(archive) + ".lock"):
        if (
            not archive.is_file()
            or dataset.checksum(archive) != lock["archive"]["sha256"]
        ):
            from huggingface_hub import hf_hub_download

            print(
                "Downloading pinned SecureVibeBench HF release " + lock["revision"],
                flush=True,
            )
            source = Path(
                hf_hub_download(
                    lock["repo_id"],
                    lock["archive"]["filename"],
                    repo_type="dataset",
                    revision=lock["revision"],
                )
            )
            if dataset.checksum(source) != lock["archive"]["sha256"]:
                raise ValueError("HF task archive checksum mismatch")
            with tempfile.TemporaryDirectory(
                prefix=".download-", dir=archive.parent
            ) as folder:
                temporary = Path(folder) / archive.name
                shutil.copyfile(source, temporary)
                temporary.replace(archive)
        root = dataset.cache_root(lock)
        root.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(root) + ".lock"):
            if root.exists():
                dataset.verify_files(root, lock)
            else:
                with tempfile.TemporaryDirectory(
                    prefix=".svb-tasks-", dir=root.parent
                ) as folder:
                    staged = Path(folder) / "release"
                    staged.mkdir()
                    dataset.extract(archive, staged)
                    dataset.verify_files(staged, lock)
                    shutil.move(staged, root)
    print("Verified SecureVibeBench task data: " + str(root), flush=True)
    return root


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    prepare_dataset()
    return build_meta.build_wheel(wheel_directory, config_settings, metadata_directory)


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    prepare_dataset()
    return build_meta.build_editable(
        wheel_directory, config_settings, metadata_directory
    )


def build_sdist(sdist_directory, config_settings=None):
    prepare_dataset()
    return build_meta.build_sdist(sdist_directory, config_settings)
