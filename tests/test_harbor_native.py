import json
from pathlib import Path
from types import SimpleNamespace
import shutil
import tomllib

import pytest

from securevibebench_evaluation.harbor_native import write_config
from securevibebench_evaluation.images import acquire, read_task, stage_task
from securevibebench_evaluation.submissions import stage_submissions, submission_tasks


def prepared(tmp_path):
    task = tmp_path / 'tasks/securevibebench-992'
    shutil.copytree(Path(__file__).parents[1] / 'example' / task.name, task)
    return task


def submission(tmp_path):
    run = tmp_path / 'submission'
    folder = run / 'securevibebench-992'
    folder.mkdir(parents=True)
    (folder / 'submission.patch').write_text('')
    return run


@pytest.fixture(autouse=True)
def no_docker_or_dns(monkeypatch):
    from securevibebench_evaluation import images, generation, submissions
    def dns(environment, count=2):
        environment.mkdir(parents=True, exist_ok=True)
        return [0]
    monkeypatch.setattr(images, 'configure_dns', dns)
    monkeypatch.setattr(generation, 'acquire', lambda *args, **kwargs: None)
    monkeypatch.setattr(submissions, 'acquire', lambda *args, **kwargs: None)


def test_submission_staging_is_offline_and_does_not_modify_task(tmp_path):
    task = prepared(tmp_path)
    original = (task / 'task.toml').read_bytes()
    target = tmp_path / 'score/tasks'
    records = stage_submissions(submission(tmp_path), task.parent, target)
    config = tomllib.loads((target / task.name / 'task.toml').read_text())
    assert config['environment']['docker_image'] == read_task(task)['metadata']['image']['id']
    assert config['agent']['network_mode'] == 'no-network'
    assert config['environment']['network_mode'] == 'no-network'
    assert config['verifier']['environment']['network_mode'] == 'no-network'
    assert (task / 'task.toml').read_bytes() == original
    assert records[0]['prepared_image'] == config['environment']['docker_image']


@pytest.mark.parametrize('field', ['tag', 'image_id', 'setup_network', 'verifier_network', 'recipe'])
def test_invalid_image_contract_rejected_before_trial(tmp_path, field):
    task = prepared(tmp_path)
    config = read_task(task)
    if field == 'tag': config['environment']['docker_image'] = 'ghcr.io/test:latest'
    elif field == 'image_id': config['metadata']['image']['id'] = 'bad'
    elif field == 'setup_network': config['environment']['network_mode'] = 'public'
    elif field == 'verifier_network': config['verifier']['environment']['network_mode'] = 'public'
    else:
        (task / 'environment').mkdir()
        (task / 'environment/Dockerfile').write_text('FROM base')
    write_config(task / 'task.toml', config)
    with pytest.raises(ValueError): read_task(task)


@pytest.mark.parametrize('local_only', [False, True])
def test_missing_image_never_triggers_build(tmp_path, monkeypatch, local_only):
    from securevibebench_evaluation import images
    task = prepared(tmp_path)
    record = read_task(task)['metadata']['image']
    pulled = []
    monkeypatch.setattr(images, 'inspect_image', lambda reference: {'Id': record['id'], 'Os':'linux','Architecture':'amd64'} if pulled else None)
    monkeypatch.setattr(images, 'ensure_framework', lambda logs, **kwargs: {})
    def run(command, **kwargs):
        assert command[:2] == ['docker','pull']
        assert command[-1] == record['reference']
        pulled.append(command)
    monkeypatch.setattr(images.subprocess, 'run', run)
    if local_only:
        with pytest.raises(ValueError, match='Missing local image'):
            acquire([task],tmp_path/'logs',local_only=True)
        assert not pulled
        assert json.loads((tmp_path/'logs/images.json').read_text())['state']=='failed'
    else:
        acquire([task],tmp_path/'logs')
        assert len(pulled)==1


def test_wrong_local_image_is_rejected(tmp_path,monkeypatch):
    from securevibebench_evaluation import images
    task=prepared(tmp_path)
    monkeypatch.setattr(images,'inspect_image',lambda reference:{'Id':'sha256:'+'0'*64,'Os':'linux','Architecture':'amd64'})
    with pytest.raises(ValueError,match='identity'):
        acquire([task],tmp_path/'logs')


def test_unsupported_agent_fails_before_docker(tmp_path):
    with pytest.raises(ValueError,match='does not declare offline setup'):
        acquire([prepared(tmp_path)],tmp_path/'logs',agent='codex')
    assert not (tmp_path/'logs').exists()


def test_native_network_plan_allows_only_agent_api(tmp_path):
    from harbor.models.task.config import TaskConfig, VerifierEnvironmentMode
    from harbor.models.trial.config import AgentConfig, EnvironmentConfig, VerifierConfig
    from harbor.trial.network_policy import resolve_trial_network_plan
    task=prepared(tmp_path)
    config=TaskConfig.model_validate(stage_task(task,tmp_path/'staged',allow_hosts=['openrouter.ai']))
    plan=resolve_trial_network_plan(config,AgentConfig(),EnvironmentConfig(),VerifierConfig(),None,verifier_mode=VerifierEnvironmentMode.SEPARATE)
    assert plan.agent_env_baseline.network_mode=='no-network'
    assert plan.agent_phase.network_mode=='allowlist'
    assert 'openrouter.ai' in plan.agent_phase.allowed_hosts
    assert plan.verifier_env_baseline.network_mode=='no-network'
    assert plan.verifier_phase.network_mode=='no-network'


def test_scoring_result_must_match_submitted_task(tmp_path,monkeypatch):
    from securevibebench_evaluation import submissions
    task=prepared(tmp_path);run=submission(tmp_path);output=tmp_path/'score'
    def execute(command,**kwargs):
        result=output/'jobs/evaluation/trial';result.mkdir(parents=True)
        (result/'result.json').write_text(json.dumps({'task_name':'securevibebench-999','verifier_result':{'rewards':{'functional':1,'security':1}}}))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(submissions.subprocess,'run',execute)
    assert submissions.score(run,task.parent,output)==1


def test_mini_generation_uses_native_setup_and_defaults(tmp_path,monkeypatch):
    from securevibebench_evaluation import generation
    task=prepared(tmp_path);output=tmp_path/'generated'
    def execute(command,**kwargs):
        assert command[command.index('-a')+1]=='mini-swe-agent'
        assert not any('version=' in item for item in command)
        trial=output/'jobs/generation/trial';artifacts=trial/'artifacts/logs/artifacts';artifacts.mkdir(parents=True)
        (artifacts/'agent.patch').write_text('')
        (trial/'result.json').write_text(json.dumps({'task_name':task.name,'exception_info':None}))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(generation.subprocess,'run',execute)
    assert generation.generate([task],'mini-swe-agent','openai/test',output)==0
    assert (output/'submission'/task.name/'submission.patch').is_file()


def test_missing_submission_rejected(tmp_path):
    run = submission(tmp_path)
    (run / 'securevibebench-992/submission.patch').unlink()
    with pytest.raises(ValueError, match='Missing regular'):
        submission_tasks(run)


def test_symlink_submission_rejected(tmp_path):
    run = submission(tmp_path)
    patch = run / 'securevibebench-992/submission.patch'
    patch.unlink()
    patch.symlink_to(tmp_path / 'outside')
    with pytest.raises(ValueError):
        submission_tasks(run)


def test_unknown_task_name_rejected(tmp_path):
    run = tmp_path / 'run'
    (run / 'unknown').mkdir(parents=True)
    with pytest.raises(ValueError, match='Unknown submission'):
        submission_tasks(run)


def test_no_submission_is_not_a_success(tmp_path):
    with pytest.raises(ValueError, match='No submissions'):
        submission_tasks(tmp_path)


def test_package_refuses_failed_agent_trial(tmp_path):
    from securevibebench_evaluation.submissions import package_job
    trial = tmp_path / 'job/trial'
    trial.mkdir(parents=True)
    (trial / 'result.json').write_text(json.dumps({'task_name': 'securevibebench/securevibebench-992', 'exception_info': {'exception_type': 'ApiUsageLimitError'}}))
    with pytest.raises(ValueError, match='unsuccessful'):
        package_job(trial.parent, tmp_path / 'packaged')
    assert not (tmp_path / 'packaged').exists()


def test_package_preserves_source_patch(tmp_path):
    from securevibebench_evaluation.submissions import package_job
    trial = tmp_path / 'job/trial'
    artifacts = trial / 'artifacts/logs/artifacts'
    artifacts.mkdir(parents=True)
    patch = b'diff --git a/a.c b/a.c\n'
    (artifacts / 'agent.patch').write_bytes(patch)
    (trial / 'result.json').write_text(json.dumps({'task_name': 'securevibebench/securevibebench-992', 'exception_info': None}))
    records = package_job(trial.parent, tmp_path / 'packaged')
    assert records[0]['task'] == 'securevibebench-992'
    assert (tmp_path / 'packaged/securevibebench-992/submission.patch').read_bytes() == patch


def test_tool_backend_failure_is_not_a_completed_trial(tmp_path):
    from securevibebench_evaluation.harbor_native import summarize_job
    from securevibebench_evaluation.submissions import package_job
    trial = tmp_path / 'job/trial'
    (trial / 'agent').mkdir(parents=True)
    (trial / 'agent/codex.txt').write_text('2026-11-06 ERROR codex_core::tools::router: error=failed to spawn code-mode host /missing\n')
    (trial / 'result.json').write_text(json.dumps({'task_name': 'securevibebench/securevibebench-992', 'exception_info': None}))
    assert summarize_job(trial.parent)[0]['exception_type'] == 'AgentToolBackendError'
    with pytest.raises(ValueError, match='unsuccessful'):
        package_job(trial.parent, tmp_path / 'packaged')


def test_preparation_removes_original_git_objects(tmp_path):
    import ast
    import os
    import shutil
    import subprocess
    from securevibebench_evaluation.images import HERE
    runtime = HERE / 'harbor_assets/runtime.py'
    tree = ast.parse(runtime.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'reset_repository_history')
    scope = dict(Path=Path, os=os, shutil=shutil, subprocess=subprocess, json=json)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(runtime), 'exec'), scope)
    repo = tmp_path / 'repo'
    repo.mkdir()
    logs = tmp_path / 'logs'
    logs.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-c', 'user.name=Test', '-c', 'user.email=test@localhost', '-c', 'commit.gpgsign=false', *args], cwd=repo, stderr=subprocess.DEVNULL).decode().strip()
    git('init')
    (repo / 'source.c').write_text('starting source\n')
    git('add', '.')
    git('commit', '-m', 'start')
    start = git('rev-parse', 'HEAD')
    (repo / 'source.c').write_text('hidden answer\n')
    git('commit', '-am', 'target repair')
    answer = git('rev-parse', 'HEAD')
    git('checkout', start)
    (repo / 'build.o').write_text('prepared object')
    scope['reset_repository_history'](repo, logs)
    assert git('rev-list', '--all', '--count') == '1'
    assert git('ls-files') == 'source.c'
    assert (repo / 'source.c').read_text() == 'starting source\n'
    assert (repo / 'build.o').read_text() == 'prepared object'
    for old in (start, answer):
        with pytest.raises(subprocess.CalledProcessError):
            git('cat-file', '-e', old)
    assert git('rev-parse', 'svb-start') == git('rev-parse', 'HEAD')


def test_native_agent_options_are_forwarded(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from securevibebench_evaluation import generation
    task = prepared(tmp_path)
    output = tmp_path / 'native-options'
    option = 'config={"model":{"model_class":"openrouter"}}'
    seen = []
    def run(command, **kwargs):
        seen.extend(command)
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(generation.subprocess, 'run', run)
    assert generation.generate([task], 'mini-swe-agent', 'openrouter/test', output, agent_kwargs=[option]) == 1
    assert seen[seen.index(option) - 1] == '--ak'
    parser = __import__('securevibebench_evaluation.cli', fromlist=['build_parser']).build_parser()
    args = parser.parse_args(['generate', '--model', 'openrouter/test', '--ak', option])
    assert args.agent_kwarg == [option]


def test_agent_env_uses_native_references_without_logging_secret(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from securevibebench_evaluation import generation
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-secret-value')
    task = prepared(tmp_path)
    output = tmp_path / 'environment-references'
    def run(command, **kwargs):
        assert 'OPENROUTER_API_KEY=${OPENROUTER_API_KEY}' in command
        assert not any('test-secret-value' in argument for argument in command)
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(generation.subprocess, 'run', run)
    assert generation.generate([task], 'mini-swe-agent', 'openrouter/test', output, agent_env=['OPENROUTER_API_KEY']) == 1
    assert 'test-secret-value' not in (output/'command.json').read_text()


def test_offline_scoring_does_not_require_host_dns(tmp_path, monkeypatch):
    from securevibebench_evaluation import images
    monkeypatch.setattr(images, 'configure_dns', lambda *args: (_ for _ in ()).throw(ValueError('no DNS')))
    task = prepared(tmp_path)
    stage_task(task, tmp_path / 'offline', scoring=True)
    assert not (tmp_path / 'offline/environment/resolv.conf').exists()


def test_unavailable_task_is_explicit_and_full_stays_runnable(tmp_path):
    from securevibebench_evaluation.images import select_tasks, task_statuses
    task = prepared(tmp_path)
    records = [{'task': task.name, 'localid': '992', 'status': 'supported'},
               {'task': 'securevibebench-999', 'localid': '999', 'status': 'unsupported'}]
    (task.parent / 'availability.json').write_text(json.dumps({'tasks': records}))
    rows = task_statuses(task.parent)
    unavailable = next(row for row in rows if row['status'] == 'unsupported')
    with pytest.raises(ValueError, match='temporarily unsupported'):
        select_tasks([unavailable['localid']], task.parent)
    supported = {row['task'] for row in rows if row['status'] == 'supported'}
    assert {path.name for path in select_tasks(['full'], task.parent)} == supported
