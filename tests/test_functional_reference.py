"""Verify functional-reference corrections against real Git objects."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tools.functional.reference import PROBE


def git(repo, *args):
    return subprocess.check_output(['git', *args], cwd=repo, text=True)


@pytest.fixture
def source(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    git(repo, 'init', '--quiet')
    git(repo, 'config', 'user.email', 'test@example.invalid')
    git(repo, 'config', 'user.name', 'Test')
    (repo / 'source.c').write_text('int feature(void) { return 0; }\n')
    (repo / 'obsolete.c').write_text('int obsolete;\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '--quiet', '-m', 'base')
    git(repo, 'tag', 'svb-start')
    return repo


def test_combined_reference_preserves_changes_deletions_and_new_files(source, tmp_path):
    repo = source
    (repo / 'source.c').write_text('int feature(void) { return 1; }\n')
    (repo / 'new.c').write_text('int new_feature;\n')
    git(repo, 'add', '.')
    feature = tmp_path / 'feature.patch'
    feature.write_text(git(repo, 'diff', '--cached', '--binary', '--full-index'))
    git(repo, 'commit', '--quiet', '-m', 'original reference')
    original_tree = git(repo, 'rev-parse', 'HEAD^{tree}').strip()
    (repo / 'source.c').write_text('int feature(void) { return 2; }\n')
    (repo / 'obsolete.c').unlink()
    (repo / 'extra.c').write_text('int extra;\n')
    git(repo, 'add', '-A')
    correction = tmp_path / 'correction.patch'
    correction.write_text(git(repo, 'diff', '--cached', '--binary', '--full-index'))
    expected = git(repo, 'write-tree').strip()
    git(repo, 'reset', '--hard', 'svb-start')
    result = subprocess.check_output([sys.executable, '-I', '-c', PROBE, str(repo), str(feature), str(correction)])
    trees = json.loads(result)
    assert trees['reference_tree'] == expected
    assert trees['original_reference_tree'] == original_tree
    assert set(trees['paths']) == {'source.c', 'new.c', 'obsolete.c', 'extra.c'}
    assert git(repo, 'status', '--porcelain') == ''
    assert (repo / 'source.c').read_text().endswith('return 0; }\n')
    combined = tmp_path / 'combined.patch'
    combined.write_bytes(base64.b64decode(trees['patch_base64']))
    git(repo, 'apply', '--index', str(combined))
    assert git(repo, 'write-tree').strip() == expected
    assert not (repo / 'obsolete.c').exists()


def test_correction_must_apply_to_original_reference_not_the_start(source, tmp_path):
    repo = source
    (repo / 'source.c').write_text('int feature(void) { return 1; }\n')
    git(repo, 'add', '.')
    feature = tmp_path / 'feature.patch'
    feature.write_text(git(repo, 'diff', '--cached'))
    # Applying the original delta twice must fail rather than produce a false tree.
    git(repo, 'reset', '--hard', 'svb-start')
    result = subprocess.run([sys.executable, '-I', '-c', PROBE, str(repo), str(feature), str(feature)], capture_output=True)
    assert result.returncode != 0
    assert b'patch does not apply' in result.stderr
    assert git(repo, 'status', '--porcelain') == ''


def test_reference_provenance_uses_the_consumed_input_snapshot(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import hashlib
    from tools.functional import reference
    paths = {name: tmp_path / name for name in ['feature.patch', 'correction.patch', 'rationale.md']}
    original = {name: ('original ' + name).encode() for name in paths}
    for name, path in paths.items():
        path.write_bytes(original[name])
    config = {'metadata': {'image': {'id': 'sha256:' + 'a' * 64},
                           'vic': 'b' * 40, 'repo_cwd': '/src/project'}}
    monkeypatch.setattr(reference, 'read_task', lambda path: config)
    monkeypatch.setattr(reference, 'inspect_image', lambda image: {})
    monkeypatch.setattr(reference, 'validate_image', lambda *args: None)
    consumed = {}
    def run(command, **kwargs):
        for name in ['feature.patch', 'correction.patch']:
            suffix = ':/' + name + ':ro'
            mounted = next(value[:-len(suffix)] for value in command if value.endswith(suffix))
            consumed[name] = Path(mounted).read_bytes()
        # The author can continue writing its own files while the probe runs.
        for path in paths.values():
            path.write_bytes(b'changed after probe started')
        result = {'base_tree': '1' * 40, 'original_reference_tree': '2' * 40,
                  'reference_tree': '3' * 40, 'paths': ['source.c'],
                  'patch_base64': base64.b64encode(b'combined patch').decode()}
        return SimpleNamespace(returncode=0, stdout=json.dumps(result).encode(), stderr=b'')
    monkeypatch.setattr(reference.subprocess, 'run', run)
    output = tmp_path / 'snapshot'
    proof = reference.prepare(tmp_path / 'securevibebench-1', paths['feature.patch'],
                              paths['correction.patch'], paths['rationale.md'], output)
    for name in paths:
        assert (output / name).read_bytes() == original[name]
    assert consumed == {name: original[name] for name in consumed}
    assert proof['feature_patch_sha256'] == hashlib.sha256(original['feature.patch']).hexdigest()
    assert proof['correction_patch_sha256'] == hashlib.sha256(original['correction.patch']).hexdigest()
    assert proof['rationale_sha256'] == hashlib.sha256(original['rationale.md']).hexdigest()
