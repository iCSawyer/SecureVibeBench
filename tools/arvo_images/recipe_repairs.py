"""Adapt one-shot project recipes for repeated offline evaluation."""

import hashlib
import json
from pathlib import Path
import re
import shutil

FIXTURES = Path(__file__).with_name('fixtures')
PROJECT_FIXTURES = {
    'mupdf': ('mupdf-sample.pdf',),
    'openvswitch': ('openvswitch-json.dict',),
}


def repair_test_script(text, repo_cwd, *, online):
    if not repo_cwd:
        return text
    project = Path(repo_cwd).name
    if project in {'util-linux', 'selinux'}:
        text = re.sub(
            r'(?m)^docker run -it --rm --entrypoint /bin/bash n132/arvo:\$\{localid\}-vul[ \t]*\n',
            '', text,
        )
    if not online and project in {'unicorn', 'openvswitch'}:
        lines = []
        for line in text.splitlines(keepends=True):
            install = re.match(r'^(?:pip3|python3 -m pip) install\s', line)
            if install and not re.search(r'[;&|`]|\$\(', line):
                continue
            lines.append(line)
        text = ''.join(lines)
    if project == 'fluent-bit':
        text = text.replace('cmake -j"$(nproc)" ..', 'cmake ..')
    if project == 'miniz':
        clean = 'rm -rf build\n'
        if clean not in text:
            text = ('set -e\n' + clean + text[len('set -e\n'):]) if text.startswith('set -e\n') else clean + text
    if project == 'mupdf':
        text = re.sub(
            r'(?m)^wget https://ontheline\.trincoll\.edu/images/bookdown/sample-local-pdf\.pdf[ \t]*$',
            'cp /opt/svb/offline-assets/mupdf-sample.pdf sample-local-pdf.pdf',
            text,
        )
    if project == 'openvswitch':
        clean = 'if [ -f Makefile ]; then make distclean; fi\n'
        if clean not in text:
            text = clean + text
    return text


def install_fixed_assets(context, repo_cwd):
    """Copy the original test inputs after checking their fixed hashes."""
    selected = PROJECT_FIXTURES.get(Path(repo_cwd).name, ())
    if not selected:
        return []
    manifest = json.loads((FIXTURES / 'manifest.json').read_text())
    records = {record['filename']: record for record in manifest['assets']}
    target = context / 'svb/offline-assets'
    target.mkdir(parents=True, exist_ok=True)
    used = []
    for filename in selected:
        source = FIXTURES / filename
        record = records[filename]
        if hashlib.sha256(source.read_bytes()).hexdigest() != record['sha256']:
            raise ValueError('Offline test input checksum mismatch: ' + filename)
        shutil.copy2(source, target / filename)
        used.append(record)
    (target / 'manifest.json').write_text(json.dumps({'assets': used}, indent=2) + '\n')
    return used
