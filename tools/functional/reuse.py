"""Reuse an approved contract only for identical requirements and source revisions."""
from __future__ import annotations

import argparse
import hashlib
import errno
import json
from pathlib import Path
import shutil
import tempfile
import time

from .authoring import contract_hash, seal_inputs, write_json
from .batch import contract_draft, workspace


def key(source):
    context = json.loads((source / 'context.json').read_text())
    code = json.loads((source / 'sources.json').read_text())
    return (hashlib.sha256((source / 'instruction.md').read_bytes()).hexdigest(),
            code['base'], code['reference'], context['repo'])


def reviewed_contract(root, identifier, contract, review):
    """Find the approval whose asset binding matches this exact test suite."""
    digest = contract_hash(contract)
    attempts = root / 'batch/tasks' / identifier / 'attempts'
    for result in sorted(attempts.glob('*/review/result.json'), reverse=True):
        binding = result.with_name('contract-sha256.json')
        try:
            bound = json.loads(binding.read_text())
            approved = json.loads(result.read_text())
        except (OSError, ValueError):
            continue
        if bound.get('sha256') == digest and approved == review:
            return digest, result
    return None


def seed(root, identifier, original):
    task = root / 'batch/tasks' / identifier
    if task.exists():return False
    sources = root / 'batch-sources'
    origin_context = sources / original
    target_context = sources / identifier
    if not (target_context / 'context.json').is_file() or key(origin_context) != key(target_context):
        return False
    result = json.loads((root / 'batch/tasks' / original / 'result.json').read_text())
    review = result['review']
    if not review.get('approved') or review.get('test_level') not in {'behavior', 'interface'}:
        return False
    original_contract = Path(result['task_path']) / 'tests/contract'
    approval = reviewed_contract(root, original, original_contract, review)
    if approval is None:
        return False
    reviewed_digest, approval_path = approval
    parent = task.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.seed-' + identifier + '-', dir=parent))
    context = workspace(target_context, temporary / 'workspace')
    contract = temporary / 'workspace/contract'
    contract.rmdir();shutil.copytree(original_contract, contract)
    if contract_hash(contract) != reviewed_digest:
        shutil.rmtree(temporary)
        return False
    contract_draft(contract, context)
    attempt = temporary / 'attempts/01'
    (attempt / 'author').mkdir(parents=True);(attempt / 'review').mkdir()
    write_json(attempt / 'author/result.json', {'status': 'ready', 'summary': 'Reuse the reviewed identical-requirement/source contract from task ' + original,
                                            'reason': 'Fresh image-specific qualification is still required', 'context_paths': []})
    write_json(attempt / 'review/result.json', review)
    write_json(attempt / 'review/contract-sha256.json', {'sha256': contract_hash(contract)})
    shutil.copytree(contract, attempt / 'authored-contract')
    seal_inputs(temporary / 'workspace', attempt / 'trusted-inputs')
    write_json(temporary / 'reuse-provenance.json', {'source_task': original, 'requirement_source_key': key(target_context),
               'original_contract_sha256': reviewed_digest, 'reused_contract_sha256': contract_hash(contract),
               'original_review': str(approval_path), 'reviewed_contract_sha256': reviewed_digest,
               'qualification_reused': False, 'review': 'Original independent review retained; no new review or model call is claimed'})
    try:temporary.rename(task)
    except OSError as error:
        if error.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
            raise
        # A worker claimed this task while the seed was prepared. Keep its work.
        shutil.rmtree(temporary);return False
    return True


def scan(root):
    batch = root / 'batch'
    progress = json.loads((batch / 'progress.json').read_text())
    qualified = [i for i,v in progress['tasks'].items() if v['state'] == 'qualified' and (batch / 'tasks' / i / 'result.json').is_file()]
    pending = [i for i,v in progress['tasks'].items() if v['state'] == 'queued']
    by_key = {key(root / 'batch-sources' / i): i for i in qualified}
    reused = []
    for identifier in pending:
        source = root / 'batch-sources' / identifier
        if not (source / 'context.json').is_file():continue
        original = by_key.get(key(source))
        if original and seed(root, identifier, original):reused.append({'task': identifier, 'from_task': original})
    return reused


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--watch',action='store_true')
    args=parser.parse_args();journal=args.root/'contract-reuse.jsonl'
    while True:
        for record in scan(args.root):
            with journal.open('a') as stream:stream.write(json.dumps(record)+'\n')
            print(json.dumps(record),flush=True)
        if not args.watch:break
        time.sleep(30)


if __name__ == '__main__':main()
