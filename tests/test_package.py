"""Public CLI delegates generation to Harbor and supports generation and independent scoring."""
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from securevibebench_evaluation import cli, images, submissions


def test_help_outside_repository_does_not_download(tmp_path):
    env={**os.environ,'XDG_CACHE_HOME':str(tmp_path/'cache')}
    result=subprocess.run([sys.executable,'-m','securevibebench_evaluation','--help'],cwd=tmp_path,env=env,capture_output=True,text=True,check=True)
    assert 'eval' in result.stdout and 'generate' in result.stdout
    assert '{list,pull,generate,eval,package}' in result.stdout
    assert not (tmp_path/'cache').exists()


@pytest.mark.parametrize('arguments',[[],['my-submission']])
def test_eval_accepts_default_or_explicit_input(tmp_path,monkeypatch,arguments):
    seen={}
    def fake(source,tasks,output,jobs,**kwargs):seen.update(source=source,output=output);return 0
    monkeypatch.setattr(submissions,'score',fake);monkeypatch.chdir(tmp_path)
    assert cli.main(['eval',*arguments])==0
    assert seen['source']==(tmp_path/'my-submission' if arguments else tmp_path/'submissions')
    assert seen['output'].name.startswith('eval-')


def test_generate_defaults_to_mini_and_eval_is_optional():
    args = cli.build_parser().parse_args(['generate', '--model', 'openai/test'])
    assert args.agent == 'mini-swe-agent'
    assert args.eval is False


@pytest.mark.parametrize('with_eval,generation_code,score_code', [
    (False, 0, 0), (True, 0, 0), (True, 0, 2), (True, 1, 0),
])
def test_generate_evaluates_only_this_successful_run(tmp_path, monkeypatch, with_eval, generation_code, score_code):
    from securevibebench_evaluation import generation
    task = tmp_path / 'tasks/securevibebench-992'
    task.mkdir(parents=True)
    (task / 'task.toml').write_text('')
    output = tmp_path / 'current-run'
    calls = []
    def generate(*args, **kwargs):
        output.mkdir()
        (output / 'summary.json').write_text(json.dumps({'generation_exit_code': generation_code}))
        return generation_code
    def score(source, tasks, destination, jobs, **kwargs):
        assert source == output / 'submission'
        assert destination == output / 'evaluation'
        assert tasks.resolve() == task.parent
        assert jobs == 2
        calls.append(source)
        return score_code
    monkeypatch.setattr(generation, 'generate', generate)
    monkeypatch.setattr(submissions, 'score', score)
    monkeypatch.setattr(cli, 'select_tasks', lambda *args: [task])
    arguments = ['generate', '--model', 'openai/test', '--tasks', str(task.parent),
                 '--task', '992', '--output', str(output), '--jobs', '2']
    if with_eval:
        arguments.append('--eval')
    should_score = with_eval and generation_code == 0
    assert cli.main(arguments) == (score_code if should_score else generation_code)
    assert len(calls) == int(should_score)
    summary = json.loads((output / 'summary.json').read_text())
    if should_score:
        assert summary['evaluation_exit_code'] == score_code
        assert summary['evaluation_result'] == str(output / 'evaluation/eval.json')
    else:
        assert 'evaluation_exit_code' not in summary


def test_eval_does_not_accept_model_arguments():
    with pytest.raises(SystemExit):cli.build_parser().parse_args(['eval','--model','openai/test'])


@pytest.mark.parametrize('selection',[['992','10172'],['992,10172'],['992','--task','10172']])
def test_generate_supports_multiple_task_forms(tmp_path,selection):
    for task in ['992','10172']:
        import shutil
        shutil.copytree(images.TASKS/'securevibebench-992',tmp_path/('securevibebench-'+task))
    args=cli.build_parser().parse_args(['generate','--model','openai/test','--task',*selection])
    assert len(images.select_tasks(args.task,tmp_path))==2
    assert len(images.select_tasks(['full'],tmp_path))==2
    with pytest.raises(ValueError):images.select_tasks(['full,992'],tmp_path)


def make_job(root,name):
    job=root/name;trial=job/'trial';trial.mkdir(parents=True)
    (job/'result.json').write_text(json.dumps({'stats':{}}))
    (trial/'result.json').write_text(json.dumps({'task_name':'securevibebench-992','exception_info':None}))
    return job


def test_native_job_and_submissions_root_are_distinguished(tmp_path):
    job=make_job(tmp_path,'first')
    assert submissions.resolve_submission(job)==(job,'harbor')
    assert submissions.resolve_submission(tmp_path)==(job,'harbor')
    make_job(tmp_path,'second')
    with pytest.raises(ValueError,match='2 candidates'):submissions.resolve_submission(tmp_path)


def test_external_patch_input_is_accepted(tmp_path):
    task=tmp_path/'securevibebench-992';task.mkdir();(task/'submission.patch').write_text('')
    assert submissions.resolve_submission(tmp_path)==(tmp_path,'patches')


def test_list_exposes_support_status_without_docker(capsys):
    assert cli.main(['list', '--json']) == 0
    records = json.loads(capsys.readouterr().out)
    assert {row['status'] for row in records} == {'supported', 'unsupported'}
