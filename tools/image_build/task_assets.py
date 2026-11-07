"""Keep shared evaluation code in the package and materialize build contexts."""
import hashlib
import json
from pathlib import Path
import shutil

from securevibebench_evaluation import harbor_native
ASSETS=Path(harbor_native.__file__).with_name('harbor_assets')
SHARED=('runtime.py','parse_test_report.py','semantics.py')


def shared_hashes():
    return {name:hashlib.sha256((ASSETS/name).read_bytes()).hexdigest() for name in SHARED}


def compact_task(task, known_hashes=None):
    """Archive original task assets intact before using package-shared copies."""
    from uuid import uuid4
    known_hashes = known_hashes or {}
    def recognized(path, canonical):
        return path.read_bytes() == canonical.read_bytes() or hashlib.sha256(path.read_bytes()).hexdigest() == known_hashes.get(str(path.relative_to(task)))
    shared=[task/'environment/svb'/name for name in SHARED]
    for path,name in zip(shared,SHARED):
        if path.exists() and not recognized(path, ASSETS/name):
            raise ValueError('Task-specific asset requires review: '+str(path))
    runtime=task/'tests/runtime.py'
    if runtime.exists() and not recognized(runtime, ASSETS/'runtime.py'):
        raise ValueError('Task-specific verifier requires review')
    archive=Path.cwd()/'.cache/securevibebench/task-asset-archive'/task.name/uuid4().hex[:10]
    archive.mkdir(parents=True)
    candidates=shared+[runtime,task/'tests/original',task/'tests/task.json',task/'environment/svb/task.json']
    records={}
    for source in candidates:
        if not source.exists():continue
        relative=source.relative_to(task)
        destination=archive/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        if source.is_file():records[str(relative)]=hashlib.sha256(source.read_bytes()).hexdigest()
        else:
            for file in source.rglob('*'):
                if file.is_file():records[str(file.relative_to(task))]=hashlib.sha256(file.read_bytes()).hexdigest()
        source.rename(destination)
    script=task/'tests/test.sh'
    shutil.copy2(script,archive/'test.sh.before')
    (archive/'manifest.json').write_text(json.dumps({'task':str(task),'files_sha256':records},indent=2)+'\n')
    (task/'.securevibebench-generated').unlink(missing_ok=True)
    script.write_text('#!/bin/bash\nset -euo pipefail\nexec /opt/svb/python/bin/python3 /opt/svb/runtime.py verify\n')


def materialize(task, context, metadata):
    shutil.copytree(task/'environment',context,ignore=shutil.ignore_patterns('toolchain','__pycache__','agent-requirements.lock'))
    assets=context/'svb';assets.mkdir(exist_ok=True)
    for name in SHARED:shutil.copy2(ASSETS/name,assets/name)
    fields=('localid','repo_cwd','base_commit','functional_script_id')
    config={key:metadata[key] for key in fields}
    (assets/'task.json').write_text(json.dumps(config,indent=2)+'\n')
    return config


def offline_functional_script(functional, reference):
    """Remove only standalone OS installs already present in online preparation."""
    import re
    lines = functional.splitlines(keepends=True)
    output, removed = [], []
    index = 0
    while index < len(lines):
        block = lines[index]
        index += 1
        if not re.match(r'^(apt-get|apt) (update|install)\b', block):
            output.append(block)
            continue
        while block.rstrip().endswith('\\') and index < len(lines):
            block += lines[index]
            index += 1
        # Permit chains of installers; keep commands that also build or test.
        flat = block.replace('\\\n', ' ')
        commands = flat.split('&&')
        safe = all(re.match(r'^\s*(apt-get|apt) (update|install)\b', command) and
                   not re.search(r'[;&|<>`]|\$\(', command) for command in commands)
        if not safe or block not in reference:
            output.append(block)
            continue
        removed.append(block)
    return ''.join(output), removed


import ast

def semantics(source):
    """Extract unchanged scoring functions without importing host Docker code."""
    names = {'CommitSafetyStatus', 'if_poc_crashes', 'compare_functional'}
    tree = ast.parse(source)
    selected = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names]
    if {node.name for node in selected} != names:
        raise ValueError('Missing original scoring functions')
    return 'import json\nfrom pathlib import Path\n\n' + '\n\n'.join(ast.get_source_segment(source, node) for node in selected) + '\n'
