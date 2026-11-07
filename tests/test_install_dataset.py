"""Installation bundles the pinned release and leaves a usable offline cache."""

import hashlib
import io
import json
import tarfile

import pytest

import build_backend


@pytest.fixture
def release(tmp_path, monkeypatch):
    contents = {
        "data/securevibebench-1/task.toml": b"task",
        "availability.json": json.dumps(
            {"tasks": [{"task": "securevibebench-1", "status": "supported"}]}
        ).encode(),
    }
    manifest = {
        "task_count": 1,
        "files_sha256": {
            name: hashlib.sha256(data).hexdigest() for name, data in contents.items()
        },
    }
    contents["manifest.json"] = json.dumps(manifest).encode()
    source = tmp_path / "tasks.tar.gz"
    with tarfile.open(source, "w:gz") as bundle:
        for name, data in contents.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            bundle.addfile(member, io.BytesIO(data))
    lock = {
        "repo_id": "fixture/tasks",
        "revision": "a" * 40,
        "task_count": 1,
        "manifest_sha256": hashlib.sha256(contents["manifest.json"]).hexdigest(),
        "archive": {
            "filename": "tasks.tar.gz",
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        },
    }
    dataset = build_backend.dataset
    monkeypatch.setattr(dataset, "release", lambda: lock)
    monkeypatch.setattr(dataset, "HERE", tmp_path / "package")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return source, lock


def test_build_downloads_the_pinned_archive_and_populates_the_cache(
    release, monkeypatch
):
    import huggingface_hub

    source, lock = release
    calls = []

    def download(*args, **kwargs):
        calls.append((args, kwargs))
        return str(source)

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", download)
    root = build_backend.prepare_dataset()
    assert calls == [
        (
            ("fixture/tasks", "tasks.tar.gz"),
            {"repo_type": "dataset", "revision": lock["revision"]},
        )
    ]
    assert (root / "data/securevibebench-1/task.toml").read_bytes() == b"task"
    assert build_backend.dataset.bundled_archive().read_bytes() == source.read_bytes()
    monkeypatch.setattr(
        huggingface_hub,
        "hf_hub_download",
        lambda *args, **kwargs: pytest.fail("Reinstallation downloaded verified data"),
    )
    assert build_backend.prepare_dataset() == root


def test_bad_download_aborts_install_without_accepting_data(release, monkeypatch):
    import huggingface_hub

    source, lock = release
    source.write_bytes(b"bad data")
    monkeypatch.setattr(
        huggingface_hub, "hf_hub_download", lambda *args, **kwargs: str(source)
    )
    with pytest.raises(ValueError, match="archive checksum"):
        build_backend.prepare_dataset()
    assert not build_backend.dataset.bundled_archive().exists()
    assert not build_backend.dataset.cache_root(lock).exists()


def test_changed_manifest_aborts_install(release, monkeypatch):
    import huggingface_hub

    source, lock = release
    lock["manifest_sha256"] = "0" * 64
    monkeypatch.setattr(
        huggingface_hub, "hf_hub_download", lambda *args, **kwargs: str(source)
    )
    with pytest.raises(ValueError, match="manifest checksum"):
        build_backend.prepare_dataset()
    assert not build_backend.dataset.cache_root(lock).exists()
