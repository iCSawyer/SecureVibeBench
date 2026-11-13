"""Keep contract reuse separate from image-specific qualification evidence."""
import errno
import json
from pathlib import Path

import pytest

from tools.functional import reuse
from tools.functional.authoring import verify_inputs, contract_hash


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def reusable(tmp_path):
    root = tmp_path / 'run'
    for identifier in ['1', '2']:
        source = root / 'batch-sources' / identifier
        write(source / 'context.json', {'reference': 'reference', 'reference_tree': identifier * 40, 'repo': '/src/project'})
        write(source / 'sources.json', {'base': 'base', 'reference': 'reference', 'diff': 'feature', 'files': {}, 'headers': {}})
        (source / 'instruction.md').write_text('Implement the requested feature.\n')
    original = root / 'approved/securevibebench-1'
    contract = original / 'tests/contract'
    write(contract / 'spec.json', {'reference_tree': '1' * 40, 'cases': [{'id': 'feature', 'command': ['/tmp/test']}], 'granularity': 'behavior'})
    (contract / 'check.c').write_text('int main(void) { return 0; }\n')
    write(original / 'tests/functional.json', {'qualification': {'image': 'origin-only'}})
    write(root / 'batch/tasks/1/result.json', {'task_path': str(original), 'review': {'approved': True, 'test_level': 'behavior'}})
    review = root / 'batch/tasks/1/attempts/01/review'
    write(review / 'result.json', {'approved': True, 'test_level': 'behavior'})
    write(review / 'contract-sha256.json', {'sha256': contract_hash(contract)})
    return root


def test_reuse_requires_new_measurements_and_seals_original_inputs(reusable):
    root = reusable
    assert reuse.seed(root, '2', '1')
    job = root / 'batch/tasks/2'
    spec = json.loads((job / 'workspace/contract/spec.json').read_text())
    assert spec['reference_tree'] == '2' * 40
    assert not list(job.rglob('functional.json'))
    assert not list(job.rglob('measure.json'))
    assert not (job / 'result.json').exists()
    provenance = json.loads((job / 'reuse-provenance.json').read_text())
    assert provenance['qualification_reused'] is False
    checkpoint = job / 'attempts/01/trusted-inputs'
    verify_inputs(job / 'workspace', checkpoint)
    (job / 'workspace/instruction.md').write_text('Altered input')
    with pytest.raises(ValueError, match='restored'):
        verify_inputs(job / 'workspace', checkpoint)
    assert (job / 'workspace/instruction.md').read_text() == 'Implement the requested feature.\n'


@pytest.mark.parametrize('change', ['instruction', 'base', 'reference', 'repo'])
def test_reuse_rejects_distinct_requirements_or_source_context(reusable, change):
    source = reusable / 'batch-sources/2'
    if change == 'instruction':
        (source / 'instruction.md').write_text('Different requested feature')
    else:
        path = source / ('context.json' if change == 'repo' else 'sources.json')
        content = json.loads(path.read_text())
        content[change] = 'different'
        write(path, content)
    assert reuse.seed(reusable, '2', '1') is False
    assert not (reusable / 'batch/tasks/2').exists()


def test_worker_claim_race_keeps_workers_files(reusable, monkeypatch):
    rename = Path.rename
    def claim(path, target):
        if path.name.startswith('.seed-'):
            target.mkdir()
            (target / 'worker.txt').write_text('in progress')
            raise OSError(errno.ENOTEMPTY, 'Directory not empty')
        return rename(path, target)
    monkeypatch.setattr(Path, 'rename', claim)
    assert reuse.seed(reusable, '2', '1') is False
    assert (reusable / 'batch/tasks/2/worker.txt').read_text() == 'in progress'
    assert not list((reusable / 'batch/tasks').glob('.seed-*'))


@pytest.mark.parametrize('change', ['missing-binding', 'wrong-hash', 'changed-assets', 'changed-decision'])
def test_reuse_does_not_claim_an_approval_for_different_assets(reusable, change):
    review = reusable / 'batch/tasks/1/attempts/01/review'
    contract = reusable / 'approved/securevibebench-1/tests/contract'
    if change == 'missing-binding':
        (review / 'contract-sha256.json').unlink()
    elif change == 'wrong-hash':
        write(review / 'contract-sha256.json', {'sha256': '0' * 64})
    elif change == 'changed-assets':
        (contract / 'check.c').write_text('int main(void) { return 1; }\n')
    else:
        write(review / 'result.json', {'approved': False, 'test_level': 'behavior'})
    assert reuse.seed(reusable, '2', '1') is False
    assert not (reusable / 'batch/tasks/2').exists()


def test_reuse_checks_the_copied_bytes_if_source_changes_during_copy(reusable, monkeypatch):
    original = reusable / 'approved/securevibebench-1/tests/contract'
    copytree = reuse.shutil.copytree
    def changed_copy(source, destination, *args, **kwargs):
        result = copytree(source, destination, *args, **kwargs)
        if Path(source) == original:
            (Path(destination) / 'check.c').write_text('changed while copying\n')
        return result
    monkeypatch.setattr(reuse.shutil, 'copytree', changed_copy)
    assert reuse.seed(reusable, '2', '1') is False
    assert not (reusable / 'batch/tasks/2').exists()
    assert not list((reusable / 'batch/tasks').glob('.seed-*'))
