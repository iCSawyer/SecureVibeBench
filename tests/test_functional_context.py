"""Check source-context boundaries using real repositories and source files."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools.functional.batch import CONTEXT_PROBE


def probe(repo, paths, revision=None):
    completed = subprocess.run(
        [sys.executable, '-I', '-c', CONTEXT_PROBE,
         json.dumps({'repo': str(repo), 'paths': paths, 'revision': revision,
                     'prepared_dependency': revision is None, 'image': 'sha256:test-image'})],
        capture_output=True, text=True, check=True,
    )
    return json.loads(completed.stdout)


def test_large_dissector_and_private_source_formats_are_available(tmp_path):
    (tmp_path / 'dissector.c').write_text('/* source */\n' * 50000)
    for suffix in ['hh', 'spec', 'inc', 'def']:
        (tmp_path / f'input.{suffix}').write_text('/* declaration */\n')
    paths = ['dissector.c', 'input.hh', 'input.spec', 'input.inc', 'input.def']
    result = probe(tmp_path, paths)
    assert len(result['dissector.c']['text']) > 500000
    assert all('text' in result[path] for path in paths)


def test_context_denies_credentials_binary_and_escaping_symlinks(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    (tmp_path / 'outside.c').write_text('private data')
    (repo / 'escape.c').symlink_to(tmp_path / 'outside.c')
    (repo / '.env').write_text('SENSITIVE_VALUE_007')
    (repo / '.private').mkdir()
    (repo / '.private/hidden.c').write_text('SENSITIVE_VALUE_007')
    (repo / 'hidden.c').symlink_to(repo / '.private/hidden.c')
    (repo / 'binary.c').write_bytes(b'abc\x00def')
    result = probe(repo, ['../outside.c', str(tmp_path / 'outside.c'), 'escape.c', 'hidden.c', '.env', 'binary.c'])
    assert all('error' in item and 'text' not in item for item in result.values())
    assert 'private data' not in json.dumps(result)
    assert 'SENSITIVE_VALUE_007' not in json.dumps(result)


def test_missing_filename_suggests_only_versioned_source_paths(tmp_path):
    subprocess.run(['git', 'init', '--quiet', str(tmp_path)], check=True)
    (tmp_path / 'cmake').mkdir()
    (tmp_path / 'cmake/FindCARES.cmake').write_text('# source\n')
    (tmp_path / 'untracked').mkdir()
    (tmp_path / 'untracked/FindCARES.cmake').write_text('# untracked\n')
    (tmp_path / '.private').mkdir()
    (tmp_path / '.private/FindCARES.cmake').write_text('private')
    subprocess.run(['git', '-C', str(tmp_path), 'add', 'cmake', '.private'], check=True)
    result = probe(tmp_path, ['wrong/FindCARES.cmake'])
    assert result['wrong/FindCARES.cmake']['suggestions'] == ['cmake/FindCARES.cmake']


def test_oversized_source_is_reported_without_loading_it(tmp_path):
    with (tmp_path / 'huge.c').open('wb') as stream:
        stream.truncate(32 * 1024 * 1024 + 1)
    result = probe(tmp_path, ['huge.c'])['huge.c']
    assert 'text' not in result
    assert result['bytes'] == 32 * 1024 * 1024 + 1
    assert 'limit' in result['error']


def commit(repo):
    subprocess.run(['git', 'init', '--quiet', str(repo)], check=True)
    subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                    'commit', '--quiet', '-m', 'Source snapshot'], check=True)
    return subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()


def test_reference_blob_is_used_even_when_parent_worktree_differs(tmp_path):
    (tmp_path / 'source.hh').write_text('reference declaration\n')
    revision = commit(tmp_path)
    (tmp_path / 'source.hh').write_text('different parent HEAD worktree\n')
    result = probe(tmp_path, ['source.hh'], revision)['source.hh']
    assert result['text'] == 'reference declaration\n'
    assert result['revision'] == revision
    assert result['requested_revision'] == revision
    assert result['source'] == 'git-reference'
    assert len(result['git_blob']) == 40 and len(result['sha256']) == 64


def test_missing_reference_file_never_falls_back_to_parent_generated_header(tmp_path):
    (tmp_path / 'source.c').write_text('reference\n')
    revision = commit(tmp_path)
    (tmp_path / 'generated.h').write_text('parent build header\n')
    result = probe(tmp_path, ['generated.h'], revision)['generated.h']
    assert 'text' not in result and 'no worktree fallback' in result['error']
    dependency = probe(tmp_path, ['generated.h'])['generated.h']
    assert dependency['text'] == 'parent build header\n'
    assert dependency['source'] == 'prepared-dependency'
    assert dependency['image'] == 'sha256:test-image'
    assert dependency['revision'] == revision and len(dependency['sha256']) == 64


def test_reference_symlinks_are_rejected_even_if_worktree_target_is_source(tmp_path):
    (tmp_path / 'target.c').write_text('reference\n')
    (tmp_path / 'link.c').symlink_to('target.c')
    revision = commit(tmp_path)
    result = probe(tmp_path, ['link.c'], revision)['link.c']
    assert 'text' not in result and 'regular source blob' in result['error']


def test_all_missing_context_is_logged_without_creating_phantom_source(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from tools.functional import batch
    output = tmp_path / 'evidence'
    output.mkdir()
    result = {'cmake/missing.cmake': {'error': 'absent from reference', 'revision': 'a' * 40}}
    monkeypatch.setattr(batch.subprocess, 'run', lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout=json.dumps(result), stderr=''))
    context = {'task': '1', 'repo': '/src/project', 'parent_image': 'sha256:parent',
               'prepared_image': 'sha256:prepared', 'reference': 'a' * 40}
    job = tmp_path / 'workspace'
    assert batch.extra_context(context, ['cmake/missing.cmake'], job, output) == result
    assert json.loads((job / 'context/extra-provenance.json').read_text()) == result
    assert not (job / 'context/extra/cmake/missing.cmake').exists()
