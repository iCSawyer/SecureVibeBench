"""Build mrbc for the host while retaining sanitizers on the fuzz library."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path('/opt/svb')
REPO = Path('/src/mruby')
BUILD = ROOT / 'host-tools/mruby-build'


def build():
    shutil.rmtree(BUILD, ignore_errors=True)
    BUILD.mkdir(parents=True)
    config = ROOT / 'mruby-host.rb'
    config.write_text("MRuby::Build.new('host', '/opt/svb/host-tools/mruby-build') do |conf|\n  conf.toolchain :gcc\n  conf.disable_presym\n  conf.gem :core => 'mruby-bin-mrbc'\nend\n")
    environment = {k: v for k, v in os.environ.items() if k not in {'CC', 'CXX', 'CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS', 'LD', 'MRUBY_CONFIG', 'CONFIG', 'MRUBY_BUILD_DIR'}}
    environment.update(CC='gcc', CXX='g++', LD='gcc', MRUBY_CONFIG=str(config))
    subprocess.run(['rake', '-m', '-j' + os.environ.get('CMAKE_BUILD_PARALLEL_LEVEL', '8')], cwd=REPO, env=environment, check=True)
    binary = BUILD / 'host/bin/mrbc'
    if not binary.is_file():
        raise RuntimeError('Host mrbc was not produced')
    fuzz = ROOT / 'mruby-fuzz.rb'
    fuzz.write_text("MRuby::Build.new do |conf|\n  conf.mrbcfile = '/opt/svb/host-tools/mruby-build/host/bin/mrbc'\nend\nload File.join(MRUBY_ROOT, 'build_config/default.rb')\n")
    (ROOT / 'preparation/mruby-host-tool.json').write_text(json.dumps({'binary': str(binary), 'sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'host_cc': 'gcc', 'target_cflags': os.environ.get('CFLAGS'), 'target_cxxflags': os.environ.get('CXXFLAGS')}, indent=2) + '\n')


def check():
    library = REPO / 'build/host/lib/libmruby.a'
    symbols = subprocess.check_output(['nm', '-u', str(library)], text=True)
    memory_sanitizer = 'sanitize=memory' in os.environ.get('CFLAGS', '')
    if memory_sanitizer and '__msan_' not in symbols:
        raise RuntimeError('Fuzz library lost its required MemorySanitizer instrumentation')
    (ROOT / 'preparation/mruby-target-instrumentation.json').write_text(json.dumps({'memory_sanitizer_required': memory_sanitizer, 'memory_sanitizer_symbols_present': '__msan_' in symbols, 'library': str(library)}, indent=2) + '\n')


if __name__ == '__main__':
    {'build': build, 'check': check}[sys.argv[1]]()
