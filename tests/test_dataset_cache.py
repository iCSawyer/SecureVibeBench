"""Task data comes from a verified HF release and works from an offline cache."""

import hashlib
import io
import json
import shutil
import tarfile
from pathlib import Path

import pytest
from securevibebench_evaluation import dataset


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def release(tmp_path, monkeypatch):
    source = tmp_path / "source"
    name = "securevibebench-992"
    shutil.copytree(
        Path(__file__).parents[1] / "example" / name, source / "data" / name
    )
    (source / "availability.json").write_text(
        json.dumps({"tasks": [{"task": name, "status": "supported"}]})
    )
    files = {
        str(p.relative_to(source)): digest(p) for p in source.rglob("*") if p.is_file()
    }
    (source / "manifest.json").write_text(
        json.dumps({"task_count": 1, "files_sha256": files})
    )
    archive = tmp_path / "tasks.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        for path in source.rglob("*"):
            if path.is_file():
                bundle.add(path, arcname=str(path.relative_to(source)))
    lock = {
        "repo_id": "fixture/tasks",
        "revision": "a" * 40,
        "task_count": 1,
        "archive": {"filename": "tasks.tar.gz", "sha256": digest(archive)},
        "manifest_sha256": digest(source / "manifest.json"),
    }
    monkeypatch.setattr(dataset, "release", lambda: lock)
    monkeypatch.setattr(dataset, "HERE", tmp_path / "package")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return archive, lock


def test_first_download_then_offline_cache_does_not_contact_hf(release, monkeypatch):
    import huggingface_hub

    archive, lock = release
    calls = []

    def download(*args, **kwargs):
        calls.append(kwargs)
        return str(archive)

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", download)
    root = dataset.snapshot()
    assert calls == [
        {
            "repo_type": "dataset",
            "revision": lock["revision"],
            "local_files_only": False,
        }
    ]
    monkeypatch.setattr(
        huggingface_hub,
        "hf_hub_download",
        lambda *args, **kwargs: pytest.fail("Offline cache contacted HF"),
    )
    assert dataset.snapshot(local_only=True) == root
    assert dataset.resolve_tasks(local_only=True) == root / "data"


def test_missing_offline_cache_forbids_network(release, monkeypatch):
    import huggingface_hub

    def download(*args, **kwargs):
        assert kwargs["local_files_only"] is True
        raise FileNotFoundError("not cached")

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", download)
    with pytest.raises(ValueError, match="cache is missing"):
        dataset.snapshot(local_only=True)


def test_changed_cache_is_rejected_without_refetch(release, monkeypatch):
    import huggingface_hub

    archive, _ = release
    monkeypatch.setattr(
        huggingface_hub, "hf_hub_download", lambda *args, **kwargs: str(archive)
    )
    root = dataset.snapshot()
    (root / "data/securevibebench-992/instruction.md").write_text("changed")
    monkeypatch.setattr(
        huggingface_hub,
        "hf_hub_download",
        lambda *args, **kwargs: pytest.fail("Unexpected refetch"),
    )
    with pytest.raises(ValueError, match="checksum mismatch"):
        dataset.snapshot(local_only=True)


def test_archive_digest_is_checked_before_extraction(release, monkeypatch):
    import huggingface_hub

    archive, _ = release
    archive.write_bytes(b"wrong archive")
    monkeypatch.setattr(
        huggingface_hub, "hf_hub_download", lambda *args, **kwargs: str(archive)
    )
    with pytest.raises(ValueError, match="archive checksum"):
        dataset.snapshot()


@pytest.mark.parametrize("kind", ["escape", "symlink", "duplicate"])
def test_unsafe_archive_members_are_rejected(tmp_path, kind):
    path = tmp_path / "unsafe.tar.gz"
    with tarfile.open(path, "w:gz") as bundle:
        entry = tarfile.TarInfo("../escape" if kind == "escape" else "data/file")
        if kind == "symlink":
            entry.type = tarfile.SYMTYPE
            entry.linkname = "/etc/passwd"
        bundle.addfile(entry, io.BytesIO(b""))
        if kind == "duplicate":
            bundle.addfile(entry, io.BytesIO(b""))
    with pytest.raises(ValueError, match="Unsafe HF archive"):
        dataset.extract(path, tmp_path / "destination")


def test_installed_bundle_restores_an_empty_cache_offline(release, monkeypatch):
    import huggingface_hub

    archive, _ = release
    bundled = dataset.bundled_archive()
    bundled.parent.mkdir(parents=True)
    shutil.copyfile(archive, bundled)
    monkeypatch.setattr(
        huggingface_hub,
        "hf_hub_download",
        lambda *args, **kwargs: pytest.fail("Installed data contacted HF"),
    )
    root = dataset.snapshot(local_only=True)
    assert (root / "data/securevibebench-992/task.toml").is_file()
    assert dataset.snapshot(local_only=True) == root


def test_changed_installed_bundle_fails_before_creating_cache(release, monkeypatch):
    import huggingface_hub

    _, lock = release
    bundled = dataset.bundled_archive()
    bundled.parent.mkdir(parents=True)
    bundled.write_bytes(b"changed archive")
    monkeypatch.setattr(
        huggingface_hub,
        "hf_hub_download",
        lambda *args, **kwargs: pytest.fail("Changed data triggered network"),
    )
    with pytest.raises(ValueError, match="archive checksum"):
        dataset.snapshot(local_only=True)
    assert not dataset.cache_root(lock).exists()
