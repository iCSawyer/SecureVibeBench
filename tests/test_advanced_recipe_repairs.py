"""Check real build ordering, test reporting, and pinned offline downloads."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from tools.arvo_images import recipe_repairs
from securevibebench_evaluation.harbor_assets.parse_test_report import parse_test_output_file

spec = importlib.util.spec_from_file_location('advanced_container', Path(__file__).parents[1] / 'tools/arvo_images/container_prepare.py')
container = importlib.util.module_from_spec(spec)
spec.loader.exec_module(container)


def test_cups_build_finishes_before_install_even_with_parallel_make(tmp_path):
    directory = tmp_path / 'filter'
    directory.mkdir()
    (directory / 'Makefile').write_text('.PHONY: libs install-libs\nlibs:\n\tsleep 0.1\n\ttouch libcupsimage.so.2\ninstall-libs:\n\ttest -f libcupsimage.so.2\n')
    script = container.stable_arvo_build('make -C filter libs install-libs\n', str(tmp_path), '/src/ghostpdl')
    for _ in range(2):
        (directory / 'libcupsimage.so.2').unlink(missing_ok=True)
        subprocess.run(['bash', '-eu', '-c', script], env={**os.environ, 'MAKEFLAGS': '-j8'}, check=True, capture_output=True)


def test_ghostscript_cannot_report_success_after_a_failed_smoke_test():
    script = 'false && ' + '\\' * 2 + '\necho "All smoke tests passed"\n'
    repaired = recipe_repairs.repair_test_script(script, '/src/ghostpdl', online=False)
    result = subprocess.run(['bash', '-c', repaired], text=True, capture_output=True)
    assert result.returncode != 0
    assert 'All smoke tests passed' not in result.stdout


def test_file_runner_keeps_failures_and_runs_fixtures_after_first_failure(tmp_path):
    tests = tmp_path / 'tests'
    tests.mkdir()
    binary = tests / 'test'
    binary.write_text('#!' + sys.executable + '\nimport sys\nraise SystemExit(1 if len(sys.argv)>1 and "bad" in sys.argv[1] else 0)\n')
    binary.chmod(0o755)
    for name in ['bad', 'good']:
        (tests / (name + '.testfile')).write_text(name)
        (tests / (name + '.result')).write_text(name)
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    make = bindir / 'make'
    make.write_text('#!/bin/sh\nexit 1\n')
    make.chmod(0o755)
    helper = Path(__file__).parents[1] / 'tools/arvo_images/file_test_runner.py'
    result = subprocess.run([sys.executable, str(helper)], cwd=tmp_path, env={**os.environ, 'PATH': str(bindir) + ':' + os.environ['PATH']}, text=True, capture_output=True)
    assert result.returncode == 1
    parsed = parse_test_output_file(result.stdout)
    assert parsed.PassList == ['default-magic', 'good.testfile']
    assert parsed.FailList == ['bad.testfile', 'upstream-make-check']


def test_bare_cmake_parallel_argument_is_bounded_with_real_ninja(tmp_path):
    if not all(shutil.which(name) for name in ['cmake', 'ninja']):
        pytest.skip('CMake and Ninja are required')
    worker = tmp_path / 'work.py'
    worker.write_text("import os,time\nfd=os.open('events',os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)\nos.write(fd,b'+\\n');time.sleep(0.1);os.write(fd,b'-\\n');os.close(fd)\n")
    (tmp_path / 'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.12)\nproject(jobs NONE)\n' + '\n'.join(f'add_custom_target(j{i} ALL COMMAND "{sys.executable}" "{worker}")' for i in range(10)))
    subprocess.run(['cmake', '-S', str(tmp_path), '-B', str(tmp_path / 'build'), '-G', 'Ninja'], check=True, capture_output=True)
    script = container.stable_arvo_build('cmake --build build --parallel --target all\n', str(tmp_path), '/src/hermes')
    subprocess.run(['bash', '-eu', '-c', script], env={**os.environ, 'CMAKE_BUILD_PARALLEL_LEVEL': '2'}, check=True, capture_output=True)
    active = peak = 0
    for event in (tmp_path / 'build/events').read_text().splitlines():
        active += 1 if event == '+' else -1
        peak = max(peak, active)
    assert active == 0 and peak == 2


def test_remote_input_download_is_pinned_cached_and_rejects_corruption(tmp_path, monkeypatch):
    fixtures = tmp_path / 'fixtures'
    fixtures.mkdir()
    data = b'fixed fixture bytes'
    record = {'filename': 'test.tar.xz', 'url': 'https://example.test/input', 'sha256': hashlib.sha256(data).hexdigest()}
    (fixtures / 'manifest.json').write_text(json.dumps({'assets': [record]}))
    monkeypatch.setattr(recipe_repairs, 'FIXTURES', fixtures)
    monkeypatch.setitem(recipe_repairs.PROJECT_FIXTURES, 'test-project', ('test.tar.xz',))
    monkeypatch.chdir(tmp_path)
    calls = []
    def download(url, **kwargs):
        calls.append(url)
        return io.BytesIO(data)
    monkeypatch.setattr(recipe_repairs.urllib.request, 'urlopen', download)
    for directory in ['first', 'second']:
        recipe_repairs.install_fixed_assets(tmp_path / directory, '/src/test-project')
    assert calls == [record['url']]
    (tmp_path / '.cache/arvo-image-assets/test.tar.xz').write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='checksum mismatch'):
        recipe_repairs.install_fixed_assets(tmp_path / 'third', '/src/test-project')
