"""Run preparation and verification inside Harbor environments."""
import importlib.util
import json
import os
import signal
from pathlib import Path
import socket
import shutil
import ssl
import subprocess
import sys

ROOT = Path('/opt/svb')
CONFIG = json.loads((ROOT / 'task.json').read_text())
REPO = CONFIG['repo_cwd']


def command(args, log, timeout=3600, check=True):
    if list(args) == ['arvo', 'compile']:
        timeout = max(timeout, int(CONFIG.get('compile_timeout_seconds', 3600)))
    with log.open('wb') as stream:
        with subprocess.Popen(args, cwd=REPO, stdout=stream, stderr=subprocess.STDOUT,
                              start_new_session=True,
                              env={**os.environ, 'SVB_LOG_DIR': str(log.parent), 'SVB_LOG_PREFIX': log.stem}) as process:
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # A shell timeout must also stop its compiler and test children.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                code = 124
    log.with_suffix(log.suffix + '.exit').write_text(str(code) + '\n')
    if check and code:
        with log.open(errors='replace') as stream:
            shutil.copyfileobj(stream, sys.stderr)
        raise RuntimeError('Command failed (%s): %s; see %s' % (code, args, log))
    return code


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def parse(log, destination):
    parser = load('parse_test_report')
    value = parser.parse_test_output(int(CONFIG['functional_script_id']), log.read_text(errors='replace'))
    text = destination.with_suffix('.txt')
    text.write_text(str(value))
    data = parser.parse_single_file(text)
    destination.write_text(json.dumps(data, indent=2) + '\n')
    return data


def network_probe(log):
    results = {}
    for host in ['api.openai.com', 'api.anthropic.com', 'example.com']:
        try:
            with socket.create_connection((host, 443), timeout=4) as connection:
                # Harbor's transparent proxy checks SNI after accepting TCP.
                with ssl.create_default_context().wrap_socket(connection, server_hostname=host):
                    results[host] = True
        except OSError:
            results[host] = False
    log.write_text(json.dumps(results, indent=2) + '\n')
    if any(results.values()):
        raise RuntimeError('Network isolation probe failed')


def reset_repository_history(repo, logs):
    """Replace the original Git database with one commit of the starting source."""
    repo = Path(repo)
    submodules, uninitialized = [], []
    def tracked_files(directory, prefix=Path()):
        entries = subprocess.check_output(['git', 'ls-files', '--stage', '-z'], cwd=directory).decode().split('\0')
        files = []
        for entry in entries:
            if not entry:
                continue
            details, name = entry.split('\t', 1)
            mode, _, stage = details.split()
            if stage != '0':
                raise RuntimeError('Unmerged source before history removal')
            relative = prefix / name
            if mode == '160000':
                child = directory / name
                marker = child / '.git'
                if not marker.exists():
                    if child.is_dir() and any(child.iterdir()):
                        raise RuntimeError('Submodule lacks Git metadata: ' + str(relative))
                    uninitialized.append(str(relative))
                    continue
                if child.is_symlink():
                    raise RuntimeError('Unexpected submodule symlink')
                files.extend(tracked_files(child, relative))
                submodules.append(child)
            else:
                files.append(str(relative))
        return files
    tracked = tracked_files(repo)
    for child in submodules:
        marker = child / '.git'
        if marker.is_symlink() or marker.is_file():
            marker.unlink()
        else:
            shutil.rmtree(marker)
    # Old checkouts can leave submodules that are absent from the current index.
    # Remove their Git databases as well; keep downloaded source files.
    orphan_git = []
    for directory, directories, filenames in os.walk(repo, followlinks=False):
        if '.git' in directories:
            directories.remove('.git')
        if Path(directory) == repo:
            continue
        marker = Path(directory) / '.git'
        if marker.is_symlink() or marker.is_file():
            marker.unlink()
        elif marker.is_dir():
            shutil.rmtree(marker)
        else:
            continue
        orphan_git.append(str(marker.relative_to(repo)))
    original_head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    git_dir = repo / '.git'
    if not git_dir.is_dir() or git_dir.is_symlink():
        raise RuntimeError('Expected a standalone .git directory before history removal')
    shutil.rmtree(git_dir)
    with (logs / 'history-reset.log').open('wb') as log:
        def git(*args, env=None):
            return subprocess.run(['git', *args], cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        git('init')
        for offset in range(0, len(tracked), 200):
            git('add', '-f', '--', *tracked[offset:offset + 200])
        env = os.environ.copy()
        env.update(GIT_AUTHOR_DATE='2000-01-01T00:00:00Z', GIT_COMMITTER_DATE='2000-01-01T00:00:00Z')
        git('-c', 'user.name=Benchmark', '-c', 'user.email=benchmark@localhost', '-c', 'commit.gpgsign=false', 'commit', '-m', 'Initial task source', env=env)
        git('tag', 'svb-start')
    count = subprocess.check_output(['git', 'rev-list', '--all', '--count'], cwd=repo, text=True).strip()
    old = subprocess.run(['git', 'cat-file', '-e', original_head], cwd=repo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if count != '1' or old.returncode == 0:
        raise RuntimeError('Original Git history was not removed')
    (logs / 'history-reset.json').write_text(json.dumps({'original_git_deleted': True, 'commit_count': int(count), 'original_commit_available': False, 'submission_base': 'svb-start', 'flattened_submodules': [str(child.relative_to(repo)) for child in submodules], 'uninitialized_submodules': uninitialized, 'removed_orphan_git': orphan_git}, indent=2) + '\n')


def has_positive_evidence(result):
    return bool(result.get('PassList')) or result.get('Status') is True or (
        result.get('type') == 'NumberResult' and result.get('PassNumber', 0) > 0
    )


def reference_baseline(logs):
    """Keep the reference pass set even when other reference tests fail."""
    command(['bash', str(ROOT / 'reference.sh')], logs / 'reference.log', check=False)
    baseline = parse(logs / 'reference.log', ROOT / 'baseline.json')
    if not has_positive_evidence(baseline):
        with (logs / 'reference.log').open(errors='replace') as stream:
            shutil.copyfileobj(stream, sys.stderr)
        raise RuntimeError('Gold baseline has no positive evidence; do not score this task')
    return baseline


def prepare():
    logs = ROOT / 'preparation'
    logs.mkdir(exist_ok=True)
    # file/992's fuzz link omitted zlib; its functional script installs zlib headers.
    if str(CONFIG['localid']) == '992':
        build = Path('/src/build.sh')
        original = build.read_text()
        needle = '-lFuzzingEngine ./src/.libs/libmagic.a'
        if original.count(needle) != 1:
            raise RuntimeError('Unexpected file/992 build script; compatibility patch not applied')
        (logs / 'build-before.sh').write_text(original)
        build.write_text(original.replace(needle, needle + ' -lz'))
        (logs / 'build-after.sh').write_text(build.read_text())
    # Preserve the original gold-reference script, including its checkout.
    reference_baseline(logs)
    if (ROOT / 'prepare.sh').is_file():
        command(['bash', str(ROOT / 'prepare.sh')], logs / 'dependencies.log')
    command(['git', 'reset', '--hard', CONFIG['base_commit']], logs / 'checkout.log')
    entries = subprocess.check_output(['git', 'ls-files', '--stage'], cwd=REPO).splitlines()
    if any(entry.startswith(b'160000 ') for entry in entries):
        command(['git', 'submodule', 'update', '--init', '--recursive'], logs / 'submodules.log')
    # Keep downloaded build dependencies. Checkout refreshes changed tracked files.
    command(['arvo', 'compile'], logs / 'compile.log')
    command(['git', 'reset', '--hard', CONFIG['base_commit']], logs / 'reset-after-compile.log')
    command(['git', 'rev-parse', 'HEAD'], logs / 'base-head.log')
    reset_repository_history(REPO, logs)
    # Exclude only files already produced by preparation from source submissions.
    existing = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=REPO).decode().split('\0')
    with (Path(REPO) / '.git/info/exclude').open('a') as out:
        for name in existing:
            if name:
                escaped = ''.join('\\' + c if c in '*?[]!#\\ ' else c for c in name)
                out.write('/' + escaped + '\n')
    command(['dpkg-query', '-W'], logs / 'packages.log')


def functional(logs, name, check=True):
    # The security build uses MSan; do not reuse its objects in ordinary tests.
    if str(CONFIG['localid']) == '992' and (Path(REPO) / 'Makefile').exists():
        command(['make', 'distclean'], logs / (name + '-clean.log'))
    return command(['bash', '-e', str(ROOT / 'functional.sh')], logs / (name + '.log'), check=check)


def probe():
    logs = ROOT / 'preparation'
    network_probe(logs / 'offline-network.json')
    command(['arvo', 'compile'], logs / 'offline-compile.log')
    functional(logs, 'offline-functional', check=False)
    parsed = parse(logs / 'offline-functional.log', logs / 'offline-functional.json')
    if not any(parsed.get(name) for name in ('PassList', 'FailList', 'UnknownList', 'PassNumber', 'FailNumber', 'UnknownNumber')) and parsed.get('Status') not in (True, False):
        raise RuntimeError('Offline functional command produced no parsed test results')


def collect():
    logs = Path('/logs/artifacts')
    logs.mkdir(parents=True, exist_ok=True)
    # Harbor restores the setup baseline after agent.run(); collection is not
    # evidence of the network policy used during agent execution.
    # Add intent-to-add entries to include new source files, respecting .gitignore.
    command(['git', 'add', '-N', '.'], logs / 'collect-add.log')
    command(['git', 'diff', '--binary', 'svb-start', '--', '.'], logs / 'agent.patch')


def verify():
    logs = Path('/logs/verifier')
    logs.mkdir(parents=True, exist_ok=True)
    network_probe(logs / 'network.json')
    patch = Path('/logs/artifacts/agent.patch')
    if not patch.exists():
        raise RuntimeError('Missing agent patch')
    if patch.stat().st_size:
        command(['git', 'apply', '--check', str(patch)], logs / 'patch-check.log')
        command(['git', 'apply', str(patch)], logs / 'patch.log')
    command(['arvo', 'compile'], logs / 'compile.log')
    code = command(['arvo'], logs / 'poc.log', timeout=300, check=False)
    semantics = load('semantics')
    security = semantics.if_poc_crashes((logs / 'poc.log').read_text(errors='replace'), code)
    if security not in ('safe', 'vul'):
        raise RuntimeError('Original security classifier reported infrastructure error')
    functional_exit = functional(logs, 'functional', check=False)
    parse(logs / 'functional.log', logs / 'functional.json')
    comparison = semantics.compare_functional(logs / 'functional.json', ROOT / 'baseline.json')
    if comparison['functional_compare_error'] or comparison['functional_pass'] not in (0, 1):
        raise RuntimeError('Original functional comparison failed')
    (logs / 'result.json').write_text(json.dumps({'functional': comparison, 'functional_exit_code': functional_exit, 'security': security}, indent=2) + '\n')
    (logs / 'reward.json').write_text(json.dumps({'functional': comparison['functional_pass'], 'security': int(security == 'safe')}) + '\n')


if __name__ == '__main__':
    {'prepare': prepare, 'probe': probe, 'collect': collect, 'verify': verify}[sys.argv[1]]()
