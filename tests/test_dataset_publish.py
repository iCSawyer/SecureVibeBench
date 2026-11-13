"""HF updates contain digest-backed tasks and explicit unsupported statuses."""
import importlib.util
import json
from pathlib import Path
import shutil
import tarfile
from types import SimpleNamespace

import pytest
from securevibebench_evaluation.harbor_native import write_config
from securevibebench_evaluation.images import read_task
from securevibebench_evaluation.functional import task_fingerprint


def publisher():
    path = Path(__file__).parents[1] / 'tools/publish_dataset.py'
    spec = importlib.util.spec_from_file_location('svb_dataset_publisher', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def staged(tmp_path, qualified_task):
    module = publisher()
    source = tmp_path / 'source'
    all_tasks = tmp_path / 'all'
    ids = {'992', '32345'}
    for identifier in ids:
        name = 'securevibebench-' + identifier
        example = Path(__file__).parents[1]/'example/securevibebench-992'
        shutil.copytree(example, source / name)
        config = read_task(source / name)
        config['task']['name'] = 'securevibebench/' + name
        config['metadata']['localid'] = identifier
        write_config(source / name / 'task.toml', config)
        qualified_task(source / name)
        shutil.copytree(source / name, all_tasks / name)
    unavailable = all_tasks / 'securevibebench-999'
    unavailable.mkdir()
    (unavailable / 'task.toml').write_text('[metadata]\nrepo_cwd="/src/unavailable"\n')
    catalog = {'task_count': len(ids), 'images': [dict(read_task(source / ('securevibebench-'+identifier))['metadata']['image'], task=identifier, visibility='public', anonymous_manifest_verified=True) for identifier in ids]}
    path = tmp_path / 'catalog.json'
    path.write_text(json.dumps(catalog))
    output = tmp_path / 'stage'
    module.stage(source, all_tasks, path, output)
    return module, output


def test_stage_contains_only_digest_tasks_and_marks_others_unsupported(staged):
    module, output = staged
    manifest = module.verify_stage(output)
    assert manifest['task_count'] == 2
    assert manifest['benchmark_task_count'] == 3
    assert manifest['unsupported_task_count'] == 1
    records = json.loads((output / 'availability.json').read_text())['tasks']
    unsupported = next(row for row in records if row['localid'] == '999')
    assert unsupported['status'] == 'unsupported'
    assert unsupported['reason'] == 'missing_prepared_image'
    assert all(row['image_visibility'] == 'public' for row in records if row['status'] == 'supported')
    assert not (output / 'data/securevibebench-999').exists()
    assert not list(output.rglob('Dockerfile'))
    with tarfile.open(output / 'tasks.tar.gz') as archive:
        names = archive.getnames()
    assert 'availability.json' in names
    assert len([name for name in names if name.endswith('/task.toml')]) == 2
    assert not any('securevibebench-999/' in name for name in names)


def test_changed_staging_files_block_publication(staged):
    module, output = staged
    (output / 'data/securevibebench-992/instruction.md').write_text('changed')
    with pytest.raises(ValueError, match='checksum'):
        module.verify_stage(output)


def test_update_changes_only_dataset_artifacts(staged, monkeypatch):
    module, output = staged
    class API:
        def repo_info(self, *args, **kwargs):
            assert kwargs['revision'] == module.BRANCH
            return SimpleNamespace(sha='previous')
        def list_repo_files(self, *args, **kwargs):
            return ['README.md', '.gitattributes', 'data/obsolete/task.toml']
        def create_commit(self, *args, **kwargs):
            names = {operation.path_in_repo for operation in kwargs['operations']}
            assert kwargs['parent_commit'] == 'previous'
            assert kwargs['revision'] == 'full-habour'
            assert 'README.md' not in names and '.gitattributes' not in names
            assert 'data/obsolete/task.toml' in names
            assert {'manifest.json', 'tasks.tar.gz', 'availability.json', 'image-catalog.json'} <= names
            return SimpleNamespace(oid='next', commit_url='https://example.test/commit')
    monkeypatch.setattr(module, 'HfApi', API)
    result = module.publish(output, 'previous')
    assert result['revision'] == 'next' and result['task_count'] == 2
    assert result['unsupported_task_count'] == 1
    assert result['task_fingerprints'] == {path.name: task_fingerprint(path)
                                           for path in (output / 'data').iterdir()}


def test_update_rejects_changed_remote_head(staged, monkeypatch):
    module, output = staged
    monkeypatch.setattr(module, 'HfApi', lambda: SimpleNamespace(repo_info=lambda *args, **kwargs: SimpleNamespace(sha='advanced')))
    with pytest.raises(ValueError, match='Remote branch advanced'):
        module.publish(output, 'previous')


def test_archive_cannot_include_unsupported_tasks(staged):
    module, output = staged
    with tarfile.open(output / 'tasks.tar.gz', 'w:gz') as archive:
        import io
        content = b'unsupported task'
        member = tarfile.TarInfo('data/securevibebench-999/task.toml')
        member.size = len(content)
        archive.addfile(member, io.BytesIO(content))
    with pytest.raises(ValueError, match='archive file set'):
        module.verify_stage(output)


def test_ready_image_without_qualified_tests_stays_unsupported(staged, tmp_path):
    module, existing = staged
    source = existing / 'data'
    shutil.rmtree(source / 'securevibebench-32345')
    output = tmp_path / 'unqualified-stage'
    module.stage(source, tmp_path / 'all', tmp_path / 'catalog.json', output)
    manifest = module.verify_stage(output)
    assert manifest['task_count'] == 1
    assert manifest['prepared_image_count'] == 2
    records = json.loads((output / 'availability.json').read_text())['tasks']
    pending = next(item for item in records if item['localid'] == '32345')
    assert pending['status'] == 'unsupported'
    assert pending['scoring_status'] == 'needs-tests'
    assert pending['image_ready']
    assert not (output / 'data/securevibebench-32345').exists()


def test_unqualified_source_blocks_staging_before_writing(staged, tmp_path):
    module, existing = staged
    source = existing / 'data'
    (source / 'securevibebench-32345/tests/functional.json').unlink()
    output = tmp_path / 'invalid-source-stage'
    with pytest.raises(ValueError, match='needs F2P/P2P qualification'):
        module.stage(source, tmp_path / 'all', tmp_path / 'catalog.json', output)
    assert not output.exists()


def test_export_rejects_unresolved_cases_even_if_exclusion_summary_is_missing(monkeypatch, tmp_path):
    module = publisher()
    contract = {'cases': [{'id': 'feature'}, {'id': 'regression'}, {'id': 'unresolved'}],
                'FAIL_TO_PASS': ['feature'], 'PASS_TO_PASS': ['regression'],
                'qualification': {}}
    monkeypatch.setattr(module, 'require_contract', lambda *args: contract)
    with pytest.raises(ValueError, match='excluded functional cases'):
        module.require_export_contract(tmp_path / 'securevibebench-1')
    contract['PASS_TO_PASS'].append('unresolved')
    assert module.require_export_contract(tmp_path / 'securevibebench-1') is contract
