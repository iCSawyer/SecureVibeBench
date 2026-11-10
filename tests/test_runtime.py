"""Reference test failures must retain the original pass-set semantics."""
import ast
from pathlib import Path
import shutil

import pytest


def runtime(tmp_path):
    from securevibebench_evaluation.images import HERE
    source = HERE / 'harbor_assets/runtime.py'
    tree = ast.parse(source.read_text())
    declarations = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef))]
    scope = {'ROOT': tmp_path, 'REPO': str(tmp_path), 'CONFIG': {'functional_script_id': 11359}}
    exec(compile(ast.Module(body=declarations, type_ignores=[]), str(source), 'exec'), scope)
    shutil.copyfile(source.with_name('parse_test_report.py'), tmp_path / 'parse_test_report.py')
    (tmp_path / 'logs').mkdir()
    return scope


def test_reference_nonzero_exit_keeps_actual_pass_set(tmp_path):
    scope = runtime(tmp_path)
    (tmp_path / 'reference.sh').write_text("printf '%s\\n' '===TEST===BEGIN===' '[  ] suite: passed' '[OK]' '[  ] suite: failed' '[XX]'\nexit 1\n")
    baseline = scope['reference_baseline'](tmp_path / 'logs')
    assert baseline['PassList'] == ['suite: passed']
    assert baseline['FailList'] == ['suite: failed']
    assert (tmp_path / 'logs/reference.log.exit').read_text().strip() == '1'


def test_reference_without_positive_evidence_still_fails(tmp_path):
    scope = runtime(tmp_path)
    (tmp_path / 'reference.sh').write_text("printf '%s\\n' '===TEST===BEGIN===' '[  ] suite: failed' '[XX]'\nexit 1\n")
    with pytest.raises(RuntimeError, match='no positive evidence'):
        scope['reference_baseline'](tmp_path / 'logs')
    assert (tmp_path / 'logs/reference.log.exit').read_text().strip() == '1'


@pytest.mark.parametrize('output,should_pass', [
    ("printf '%s\\n' '===TEST===BEGIN===' '[  ] suite: skipped' '[BR]'\nexit 1\n", True),
    ('exit 1\n', False),
])
def test_offline_probe_requires_parsed_results_including_known_unknowns(tmp_path, monkeypatch, output, should_pass):
    import json
    scope = runtime(tmp_path)
    scope['CONFIG']['localid'] = '11359'
    scope['network_probe'] = lambda path: path.write_text('{}')
    (tmp_path / 'preparation').mkdir()
    (tmp_path / 'functional.sh').write_text(output)
    binary = tmp_path / 'bin/arvo'
    binary.parent.mkdir()
    binary.write_text('#!/bin/sh\nexit 0\n')
    binary.chmod(0o755)
    monkeypatch.setenv('PATH', str(binary.parent) + ':' + __import__('os').environ['PATH'])
    if should_pass:
        scope['probe']()
        parsed = json.loads((tmp_path / 'preparation/offline-functional.json').read_text())
        assert parsed.get('UnknownList') == ['suite: skipped'] or (parsed['type'] == 'BoolResult' and parsed['Status'] is False)
    else:
        with pytest.raises(RuntimeError, match='no parsed test results'):
            scope['probe']()
    assert (tmp_path / 'preparation/offline-functional.log.exit').read_text().strip() == '1'


def test_history_reset_flattens_prepared_submodule_sources(tmp_path):
    import subprocess
    scope = runtime(tmp_path)
    source = tmp_path / 'dependency'
    repo = tmp_path / 'main'
    source.mkdir()
    repo.mkdir()
    def git(cwd, *args):
        return subprocess.check_output(['git', '-c', 'user.name=Test', '-c', 'user.email=test@localhost',
                                       '-c', 'commit.gpgsign=false', *args], cwd=cwd, stderr=subprocess.STDOUT)
    git(source, 'init')
    (source/'dependency.c').write_text('int dependency;\n')
    git(source, 'add', '.')
    git(source, 'commit', '-m', 'Dependency source')
    inner = tmp_path / 'inner'
    inner.mkdir()
    git(inner, 'init')
    (inner/'inner.c').write_text('int inner;\n')
    git(inner, 'add', '.')
    git(inner, 'commit', '-m', 'Nested dependency')
    git(source, '-c', 'protocol.file.allow=always', 'submodule', 'add', str(inner), 'nested')
    git(source, 'commit', '-am', 'Add nested dependency')
    git(repo, 'init')
    git(repo, '-c', 'protocol.file.allow=always', 'submodule', 'add', str(source), 'vendor/dependency')
    git(repo, 'commit', '-am', 'Original main source')
    git(repo, '-c', 'protocol.file.allow=always', 'submodule', 'update', '--init', '--recursive')
    scope['reset_repository_history'](repo, tmp_path/'logs')
    assert not (repo/'vendor/dependency/.git').exists()
    assert not (repo/'vendor/dependency/nested/.git').exists()
    assert (repo/'vendor/dependency/nested/inner.c').read_text() == 'int inner;\n'
    assert (repo/'vendor/dependency/dependency.c').read_text() == 'int dependency;\n'
    assert b'vendor/dependency/dependency.c' in git(repo, 'ls-files')
    assert b'160000 ' not in git(repo, 'ls-files', '--stage')
    assert git(repo, 'rev-list', '--all', '--count').strip() == b'1'
    assert git(repo, 'status', '--porcelain') == b''


def test_number_reference_keeps_reported_counts(tmp_path):
    scope = runtime(tmp_path)
    scope['CONFIG']['functional_script_id'] = 43587
    (tmp_path / 'reference.sh').write_text("printf '%s\\n' '652 passed, 0 failed, 0 errored, 0 skipped'\n")
    baseline = scope['reference_baseline'](tmp_path / 'logs')
    assert baseline['type'] == 'NumberResult'
    assert baseline['PassNumber'] == 652 and baseline['FailNumber'] == 0


@pytest.mark.parametrize('passed,failed,unknown,expected', [
    (10, 1, 2, 1), (11, 0, 2, 1), (12, 1, 0, 1),
    (9, 1, 2, 0), (10, 2, 2, 0), (10, 1, 3, 0), (10, 0, 2, 0),
])
def test_number_comparison_preserves_passes_and_coverage(tmp_path, passed, failed, unknown, expected):
    import importlib.util
    import json
    source = Path(__file__).parents[1] / 'evaluation/harbor_assets/semantics.py'
    spec = importlib.util.spec_from_file_location('count_semantics', source)
    semantics = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(semantics)
    baseline = tmp_path / 'baseline.json'
    candidate = tmp_path / 'candidate.json'
    baseline.write_text(json.dumps({'type':'NumberResult','PassNumber':10,'FailNumber':1,'UnknownNumber':2}))
    candidate.write_text(json.dumps({'type':'NumberResult','PassNumber':passed,'FailNumber':failed,'UnknownNumber':unknown}))
    result = semantics.compare_functional(candidate, baseline)
    assert result['functional_compare_error'] is False
    assert result['functional_pass'] == expected


def test_miniz_case_markers_produce_actual_pass_identifiers(tmp_path):
    scope = runtime(tmp_path)
    scope['CONFIG']['functional_script_id'] = 27413
    log = tmp_path / 'log.txt'
    log.write_text('Usage: example5 infile outfile\nSVB_MINIZ_CASE example1 PASS\nSVB_MINIZ_CASE example5-roundtrip FAIL\n')
    result = scope['parse'](log, tmp_path / 'result.json')
    assert result['type'] == 'ListResult'
    assert result['PassList'] == ['example1']
    assert result['FailList'] == ['example5-roundtrip']


def test_command_timeout_stops_background_compilers(tmp_path):
    import os
    import signal
    import sys
    import time

    scope = runtime(tmp_path)
    script = (
        "import subprocess,time\n"
        "from pathlib import Path\n"
        "child=subprocess.Popen(['sleep','60'])\n"
        "Path('child.pid').write_text(str(child.pid))\n"
        "print('compiler started',flush=True)\n"
        "time.sleep(60)\n"
    )
    log = tmp_path / "logs/timeout.log"
    child = None
    try:
        assert scope['command']([sys.executable, '-c', script], log, timeout=0.5, check=False) == 124
        child = int((tmp_path / "child.pid").read_text())
        for _ in range(50):
            status = Path(f'/proc/{child}/stat')
            if not status.exists() or status.read_text().split(') ', 1)[1].split()[0] == 'Z':
                break
            time.sleep(0.01)
        else:
            pytest.fail('Timed-out command left a live compiler process')
        assert log.with_suffix('.log.exit').read_text().strip() == '124'
        assert 'compiler started' in log.read_text()
    finally:
        if child is not None:
            try:
                os.kill(child, signal.SIGKILL)
            except ProcessLookupError:
                pass
