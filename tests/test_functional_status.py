"""Publication status follows the exact accepted task bytes and inventory."""
import json
from pathlib import Path
import shutil

import pytest

from securevibebench_evaluation.functional import POLICY, task_fingerprint
from tools.functional.status import collect


@pytest.fixture
def status_root(tmp_path, qualified_task):
    root = tmp_path / 'run'
    task = root / 'ready-tasks/securevibebench-992'
    shutil.copytree(Path(__file__).parents[1] / 'example' / task.name, task)
    qualified_task(task)
    inventory = tmp_path / 'inventory.json'
    inventory.write_text(json.dumps([{'task': '992', 'project': 'miniz'}]))
    publication = {'task_count': 1, 'scoring_policy': POLICY,
                   'task_fingerprints': {task.name: task_fingerprint(task)}}
    (root / 'publication.json').write_text(json.dumps(publication))
    return root, inventory, task


def test_current_publication_is_complete(status_root):
    root, inventory, _ = status_root
    report = collect(root, inventory)
    assert report['phase'] == 'complete'
    assert report['qualified_tasks'] == report['total_tasks'] == 1


@pytest.mark.parametrize('name', ['task.toml', 'instruction.md', 'tests/functional.json'])
def test_equal_task_count_does_not_hide_changed_published_bytes(status_root, name):
    root, inventory, task = status_root
    with (task / name).open('a') as stream:
        stream.write('\n')
    report = collect(root, inventory)
    assert report['qualified_tasks'] == 1
    assert report['phase'] == 'qualifying'


def test_legacy_count_without_fingerprints_is_not_a_current_publication(status_root):
    root, inventory, _ = status_root
    (root / 'publication.json').write_text(json.dumps({'task_count': 1, 'scoring_policy': POLICY}))
    assert collect(root, inventory)['phase'] == 'qualifying'


def test_stale_candidate_outside_inventory_cannot_change_counts(status_root, qualified_task):
    root, inventory, task = status_root
    stale = root / 'ready-tasks/securevibebench-32345'
    shutil.copytree(task, stale)
    qualified_task(stale)
    report = collect(root, inventory)
    assert report['phase'] == 'complete'
    assert report['qualified_tasks'] == report['total_tasks'] == 1
    assert set(report['tasks']) == {'992'}


def test_fingerprint_does_not_follow_asset_symlinks(status_root):
    _, _, task = status_root
    original = task / 'instruction.md'
    saved = task.parent / 'saved-instruction.md'
    original.rename(saved)
    original.symlink_to(saved)
    with pytest.raises(ValueError, match='regular file'):
        task_fingerprint(task)
