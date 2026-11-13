"""Report resumed work independently from task history."""
import json
from pathlib import Path
from types import SimpleNamespace

from tools.functional.batch import Batch


def test_resumed_failed_job_is_queued_and_subset_can_finish(tmp_path):
    old = {'tasks': {'1': {'state': 'needs-attention', 'attempt': 6},
                     '2': {'state': 'needs-attention', 'attempt': 6}}}
    (tmp_path / 'progress.json').write_text(json.dumps(old))
    batch = Batch(SimpleNamespace(output=tmp_path, workers=1, ids=['1']))
    observed = []
    def work(identifier):
        observed.append(json.loads(batch.path.read_text()))
        batch.update(identifier, 'qualified')
    batch.one = work
    batch.run()
    assert observed[0]['tasks']['1']['state'] == 'queued'
    assert observed[0]['tasks']['1']['attempt'] == 6
    assert observed[0]['tasks']['2']['state'] == 'needs-attention'
    result = json.loads(batch.path.read_text())
    assert result['complete'] is True
    assert result['selected_tasks'] == ['1']
    assert result['selected'] == 1
    assert result['tasks']['2']['state'] == 'needs-attention'
