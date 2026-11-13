"""Build an auditable functional reference correction in a disposable image."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from securevibebench_evaluation.images import inspect_image, read_task, validate_image
from .authoring import write_json

PROBE = r'''
import base64, json, os, subprocess, sys, tempfile
repo, feature, correction = sys.argv[1:]
with tempfile.TemporaryDirectory(prefix='svb-reference-') as temporary:
 env = {**os.environ, 'GIT_INDEX_FILE': temporary + '/index', 'GIT_OPTIONAL_LOCKS': '0'}
 def git(*args):
  return subprocess.check_output(['git', *args], cwd=repo, env=env)
 base = git('rev-parse', 'svb-start^{tree}').decode().strip()
 git('read-tree', 'svb-start')
 for patch in [feature, correction]:
  git('apply', '--cached', '--check', patch)
  git('apply', '--cached', patch)
  if patch == feature:
   original = git('write-tree').decode().strip()
 tree = git('write-tree').decode().strip()
 patch = git('diff', '--cached', '--binary', '--full-index', 'svb-start', '--')
 paths = git('diff', '--cached', '--name-only', '--no-renames', '-z', 'svb-start').split(b'\0')
 print(json.dumps({'base_tree': base, 'original_reference_tree': original,
  'reference_tree': tree, 'patch_base64': base64.b64encode(patch).decode(),
  'paths': [p.decode() for p in paths if p]}))
'''


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(task: Path, feature: Path, correction: Path, rationale: Path, output: Path):
    """Keep the original VIC as provenance and pin the corrected source tree."""
    config = read_task(task)
    metadata = config['metadata']
    image_id = metadata['image']['id']
    info = inspect_image(image_id)
    if info is None:
        raise ValueError('The immutable task image is not present locally')
    validate_image(info, image_id)
    inputs = {}
    for name, path in [('feature.patch', feature), ('correction.patch', correction),
                       ('rationale.md', rationale)]:
        if not path.is_file():
            raise ValueError('A nonempty feature patch, correction and rationale are required')
        inputs[name] = path.read_bytes()
        if not inputs[name]:
            raise ValueError('A nonempty feature patch, correction and rationale are required')
    output.mkdir(parents=True, exist_ok=False)
    for name, content in inputs.items():
        (output / name).write_bytes(content)
    feature = output / 'feature.patch'
    correction = output / 'correction.patch'
    rationale = output / 'rationale.md'
    name = 'junkai-f2p-reference-' + task.name
    command = ['docker', 'run', '--rm', '--pull=never', '--network', 'none',
               '--name', name, '--cpus', '1', '--memory', '2048m',
               '-v', str(feature.resolve()) + ':/feature.patch:ro',
               '-v', str(correction.resolve()) + ':/correction.patch:ro',
               '--entrypoint', '/opt/svb/python/bin/python3', image_id,
               '-I', '-c', PROBE, metadata['repo_cwd'], '/feature.patch', '/correction.patch']
    write_json(output / 'command.json', command)
    try:
        result = subprocess.run(command, capture_output=True, timeout=300)
    except subprocess.TimeoutExpired as error:
        cleanup = subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=30)
        (output / 'cleanup.log').write_bytes(cleanup.stdout + cleanup.stderr)
        (output / 'stdout.log').write_bytes(error.stdout or b'')
        (output / 'stderr.log').write_bytes(error.stderr or b'')
        (output / 'exit.txt').write_text('124\n')
        raise RuntimeError('Reference preparation timed out; see ' + str(output)) from error
    (output / 'stdout.log').write_bytes(result.stdout)
    (output / 'stderr.log').write_bytes(result.stderr)
    (output / 'exit.txt').write_text(str(result.returncode) + '\n')
    if result.returncode:
        raise RuntimeError('Reference patches did not apply; see ' + str(output))
    trees = json.loads(result.stdout)
    patch = base64.b64decode(trees.pop('patch_base64'), validate=True)
    if trees['reference_tree'] == trees['original_reference_tree']:
        raise ValueError('The correction does not change the reference tree')
    (output / 'reference.patch').write_bytes(patch)
    provenance = {'schema_version': 1, 'task': task.name, 'image_id': image_id,
                  'origin_reference_commit': metadata['vic'], **trees,
                  'feature_patch_sha256': checksum(feature),
                  'correction_patch_sha256': checksum(correction),
                  'reference_patch_sha256': checksum(output / 'reference.patch'),
                  'rationale_sha256': checksum(rationale),
                  'created_at': datetime.now(timezone.utc).isoformat()}
    write_json(output / 'provenance.json', provenance)
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['task', 'feature-patch', 'correction', 'rationale', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.task, args.feature_patch, args.correction, args.rationale, args.output), indent=2))


if __name__ == '__main__':
    main()
