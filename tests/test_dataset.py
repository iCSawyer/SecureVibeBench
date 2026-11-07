import hashlib
import json
from pathlib import Path
import pytest
from tools.image_build.dataset import verify


def snapshot(tmp_path):
    task=tmp_path/'data/securevibebench-992/task.toml';task.parent.mkdir(parents=True);task.write_text('task')
    manifest={'task_count':1,'files_sha256':{'data/securevibebench-992/task.toml':hashlib.sha256(task.read_bytes()).hexdigest()}}
    path=tmp_path/'manifest.json';path.write_text(json.dumps(manifest))
    lock={'task_count':1,'manifest_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    return task,lock


def test_dataset_file_hashes_are_verified(tmp_path):
    task,lock=snapshot(tmp_path)
    verify(tmp_path,lock)
    task.write_text('changed')
    with pytest.raises(ValueError,match='checksum'):verify(tmp_path,lock)


def test_manifest_cannot_change_independently_of_pinned_lock(tmp_path):
    _,lock=snapshot(tmp_path)
    (tmp_path/'manifest.json').write_text('{}')
    with pytest.raises(ValueError,match='manifest checksum'):verify(tmp_path,lock)


def test_manifest_rejects_path_escape(tmp_path):
    _,lock=snapshot(tmp_path)
    path=tmp_path/'manifest.json';path.write_text(json.dumps({'files_sha256':{'../secret':'bad'},'task_count':1}))
    lock['manifest_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError,match='Unsafe'):verify(tmp_path,lock)


def test_fetch_uses_one_verified_bundle(tmp_path, monkeypatch):
    import tarfile
    import huggingface_hub
    from tools.image_build import dataset
    original = tmp_path / 'snapshot'
    _, lock = snapshot(original)
    archive = tmp_path / 'tasks.tar.gz'
    with tarfile.open(archive, 'w:gz') as bundle:
        for path in original.rglob('*'):
            if path.is_file():
                bundle.add(path, arcname=str(path.relative_to(original)))
    lock.update(repo_id='example/tasks', revision='fixed', archive={
        'filename': 'tasks.tar.gz', 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()})
    calls = []
    def download(**kwargs):
        calls.append(kwargs)
        return str(archive)
    monkeypatch.setattr(dataset, 'release', lambda: lock)
    monkeypatch.setattr(huggingface_hub, 'hf_hub_download', download)
    monkeypatch.setattr(huggingface_hub, 'snapshot_download', lambda **kwargs: pytest.fail('Per-file download used'))
    dataset.fetch(tmp_path / 'fetched')
    assert (tmp_path / 'fetched/securevibebench-992/task.toml').read_text() == 'task'
    assert len(calls) == 1 and calls[0]['revision'] == 'fixed'


@pytest.mark.parametrize('kind', ['escape', 'symlink', 'hardlink'])
def test_bundle_rejects_unsafe_members(tmp_path, kind):
    import tarfile
    from tools.image_build.dataset import extract_bundle
    archive = tmp_path / 'tasks.tar.gz'
    with tarfile.open(archive, 'w:gz') as bundle:
        member = tarfile.TarInfo('../escape' if kind == 'escape' else 'data/task/link')
        if kind != 'escape':
            member.type = tarfile.SYMTYPE if kind == 'symlink' else tarfile.LNKTYPE
            member.linkname = '/etc/passwd'
        bundle.addfile(member)
    with pytest.raises(ValueError, match='Unsafe'):
        extract_bundle(archive, tmp_path / 'extracted')
    assert not (tmp_path / 'escape').exists()


def test_compaction_archives_original_task_files(tmp_path, monkeypatch):
    from tools.image_build.task_assets import compact_task
    monkeypatch.chdir(tmp_path)
    task = tmp_path / 'securevibebench-1'
    script = task / 'tests/original/test.sh'
    script.parent.mkdir(parents=True)
    script.write_text('unique original task test\n')
    (task / 'tests/test.sh').write_text('old entrypoint\n')
    runtime = task / 'environment/svb/runtime.py'
    runtime.parent.mkdir(parents=True)
    runtime.write_text('known old shared runtime\n')
    sha = hashlib.sha256(runtime.read_bytes()).hexdigest()
    compact_task(task, {'environment/svb/runtime.py': sha})
    archive = next((tmp_path / '.cache/securevibebench/task-asset-archive/securevibebench-1').iterdir())
    assert (archive / 'tests/original/test.sh').read_text() == 'unique original task test\n'
    assert (archive / 'test.sh.before').read_text() == 'old entrypoint\n'
    assert hashlib.sha256((archive / 'environment/svb/runtime.py').read_bytes()).hexdigest() == sha
    assert '/opt/svb/runtime.py verify' in (task / 'tests/test.sh').read_text()
