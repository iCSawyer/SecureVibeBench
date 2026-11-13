"""Prepare immutable source context for differential test authors."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import tempfile
import time

PROBE = r'''
import json, subprocess, sys
from pathlib import Path
config=json.loads(sys.argv[1]);repo=Path(config['repo']);base=config['base'];reference=config['reference']
def git(*args):return subprocess.check_output(['git',*args],cwd=repo,text=True,errors='replace')
changes=git('diff','--name-only',base,reference).splitlines();files={};headers={}
for name in changes:
 for revision in [base,reference]:
  p=subprocess.run(['git','show',revision+':'+name],cwd=repo,capture_output=True)
  if p.returncode==0 and len(p.stdout)<500000 and b'\0' not in p.stdout:
   files[revision+':'+name]=p.stdout.decode(errors='replace')
 # Public declarations and local compilation context, never credentials.
 parent=repo/name
 if parent.parent.is_dir():
  candidates=list(parent.parent.glob('*.h'))+list(parent.parent.glob('*.h.in'))
  for path in candidates[:100]:
   if path.is_file() and path.stat().st_size<200000:
    headers[str(path.relative_to(repo))]=path.read_text(errors='replace')
print(json.dumps({'base':git('rev-parse',base).strip(),'reference':git('rev-parse',reference).strip(),
 'base_original_tree':git('rev-parse',base+'^{tree}').strip(),
 'reference_original_tree':git('rev-parse',reference+'^{tree}').strip(),
 'diff':git('diff','--binary','--full-index',base,reference),'changed_files':changes,'files':files,'headers':headers}))
'''

TREE_PROBE = r'''
import json,subprocess,sys
from pathlib import Path
repo=Path(sys.argv[1]);patch=Path('/reference.patch')
def git(*args):return subprocess.check_output(['git',*args],cwd=repo,text=True).strip()
base=git('rev-parse','svb-start^{tree}')
subprocess.run(['git','apply','--check',str(patch)],cwd=repo,check=True)
subprocess.run(['git','apply',str(patch)],cwd=repo,check=True)
names=json.loads(sys.argv[2])
for offset in range(0,len(names),100):
 subprocess.run(['git','add','-A','-f','--',*names[offset:offset+100]],cwd=repo,check=True)
print(json.dumps({'base_tree':base,'reference_tree':git('write-tree')}))
'''


def write_json(path, value):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.' + path.name, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def run(command, folder, name):
    write_json(folder / (name + '-command.json'), command)
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=180)
    except subprocess.TimeoutExpired:
        if '--name' in command:
            cleanup = subprocess.run(['docker', 'rm', '-f', command[command.index('--name') + 1]], text=True, capture_output=True, timeout=30)
            (folder / (name + '-timeout-cleanup.log')).write_text(cleanup.stdout + cleanup.stderr)
        (folder / (name + '-exit.txt')).write_text('124\n')
        raise
    (folder / (name + '-stderr.log')).write_text(result.stderr)
    (folder / (name + '-stdout.log')).write_text(result.stdout)
    (folder / (name + '-exit.txt')).write_text(str(result.returncode) + '\n')
    if result.returncode:
        raise RuntimeError(name + ': ' + result.stderr[-1200:])
    return json.loads(result.stdout)


def prepare(row, parent, task, root):
    identifier = row['task'];folder = root / identifier
    folder.mkdir(parents=True, exist_ok=True)
    from securevibebench_evaluation.images import read_task
    metadata = read_task(task)['metadata']
    context_file = folder / 'context.json'
    if context_file.is_file():
        context = json.loads(context_file.read_text())
        complete = all((folder / name).is_file() for name in ('sources.json', 'reference.patch', 'instruction.md'))
        identity = context.get('prepared_image') == row['image']['id'] and context.get('reference') == row['reference_commit']
        if complete and identity:
            source = json.loads((folder / 'sources.json').read_text())
            if (folder / 'reference.patch').read_text() == source.get('diff') and (folder / 'instruction.md').read_text() == (task / 'instruction.md').read_text():
                return context
        archive = folder / ('invalid-cache-' + str(time.time_ns()))
        archive.mkdir()
        for name in ('context.json', 'sources.json', 'reference.patch', 'instruction.md'):
            previous = folder / name
            if previous.exists():previous.rename(archive / name)
    args = {'repo': metadata['repo_cwd'], 'base': row['original_base_commit'], 'reference': row['reference_commit']}
    prefix = ['docker', 'run', '--rm', '--pull=never', '--network', 'none', '--cpus', '1', '--memory', '2048m']
    command = prefix + ['--name', 'junkai-f2p-source-' + identifier, '--read-only', '--entrypoint', '/opt/svb/python/bin/python3', parent, '-I', '-c', PROBE, json.dumps(args)]
    source = run(command, folder, 'source')
    write_json(folder / 'sources.json', source)
    (folder / 'reference.patch').write_text(source['diff'])
    command = prefix + ['--name', 'junkai-f2p-tree-' + identifier, '-v', str((folder / 'reference.patch').resolve()) + ':/reference.patch:ro', '--entrypoint', '/opt/svb/python/bin/python3', row['image']['id'], '-I', '-c', TREE_PROBE, metadata['repo_cwd'], json.dumps(source['changed_files'])]
    trees = run(command, folder, 'prepared-trees')
    context = {**args, **trees, 'task': identifier, 'project': row['project'], 'prepared_image': row['image']['id'], 'parent_image': parent, 'source_task': str(task.resolve()), 'original_reference_tree': source['reference_original_tree'], 'files': source['changed_files']}
    (folder / 'instruction.md').write_text((task / 'instruction.md').read_text())
    write_json(folder / 'context.json', context)
    return context


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, default=Path('runs/evaluation-equivalence-audit-20261112'))
    parser.add_argument('--tasks', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--task', action='append')
    args = parser.parse_args();args.output.mkdir(parents=True, exist_ok=True)
    rows = json.loads((args.audit / 'inventory.json').read_text())
    parents = json.loads((args.audit / 'source-comparison.json').read_text())
    if args.task: rows = [row for row in rows if row['task'] in args.task]
    path = args.output.parent / 'source-status.json'
    state = json.loads(path.read_text()).get('tasks', {}) if path.is_file() else {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(prepare, row, parents[row['task']]['parent_image'], args.tasks / ('securevibebench-' + row['task']), args.output): row['task'] for row in rows}
        for future in as_completed(futures):
            identifier = futures[future]
            try:
                context = future.result();state[identifier] = {'state': 'ready', 'context': str(args.output / identifier / 'context.json')}
            except Exception as error:
                state[identifier] = {'state': 'source-error', 'error': str(error)}
            write_json(path, {'updated_at': time.time(), 'tasks': state, 'counts': {key: sum(item['state'] == key for item in state.values()) for key in ['ready', 'source-error']}})
            print(identifier, state[identifier]['state'], flush=True)


if __name__ == '__main__':
    main()
