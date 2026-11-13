"""Report task qualification separately from prepared-image availability."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

from securevibebench_evaluation.functional import POLICY, require_contract, task_fingerprint
from securevibebench_evaluation.images import read_task
from .authoring import write_json


def read(path, default=None):
    try:return json.loads(path.read_text())
    except (OSError, ValueError):return default if default is not None else {}


def collect(root, inventory):
    rows = read(inventory, [])
    inventory_ids = {str(row['task']) for row in rows}
    batch = read(root / 'batch/progress.json')
    source = read(root / 'source-status.json').get('tasks', {})
    candidates = list((root / 'ready-tasks').glob('*/task.toml'))
    candidates += list(root.glob('qualified-pilots-*/*/tasks/*/task.toml'))
    candidates += list(root.glob('qualification-*/tasks/*/task.toml'))
    candidates += list((root / 'batch/tasks').glob('*/qualification-*/tasks/*/task.toml'))
    candidates += list((root / 'repairs').glob('*/qualification*/tasks/*/task.toml'))
    # Prefer the newest validated proof when a task was requalified.
    candidates.sort(key=lambda path: (path.parent / 'tests/functional.json').stat().st_mtime if (path.parent / 'tests/functional.json').is_file() else 0)
    holds = read(root / 'qualification-holds.json')
    qualified = {}
    for path in candidates:
        identifier = path.parent.name.removeprefix('securevibebench-')
        if identifier not in inventory_ids:
            continue
        hold = holds.get(identifier)
        if hold and not path.is_relative_to(root / hold['accepted_under']):
            continue
        try:
            spec = require_contract(path.parent, read_task(path.parent))
            fingerprint = task_fingerprint(path.parent)
        except (OSError, ValueError, KeyError, TypeError):continue
        if {case['id'] for case in spec['cases']} != set(spec['FAIL_TO_PASS']) | set(spec['PASS_TO_PASS']):
            continue
        qualified[path.parent.name.removeprefix('securevibebench-')] = {
            'task_path': str(path.parent.resolve()), 'f2p': len(spec['FAIL_TO_PASS']),
            'p2p': len(spec['PASS_TO_PASS']), 'granularity': spec.get('granularity', 'behavior'),
            'task_fingerprint': fingerprint}
    tasks = {}
    for row in rows:
        ident = row['task'];entry = {'task': ident, 'project': row['project'], 'image_ready': True}
        if ident in qualified:entry.update(state='qualified', **qualified[ident])
        else:
            active = batch.get('tasks', {}).get(ident, {})
            if ident in holds:
                active = {'state': 'needs-repair', 'reason': holds[ident]['reason']}
            entry.update(state=active.get('state', 'pending'), reason=active.get('reason', ''),
                         attempt=active.get('attempt'), retry_at=active.get('retry_at'))
        entry['source_ready'] = (root / 'batch-sources' / ident / 'context.json').is_file()
        if not entry['source_ready'] and source.get(ident, {}).get('state') == 'source-error':
            entry['source_error'] = source[ident].get('error')
        tasks[ident] = entry
    native = {}
    for path in root.glob('native-*/eval.json'):
        result = read(path)
        native[path.parent.name] = {'tasks': result.get('completed_records'),
                                  'rewards': {str(x.get('task')).rsplit('/', 1)[-1]: x.get('rewards') for x in result.get('results', [])}}
    publication = read(root / 'publication.json')
    current_fingerprints = {'securevibebench-' + identifier: row['task_fingerprint']
                            for identifier, row in qualified.items()}
    published_current = (publication.get('task_count') == len(rows)
                         and publication.get('scoring_policy') == POLICY
                         and publication.get('task_fingerprints') == current_fingerprints)
    counts = {state: sum(x['state'] == state for x in tasks.values())
              for state in sorted({x['state'] for x in tasks.values()})}
    return {'updated_at': datetime.now(timezone.utc).isoformat(), 'phase': 'complete' if len(qualified) == len(rows) and published_current else 'qualifying',
            'policy': 'functional-f2p-p2p-v1', 'total_tasks': len(rows), 'prepared_images': len(rows),
            'source_ready': sum(x['source_ready'] for x in tasks.values()),
            'qualified_tasks': len(qualified), 'published_f2p_tasks': publication.get('task_count', 0),
            'batch_workers': batch.get('workers'), 'batch_pid': batch.get('pid'),
            'counts': counts, 'native_controls': native, 'tasks': tasks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, default=Path('runs/evaluation-equivalence-audit-20261112/inventory.json'))
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    while True:
        result = collect(args.root, args.inventory);write_json(args.root / 'status.json', result)
        print(json.dumps({key: result[key] for key in ['updated_at','total_tasks','source_ready','qualified_tasks','counts']}), flush=True)
        if not args.watch or result['phase'] == 'complete':break
        time.sleep(30)


if __name__ == '__main__':
    main()
