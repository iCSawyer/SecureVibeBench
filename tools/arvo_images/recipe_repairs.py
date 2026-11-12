"""Adapt one-shot project recipes for repeated offline evaluation."""

import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import urllib.request
from filelock import FileLock

FIXTURES = Path(__file__).with_name('fixtures')
PROJECT_FIXTURES = {
    'mupdf': ('mupdf-sample.pdf',),
    'openvswitch': ('openvswitch-json.dict',),
    'libavc': ('AvcTestRes-1.0.zip',),
    'igraph': ('libxml2-2.12.5.tar.xz',),
}


def repair_test_script(text, repo_cwd, *, online, identifier=None):
    if not repo_cwd:
        return text
    project = Path(repo_cwd).name
    if project in {'util-linux', 'selinux'}:
        text = re.sub(
            r'(?m)^docker run -it --rm --entrypoint /bin/bash n132/arvo:\$\{localid\}-vul[ \t]*\n',
            '', text,
        )
    if not online and project in {'unicorn', 'openvswitch', 'wireshark'}:
        lines = []
        for line in text.splitlines(keepends=True):
            install = re.match(r'^(?:pip3|python3 -m pip|/usr/local/bin/python3\.[0-9]+ -m pip) install\s', line)
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
    if project == 'libsrtp':
        prepare = 'if [ -f Makefile ]; then make distclean; fi\nunset CC CXX CFLAGS CXXFLAGS CPPFLAGS LDFLAGS\nexport CC=gcc CXX=g++\n'
        if prepare not in text:
            text = text.replace('./configure --enable-openssl', prepare + './configure --enable-openssl', 1)
    if project == 'harfbuzz':
        text = text.replace('git clean -fdx', 'if [ -f Makefile ]; then make distclean; fi')
    if project in {'binutils-gdb', 'igraph'}:
        prepare = 'rm -rf build\n'
        if project == 'binutils-gdb':
            prepare = 'if [ -f Makefile ]; then make -j1 distclean; fi\nif [ -f zlib/Makefile ]; then make -C zlib -j1 distclean; fi\nunset CC CXX CFLAGS CXXFLAGS CPPFLAGS LDFLAGS\nexport CC=gcc CXX=g++\n' + prepare
        if prepare not in text:
            text = text.replace('mkdir -p build', prepare + 'mkdir -p build', 1)
    if project == 'binutils-gdb':
        text = text.replace('then make distclean; fi', 'then make -j1 distclean; fi')
        if online:
            text = re.sub(r'(?m)^([ \t]*python3)[ \t]*$', r'\1 libgmp-dev libmpfr-dev', text, count=1)
    if project == 'ghostpdl':
        ordinary = 'if [ -f Makefile ]; then make -j1 distclean; fi\nunset CC CXX CFLAGS CXXFLAGS CPPFLAGS LDFLAGS\nexport CC=gcc CXX=g++\n'
        if ordinary not in text:
            text = text.replace('./autogen.sh', ordinary + './autogen.sh', 1)
        text = text.replace('&& ' + chr(92) * 2 + '\n', '\n')
        if not text.startswith('set -e\n'):
            text = 'set -e\n' + text
    if project == 'hermes':
        limit = 'export LIT_OPTS="-j${CMAKE_BUILD_PARALLEL_LEVEL:-8}"\n'
        if limit not in text:
            text = limit + text
    if project == 'zeek':
        text = text.replace('sudo make install', 'make install')
        clean = 'rm -rf build\n'
        if clean not in text:
            text = text.replace('./configure', clean + './configure', 1)
    if project == 'libavc':
        if '-DCMAKE_PROJECT_libavc_INCLUDE=' not in text:
            text = text.replace('-DENABLE_TESTS=ON', '-DENABLE_TESTS=ON ' + chr(92) + '\n  -DCMAKE_PROJECT_libavc_INCLUDE=/opt/svb/libavc_dependencies.cmake', 1)
        text = re.sub(r'(?m)^ln -sf /usr/local/lib/clang/[^\n]+libclang_rt\.fuzzer-x86_64\.a \\\n[ \t]+/usr/lib/libFuzzingEngine\.a\n', '', text)
        text = text.replace('wget https://storage.googleapis.com/android_media/external/libavc/tests/AvcTestRes-1.0.zip', 'cp /opt/svb/offline-assets/AvcTestRes-1.0.zip AvcTestRes-1.0.zip')
    if project == 'libjxl' and not online:
        text = re.sub(r'(?m)^apt-get remove -y libjpeg-dev libjpeg8-dev libjpeg-turbo8-dev \|\| true\n', '', text)
    if str(identifier) == '20702':
        text = re.sub(r'(?m)^make -j"\$\(nproc\)" check\necho \$\?[ \t]*$', '/opt/svb/python/bin/python3 /opt/svb/file_test_runner.py', text)
    return text


def cached_asset(record):
    cache = Path.cwd() / '.cache/arvo-image-assets'
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / record['filename']
    with FileLock(str(target) + '.lock'):
        if not target.exists():
            with tempfile.NamedTemporaryFile(dir=cache, delete=False) as stream:
                temporary = Path(stream.name)
            try:
                with urllib.request.urlopen(record['url'], timeout=120) as response, temporary.open('wb') as output:
                    shutil.copyfileobj(response, output)
                if hashlib.sha256(temporary.read_bytes()).hexdigest() != record['sha256']:
                    raise ValueError('Downloaded test input checksum mismatch: ' + record['filename'])
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        return target


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
        if not source.exists():
            source = cached_asset(record)
        if hashlib.sha256(source.read_bytes()).hexdigest() != record['sha256']:
            raise ValueError('Offline test input checksum mismatch: ' + filename)
        shutil.copy2(source, target / filename)
        used.append(record)
    (target / 'manifest.json').write_text(json.dumps({'assets': used}, indent=2) + '\n')
    return used
