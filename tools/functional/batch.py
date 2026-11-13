"""Resume differential test authoring and offline qualification for prepared tasks."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time

from securevibebench_evaluation.harbor_assets.differential import POLICY
from .authoring import QuotaWait, run_codex, seal_inputs, verify_inputs, write_json
from .qualify import qualify


def utc():
    return datetime.now(timezone.utc).isoformat()


def checked_path(name):
    path = Path(name)
    if path.is_absolute() or '..' in path.parts or not path.parts or '.git' in path.parts:
        raise ValueError('Unsafe requested source path: ' + name)
    return path


def workspace(source, destination):
    destination.mkdir(parents=True, exist_ok=False)
    context = json.loads((source / 'context.json').read_text())
    data = json.loads((source / 'sources.json').read_text())
    shutil.copyfile(source / 'instruction.md', destination / 'instruction.md')
    write_json(destination / 'context.json', context)
    (destination / 'reference.diff').write_text(data['diff'])
    for key, value in data['files'].items():
        revision, name = key.split(':', 1)
        phase = 'reference' if revision == context['reference'] else 'base'
        target = destination / 'context' / phase / checked_path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value)
    for name, text in data.get('headers', {}).items():
        target = destination / 'context' / 'headers' / checked_path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    (destination / 'contract').mkdir()
    subprocess.run(['git', 'init', '--quiet', str(destination)], check=True, capture_output=True)
    (destination / 'AGENTS.md').write_text(
        'Write only contract/ assets. Source snapshots and task metadata are read-only inputs.\n'
        'Do not inspect credentials, .env, auth or other projects. No network, Docker, delegation,\n'
        'package installs or source-text/hash tricks. The host executes offline validation.\n')
    return context


CONTEXT_PROBE = r'''
import hashlib,json,re,subprocess,sys
from pathlib import Path
cfg=json.loads(sys.argv[1]);repo=Path(cfg['repo']).resolve();result={};total=0
limit=32*1024*1024;total_limit=64*1024*1024
suffixes={'.c','.h','.cpp','.cc','.cxx','.hh','.hpp','.hxx','.in','.inc','.def','.spec','.txt','.py','.rb','.js','.cmake','.sh','.am','.ac','.mk','.m4','.y','.l'}
names={'Makefile','configure','CMakeLists.txt','meson.build','meson_options.txt','Rakefile','Gemfile'}
prepared=cfg.get('prepared_dependency') is True
requested=cfg.get('revision')
def git(*args):
 return subprocess.run(['git','-C',str(repo),*args],capture_output=True,timeout=20,check=True).stdout
def source_path(path):
 return path.suffix.lower() in suffixes or path.name in names
def safe_path(name):
 path=Path(name)
 return not path.is_absolute() and '..' not in path.parts and not any(part.startswith('.') or part.startswith(':') for part in path.parts)
if prepared:
 try: revision=git('rev-parse','HEAD').decode().strip()
 except subprocess.SubprocessError: revision=None
else:
 if not isinstance(requested,str) or re.fullmatch('[0-9a-f]{40}',requested) is None:
  raise ValueError('Source context requires an explicit 40-character commit SHA')
 revision=git('rev-parse','--verify',requested+'^{commit}').decode().strip()
def suggestions(name):
 try:
  listed=git('ls-files','-z') if prepared else git('ls-tree','-rz','--name-only',revision)
 except (OSError,subprocess.SubprocessError):
  return []
 needle=Path(name).name.lower();matches=[]
 for item in listed.decode(errors='replace').split('\0'):
  if not item or not safe_path(item) or not source_path(Path(item)):
   continue
  if Path(item).name.lower()==needle or needle in Path(item).name.lower():
   matches.append(item)
 return sorted(matches)[:20]
for name in cfg['paths'][:20]:
 if not safe_path(name):
  result[name]={'error':'unsafe source-context path'};continue
 if not source_path(Path(name)):
  result[name]={'error':'not a source-context file'};continue
 blob=None
 if prepared:
  p=(repo/name).resolve()
  if not p.is_relative_to(repo) or not safe_path(str(p.relative_to(repo))):
   result[name]={'error':'source path escapes the permitted repository context'};continue
  if not p.is_file():
   result[name]={'error':'prepared dependency unavailable','suggestions':suggestions(name)};continue
  size=p.stat().st_size
 else:
  try:
   entries=git('ls-tree','-z',revision,'--',name).decode(errors='replace').split('\0')
   entry=next((item.split('\t',1)[0].split() for item in entries if '\t' in item and item.split('\t',1)[1]==name),None)
   if entry is None:
    result[name]={'error':'source file absent from requested reference; no worktree fallback','revision':revision,'suggestions':suggestions(name)};continue
   mode,kind,blob=entry
   if kind!='blob' or mode not in {'100644','100755'}:
    result[name]={'error':'reference path is not a regular source blob','revision':revision};continue
   size=int(git('cat-file','-s',blob))
  except subprocess.SubprocessError:
   result[name]={'error':'could not read requested reference blob','revision':revision};continue
 if size>limit or total+size>total_limit:
  result[name]={'error':'source context exceeds the 32 MiB file or 64 MiB request limit','bytes':size};continue
 data=p.read_bytes() if prepared else git('cat-file','blob',blob)
 if b'\0' in data:
  result[name]={'error':'binary file is not source context'};continue
 total+=len(data)
 result[name]={'text':data.decode(errors='replace'),'source':'prepared-dependency' if prepared else 'git-reference',
               'requested_revision':requested,'revision':revision,'git_blob':blob,'image':cfg.get('image'),'parent_image':cfg.get('parent_image'),
               'sha256':hashlib.sha256(data).hexdigest()}
print(json.dumps(result))
'''


def extra_context(context, paths, job, output, *, prepared_dependency=False):
    paths = [str(checked_path(name)) for name in paths[:20]]
    image = context['prepared_image'] if prepared_dependency else context['parent_image']
    command = ['docker', 'run', '--rm', '--pull=never', '--network', 'none', '--read-only',
               '--name', 'junkai-f2p-context-' + context['task'], '--cpus', '1', '--memory', '512m',
               '--entrypoint', '/opt/svb/python/bin/python3', image, '-I', '-c',
               CONTEXT_PROBE, json.dumps({'repo': context['repo'], 'paths': paths,
                                         'revision': context['reference'], 'image': image, 'parent_image': context['parent_image'],
                                         'prepared_dependency': prepared_dependency})]
    write_json(output / 'context-command.json', command)
    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired as error:
        subprocess.run(['docker', 'rm', '-f', 'junkai-f2p-context-' + context['task']],
                       capture_output=True, text=True, timeout=30)
        stderr = error.stderr or ''
        if isinstance(stderr, bytes): stderr = stderr.decode(errors='replace')
        (output / 'context-stderr.log').write_text(stderr)
        raise RuntimeError('Timed out fetching source context; container removed') from error
    (output / 'context-stderr.log').write_text(process.stderr)
    if process.returncode:
        raise RuntimeError('Could not fetch requested source declarations: ' + process.stderr[-1000:])
    results = json.loads(process.stdout);write_json(output / 'context-results.json', results)
    for name, result in results.items():
        if 'text' in result:
            target = job / 'context' / 'extra' / checked_path(name)
            target.parent.mkdir(parents=True, exist_ok=True);target.write_text(result['text'])
    provenance = job / 'context' / 'extra-provenance.json'
    provenance.parent.mkdir(parents=True, exist_ok=True)
    previous = json.loads(provenance.read_text()) if provenance.is_file() else {}
    previous.update({name: {key: value for key, value in result.items() if key != 'text'}
                     for name, result in results.items()})
    write_json(provenance, previous)
    return results


def contract_draft(contract, context):
    path = contract / 'spec.json'
    spec = json.loads(path.read_text())
    # The test author cannot choose the reference tree or qualification evidence.
    for field in ['qualification', 'FAIL_TO_PASS', 'PASS_TO_PASS', 'image_id', 'base_tree', 'policy']:
        spec.pop(field, None)
    spec['reference_tree'] = context['reference_tree']
    spec['granularity'] = spec.get('granularity', 'behavior')
    for file in contract.rglob('*'):
        if file.is_symlink():
            raise ValueError('Contract assets may not be symlinks')
        if file.is_file() and file.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('Contract asset exceeds 8 MiB')
        if file.is_file():
            text = file.read_bytes()
            if any(marker in text for marker in [b'/reference.patch', b'/context/', b'sources.json', b'git rev-parse']):
                raise ValueError('Contract reads source snapshots or identities instead of candidate behavior')
    write_json(path, spec)
    return spec


def feedback(directory, limit=28000):
    parts = []
    for path in sorted(directory.rglob('*')):
        if path.is_file() and path.suffix in {'.log', '.txt'}:
            text = path.read_text(errors='replace')
            if text:
                parts.append(str(path.relative_to(directory)) + '\n' + text[-7000:])
    return '\n\n'.join(parts)[-limit:]


class Batch:
    def __init__(self, args):
        self.args = args;self.root = args.output.resolve();self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock();self.path = self.root / 'progress.json'
        previous = json.loads(self.path.read_text()) if self.path.is_file() else {}
        self.tasks = previous.get('tasks', {});self.started = previous.get('started_at', utc())
        self.quota_until = max((item.get('retry_at', 0) or 0 for item in self.tasks.values()), default=0)

    def update(self, identifier, state, **data):
        with self.lock:
            self.tasks[identifier] = {**self.tasks.get(identifier, {}), **data, 'state': state, 'updated_at': utc()}
            counts = {name: sum(x['state'] == name for x in self.tasks.values()) for name in sorted({x['state'] for x in self.tasks.values()})}
            record = {'started_at': self.started, 'updated_at': utc(), 'pid': os.getpid(),
                      'policy': POLICY, 'workers': self.args.workers, 'selected': len(self.args.ids),
                      'selected_tasks': self.args.ids,
                      'complete': all(self.tasks.get(identifier, {}).get('state') == 'qualified' for identifier in self.args.ids),
                      'counts': counts, 'tasks': self.tasks}
            temporary = self.path.with_suffix('.tmp');write_json(temporary, record);temporary.replace(self.path)

    def wait_for_framework(self, identifier):
        while not self.args.framework_ready.is_file():
            self.update(identifier, 'waiting-for-framework')
            time.sleep(20)

    def wait_for_quota(self, identifier):
        while time.time() < self.quota_until:
            self.update(identifier, 'quota-wait', retry_at=self.quota_until)
            time.sleep(min(20, self.quota_until - time.time()))

    def one(self, identifier):
        from securevibebench_evaluation.functional import require_contract
        from securevibebench_evaluation.images import read_task
        previous = self.tasks.get(identifier, {})
        if previous.get('state') == 'qualified' and previous.get('task_path'):
            try:
                path = Path(previous['task_path']);require_contract(path, read_task(path))
                return
            except (OSError, ValueError):
                self.update(identifier, 'requalification-needed')
        source = self.args.sources / identifier
        while not (source / 'context.json').is_file():
            status = self.args.sources.parent / 'source-status.json'
            inventory = json.loads(status.read_text()) if status.is_file() else {}
            outcome = inventory.get('tasks', {}).get(identifier, {})
            if outcome.get('state') == 'source-error':
                self.update(identifier, 'source-unavailable', reason=outcome.get('error', 'Source preparation failed'))
                return
            self.update(identifier, 'waiting-for-source');time.sleep(20)
        task_root = self.root / 'tasks' / identifier;task_root.mkdir(parents=True, exist_ok=True)
        job = task_root / 'workspace'
        if not job.is_dir():context = workspace(source, job)
        else:context = json.loads((job / 'context.json').read_text())
        attempts = task_root / 'attempts';attempts.mkdir(exist_ok=True)
        used = 0;index = 0
        while used < self.args.attempts:
            index += 1;attempt = attempts / ('%02d' % index)
            error_path = attempt / 'error.json'
            if error_path.is_file():
                if json.loads(error_path.read_text()).get('kind') != 'quota':used += 1
                continue
            attempt.mkdir(exist_ok=True);self.wait_for_quota(identifier)
            self.update(identifier, 'authoring', attempt=index)
            try:
                author = attempt / 'author/result.json'
                if author.is_file():written = json.loads(author.read_text())
                else:
                    abandoned = attempt / 'author'
                    if abandoned.exists():abandoned.rename(attempt / ('author-interrupted-' + str(time.time_ns())))
                    seal_inputs(job, attempt / 'trusted-inputs')
                    try:
                        written = run_codex(job, attempt / 'author', timeout=self.args.author_timeout)
                    finally:
                        verify_inputs(job, attempt / 'trusted-inputs')
                if (attempt / 'trusted-inputs').is_dir():verify_inputs(job, attempt / 'trusted-inputs')
                if written['status'] == 'needs-context':
                    result = extra_context(context, written['context_paths'], job, attempt)
                    (job / 'feedback.txt').write_text('Requested declarations were fetched into context/extra.\n' + json.dumps({k: {field: value for field, value in v.items() if field != 'text'} or 'available' for k, v in result.items()}))
                    write_json(error_path, {'kind': 'context', 'reason': 'Requested source context added'})
                    used += 1;self.update(identifier, 'context-added', attempt=index)
                    continue
                if written['status'] != 'ready':
                    raise ValueError(written.get('reason', 'No behavior contract was produced'))
                contract = job / 'contract';spec = contract_draft(contract, context)
                if not (attempt / 'authored-contract').exists():shutil.copytree(contract, attempt / 'authored-contract')
                self.update(identifier, 'reviewing', attempt=index)
                review_file = attempt / 'review/result.json'
                from .authoring import contract_hash
                contract_digest = contract_hash(contract)
                binding = attempt / 'review/contract-sha256.json'
                bound = json.loads(binding.read_text()) if binding.is_file() else {}
                if review_file.is_file() and bound.get('sha256') == contract_digest:
                    review = json.loads(review_file.read_text())
                else:
                    abandoned = attempt / 'review'
                    if abandoned.exists():abandoned.rename(attempt / ('review-interrupted-' + str(time.time_ns())))
                    review = run_codex(job, attempt / 'review', review=True, timeout=600)
                    if contract_hash(contract) != contract_digest:
                        raise ValueError('Contract changed during independent review')
                    write_json(binding, {'sha256': contract_digest})
                if (attempt / 'trusted-inputs').is_dir():verify_inputs(job, attempt / 'trusted-inputs')
                if not review['approved'] or review['test_level'] not in {'behavior', 'interface'}:
                    raise ValueError('Independent test review: ' + review['reason'])
                spec['granularity'] = review['test_level'];write_json(contract / 'spec.json', spec)
                self.wait_for_framework(identifier)
                self.update(identifier, 'qualifying', attempt=index)
                target = task_root / ('qualification-%02d' % index)
                if target.exists():target.rename(task_root / ('qualification-%02d-archive-%d' % (index, time.time_ns())))
                report = qualify(self.args.tasks / ('securevibebench-' + identifier), contract,
                                 source / 'reference.patch', target, repeats=2)
                result = {**report, 'review': review, 'author_summary': written['summary']}
                write_json(task_root / 'result.json', result)
                self.update(identifier, 'qualified', qualification=str(target / 'qualification.json'),
                            task_path=report['task_path'], f2p=report['f2p'], p2p=report['p2p'])
                return
            except QuotaWait as error:
                self.quota_until = max(self.quota_until, time.time() + self.args.quota_retry)
                write_json(attempt / ('quota-' + str(time.time_ns()) + '.json'), {'kind': 'quota', 'reason': str(error)})
                self.update(identifier, 'quota-wait', reason=str(error)[-500:])
                self.wait_for_quota(identifier)
                index -= 1
            except Exception as error:
                used += 1;write_json(error_path, {'kind': type(error).__name__, 'reason': str(error)})
                target = task_root / ('qualification-%02d' % index)
                detail = feedback(target) if target.exists() else ''
                (job / 'feedback.txt').write_text('The prior attempt did not qualify. Repair the actual test/setup; do not weaken assertions to detect source identity.\n' + str(error) + '\n' + detail)
                self.update(identifier, 'repair-needed', reason=str(error)[-1000:], attempt=index)
        self.update(identifier, 'needs-attention', reason='Recorded attempt budget used; preserved author, review and measurement logs need follow-up')

    def run(self):
        lock = (self.root / '.lock').open('w')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('This qualification batch is already running')
        for identifier in self.args.ids:
            if self.tasks.get(identifier, {}).get('state') != 'qualified':
                self.update(identifier, 'queued', reason='Scheduled for this resumed qualification batch')
        with ThreadPoolExecutor(max_workers=self.args.workers) as pool:
            futures = {pool.submit(self.one, identifier): identifier for identifier in self.args.ids}
            for future in as_completed(futures):
                identifier = futures[future]
                try:future.result()
                except Exception as error:self.update(identifier, 'execution-error', reason=str(error))
                print(identifier, self.tasks[identifier]['state'], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tasks', type=Path, required=True)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--framework-ready', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--attempts', type=int, default=6)
    parser.add_argument('--author-timeout', type=int, default=1800)
    parser.add_argument('--quota-retry', type=int, default=900)
    parser.add_argument('--task', action='append', dest='ids')
    args = parser.parse_args()
    args.tasks=args.tasks.resolve();args.sources=args.sources.resolve();args.framework_ready=args.framework_ready.resolve()
    if not args.ids:
        args.ids=[p.parent.name for p in args.sources.glob('*/context.json')]
    args.ids=list(dict.fromkeys(args.ids))
    if not 1 <= args.workers <= 4:raise ValueError('Use one to four author workers')
    Batch(args).run()


if __name__ == '__main__':
    main()
