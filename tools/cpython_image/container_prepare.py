"""Prepare an offline gold baseline or a clean starting-source snapshot."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, '/opt/svb')
import runtime

parser = argparse.ArgumentParser()
parser.add_argument('phase', choices=['gold', 'start'])
parser.add_argument('--commit', required=True)
args = parser.parse_args()
logs = Path('/opt/svb/preparation')
logs.mkdir(exist_ok=True)
runtime.network_probe(logs / 'network.json')
runtime.command(['git', 'reset', '--hard', args.commit], logs / 'checkout.log')
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=runtime.REPO, text=True).strip()
(logs / 'source.json').write_text(json.dumps({'phase': args.phase, 'commit': head}, indent=2) + '\n')
if args.phase == 'gold':
    code = runtime.command(['bash', '-e', '/opt/svb/functional.sh'], logs / 'functional.log', timeout=7200, check=False)
    baseline = runtime.parse(logs / 'functional.log', Path('/opt/svb/baseline.json'))
    if code or not baseline.get('PassList'):
        raise RuntimeError('Offline gold tests must finish successfully with positive evidence; exit=' + str(code))
else:
    if not Path('/opt/svb/baseline.json').is_file():
        raise RuntimeError('Missing validated offline reference baseline')
    runtime.command(['arvo', 'compile'], logs / 'compile.log', timeout=7200)
    runtime.command(['git', 'reset', '--hard', args.commit], logs / 'reset-after-compile.log')
    runtime.reset_repository_history(runtime.REPO, logs)
    untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=runtime.REPO).decode().split('\0')
    with (Path(runtime.REPO) / '.git/info/exclude').open('a') as stream:
        for name in untracked:
            if name:
                escaped = ''.join('\\' + c if c in '*?[]!#\\ ' else c for c in name)
                stream.write('/' + escaped + '\n')
    runtime.command(['dpkg-query', '-W'], logs / 'packages.log')
