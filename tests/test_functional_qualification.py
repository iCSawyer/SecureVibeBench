"""Reject unusable qualification runs before repeating expensive builds."""
import copy
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import uuid

import pytest

from securevibebench_evaluation.functional import require_contract
from tools.functional import qualify as qualification


@pytest.fixture
def trial(tmp_path, monkeypatch):
    task = tmp_path / 'input/securevibebench-992'
    shutil.copytree(Path(__file__).parents[1] / 'example' / task.name, task)
    contract = tmp_path / 'contract'
    contract.mkdir()
    spec = {'reference_tree': 'd' * 40, 'granularity': 'behavior',
            'build': ['/bin/true'], 'cases': [
                {'id': name, 'command': ['/tmp/check', name]}
                for name in ['feature', 'regression']]}
    (contract / 'spec.json').write_text(json.dumps(spec))
    patch = tmp_path / 'reference.patch'
    patch.write_text('Synthetic patch: Docker calls are mocked in this host test.\n')
    output = tmp_path / 'qualification'
    plans = {source: [dict(feature='FAIL' if source == 'base' else 'PASS', regression='PASS')
                      for _ in range(2)] for source in ['base', 'reference']}
    commands, runs = [], []
    monkeypatch.setattr(qualification, 'inspect_image',
                        lambda image: {'Id': image, 'Os': 'linux', 'Architecture': 'amd64'})
    def check_output(command, **kwargs):
        assert command[:2] == ['docker', 'run']
        return 'b' * 40 + '\n'
    def measure(command, **kwargs):
        assert command[:2] == ['docker', 'run'] and command[-1] in ['measure', '/reference.patch']
        source = 'reference' if '--reference-patch' in command else 'base'
        index = sum(row['source'] == source for row in runs)
        result = {'build_exit_code': 0, 'completed': True,
                  'source_tree': ('d' if source == 'reference' else 'b') * 40,
                  'measurement_id': uuid.uuid4().hex, 'cases': copy.deepcopy(plans[source][index])}
        volumes = [command[i + 1] for i, token in enumerate(command) if token == '-v']
        logs = next(Path(value[:-len(':/logs/verifier')]) for value in volumes
                    if value.endswith(':/logs/verifier'))
        (logs / 'measure.json').write_text(json.dumps(result))
        commands.append(command)
        runs.append({'source': source, 'index': index, 'result': result, 'directory': logs})
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(qualification.subprocess, 'check_output', check_output)
    monkeypatch.setattr(qualification.subprocess, 'run', measure)
    return SimpleNamespace(task=task, contract=contract, patch=patch, output=output,
                           plans=plans, commands=commands, runs=runs)


def perform(trial):
    return qualification.qualify(trial.task, trial.contract, trial.patch, trial.output)


def assert_unqualified(trial):
    assert not (trial.output / 'qualification.json').exists()
    spec = json.loads((trial.output / 'tasks' / trial.task.name / 'tests/functional.json').read_text())
    return spec


@pytest.mark.parametrize('status', ['ERROR', 'NOT_RUN', 'SKIP', 'XFAIL', 'XPASS'])
def test_bad_base_result_stops_after_first_measurement_without_fake_proof(trial, status):
    trial.plans['base'][0]['feature'] = {'status': status, 'exit_code': 2}
    with pytest.raises((RuntimeError, ValueError)) as error:
        perform(trial)
    assert len(trial.runs) == 1
    assert status in str(error.value)
    assert str(trial.output / 'evidence/base-0') in str(error.value)
    assert (trial.output / 'evidence/base-0/measure.json').is_file()
    assert not (trial.output / 'evidence/base-1').exists()
    assert 'qualification' not in assert_unqualified(trial)


@pytest.mark.parametrize('change', ['missing', 'unknown-status', 'extra'])
def test_missing_or_invalid_case_results_are_not_repeated(trial, change):
    cases = trial.plans['base'][0]
    if change == 'missing':
        del cases['feature']
    elif change == 'unknown-status':
        cases['feature'] = 'UNRECOGNIZED'
    else:
        cases['undeclared'] = 'PASS'
    with pytest.raises((RuntimeError, ValueError)) as error:
        perform(trial)
    assert len(trial.runs) == 1
    assert str(trial.output / 'evidence/base-0') in str(error.value)
    assert_unqualified(trial)


@pytest.mark.parametrize('status', ['FAIL', 'ERROR', 'SKIP', 'XFAIL', 'XPASS', 'NOT_RUN'])
def test_first_nonpassing_reference_result_stops_without_claiming_qualification(trial, status):
    trial.plans['reference'][0]['feature'] = {'status': status}
    with pytest.raises((RuntimeError, ValueError)) as error:
        perform(trial)
    assert [row['source'] for row in trial.runs] == ['base', 'base', 'reference']
    assert status in str(error.value)
    assert str(trial.output / 'evidence/reference-0') in str(error.value)
    assert not (trial.output / 'evidence/reference-1').exists()
    assert 'qualification' not in assert_unqualified(trial)


def test_success_still_needs_four_unique_offline_runs_and_final_host_gate(trial, monkeypatch):
    gates = []
    def gate(task, config):
        assert len(trial.runs) == 4
        assert not (trial.output / 'qualification.json').exists()
        gates.append(task)
        return require_contract(task, config)
    monkeypatch.setattr(qualification, 'require_contract', gate, raising=False)
    original = (trial.task / 'task.toml').read_bytes()
    report = perform(trial)
    assert report['state'] == 'qualified' and gates == [Path(report['task_path'])]
    assert [row['source'] for row in trial.runs] == ['base', 'base', 'reference', 'reference']
    assert len({row['result']['measurement_id'] for row in trial.runs}) == 4
    spec = require_contract(Path(report['task_path']))
    assert spec['FAIL_TO_PASS'] == ['feature']
    assert spec['PASS_TO_PASS'] == ['regression']
    for command, row in zip(trial.commands, trial.runs):
        assert command[command.index('--network') + 1] == 'none'
        assert '--pull=never' in command
        mounted = any(token.endswith(':/reference.patch:ro') for token in command)
        assert mounted == (row['source'] == 'reference')
    assert (trial.task / 'task.toml').read_bytes() == original


def test_flaky_baseline_cannot_be_signed_as_scorable_after_four_runs(trial):
    # One valid F2P feature remains, so the low-level split can retain the
    # unstable regression as draft evidence. Final host acceptance must reject it.
    trial.plans['base'][0]['regression'] = 'FAIL'
    with pytest.raises((RuntimeError, ValueError), match='unresolved functional cases'):
        perform(trial)
    assert len(trial.runs) == 4
    assert_unqualified(trial)


def test_failed_fresh_measurement_does_not_retain_supplied_historical_proof(trial):
    path = trial.contract / 'spec.json'
    draft = json.loads(path.read_text())
    draft.update(qualification={'historical': 'not a new measurement'},
                 FAIL_TO_PASS=['feature'], PASS_TO_PASS=['regression'])
    path.write_text(json.dumps(draft))
    trial.plans['base'][0]['feature'] = 'ERROR'
    with pytest.raises(RuntimeError, match='feature=ERROR'):
        perform(trial)
    assert len(trial.runs) == 1
    spec = assert_unqualified(trial)
    assert not {'qualification', 'FAIL_TO_PASS', 'PASS_TO_PASS'} & spec.keys()
