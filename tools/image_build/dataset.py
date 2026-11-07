"""Fetch a pinned native Harbor dataset and verify every published task file."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import tempfile
import tarfile


def release():
    return json.loads(Path(__file__).with_name('dataset-lock.json').read_text())


def verify(snapshot, lock):
    manifest = snapshot / 'manifest.json'
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != lock['manifest_sha256']:
        raise ValueError('Dataset manifest checksum mismatch')
    record = json.loads(manifest.read_text())
    for name, expected in record['files_sha256'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or relative.parts[0] != 'data':
            raise ValueError('Unsafe dataset path: ' + name)
        path = snapshot / relative
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Dataset checksum mismatch: ' + name)
    if record.get('shared_assets_sha256'):
        from .task_assets import shared_hashes
        if record['shared_assets_sha256'] != shared_hashes():
            raise ValueError('Dataset requires different shared evaluation assets; update the installed package')
    configs = list((snapshot / 'data').glob('*/task.toml'))
    if len(configs) != lock['task_count'] or len(configs) != record['task_count']:
        raise ValueError('Dataset task count mismatch')
    return record


def extract_bundle(archive, destination):
    """Extract regular task files; reject links and paths outside the dataset."""
    seen = set()
    with tarfile.open(archive, 'r:gz') as bundle:
        members = bundle.getmembers()
        for member in members:
            path = Path(member.name)
            valid_root = path.parts and (path.parts[0] == 'data' or member.name == 'manifest.json')
            if path.is_absolute() or '..' in path.parts or not valid_root or not (member.isfile() or member.isdir()):
                raise ValueError('Unsafe dataset archive member: ' + member.name)
            if member.name in seen:
                raise ValueError('Duplicate dataset archive member: ' + member.name)
            seen.add(member.name)
        bundle.extractall(destination, members=members, filter='data')


def fetch(output):
    from huggingface_hub import snapshot_download, hf_hub_download
    lock = release()
    if output.exists():
        raise FileExistsError('Choose an absent output directory: ' + str(output))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.svb-fetch-', dir=output.parent) as temporary:
        staging = Path(temporary)
        if lock.get('archive'):
            record = lock['archive']
            archive = Path(hf_hub_download(repo_id=lock['repo_id'], repo_type='dataset',
                                          revision=lock['revision'], filename=record['filename']))
            if hashlib.sha256(archive.read_bytes()).hexdigest() != record['sha256']:
                raise ValueError('Dataset archive checksum mismatch')
            extract_bundle(archive, staging)
        else:
            snapshot_download(repo_id=lock['repo_id'], repo_type='dataset', revision=lock['revision'],
                              allow_patterns=['manifest.json', 'data/**'], local_dir=staging)
        verify(staging, lock)
        (staging / 'data').replace(output)
    (output / 'release.json').write_text(json.dumps(lock, indent=2) + '\n')
    print(f"Fetched {lock['task_count']} native Harbor tasks into {output}")
