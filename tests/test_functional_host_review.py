"""Do not expose unresolved authoring measurements as a scorable task."""
import json
from pathlib import Path
import shutil

import pytest

from securevibebench_evaluation import functional
from securevibebench_evaluation.harbor_assets import differential as policy


def test_host_preflight_rejects_stable_fail_to_fail_draft(tmp_path, qualified_task):
    task = tmp_path / 'securevibebench-992'
    shutil.copytree(Path(__file__).parents[1] / 'example' / task.name, task)
    spec = qualified_task(task)
    spec['cases'].append({'id': 'unresolved', 'command': ['/tmp/test']})
    for key in ['base_runs', 'reference_runs']:
        for run in spec['qualification'][key]:
            run['cases']['unresolved'] = 'FAIL'
    spec['qualification']['suite_sha256'] = policy.suite_hash(spec)
    (task / 'tests/functional.json').write_text(json.dumps(spec))
    # The low-level draft remains useful evidence; the host must not score it.
    policy.validate_spec(spec, task / 'tests', framework=functional.ASSETS)
    with pytest.raises(ValueError, match='unresolved functional cases'):
        functional.require_contract(task)
    with pytest.raises(ValueError, match='unresolved functional cases'):
        functional.preflight([task])
    status = functional.scoring_status(task)
    assert status['scoring_status'] == 'needs-tests'
    assert 'unresolved functional cases' in status['scoring_reason']
