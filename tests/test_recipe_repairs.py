"""Exercise repeated project builds and their fixed offline inputs."""
import importlib.util
import os
from pathlib import Path
import subprocess

import pytest
from tools.arvo_images.recipe_repairs import install_fixed_assets, repair_test_script

spec = importlib.util.spec_from_file_location('repair_container', Path(__file__).parents[1] / 'tools/arvo_images/container_prepare.py')
container = importlib.util.module_from_spec(spec)
spec.loader.exec_module(container)


def run_script(text, cwd, **environment):
    return subprocess.run(['bash', '-eu', '-c', text], cwd=cwd, env={**os.environ, **environment}, capture_output=True, text=True, check=True)


def test_mruby_dependency_folder_can_be_created_twice(tmp_path):
    (tmp_path / 'LPM').mkdir()
    original = '(mkdir LPM && cd LPM && printf ready)\n'
    script = container.stable_arvo_build(original, str(tmp_path), '/src/mruby')
    assert run_script(script, tmp_path).stdout == 'ready'
    assert run_script(script, tmp_path).stdout == 'ready'


def test_miniz_replaces_an_ordinary_build_before_fuzz_configuration(tmp_path):
    build = tmp_path / 'build'
    build.mkdir()
    (build / 'ordinary-cache').write_text('ordinary compiler flags')
    source = 'mkdir build\ntest ! -f build/ordinary-cache\n'
    script = container.stable_arvo_build(source, str(tmp_path), str(tmp_path / 'miniz'))
    # Use a repository named miniz for the real path-based cleanup.
    project = tmp_path / 'miniz'
    project.mkdir()
    (project / 'build').mkdir()
    (project / 'build/ordinary-cache').write_text('ordinary flags')
    script = container.stable_arvo_build(source, str(project), str(project))
    run_script(script, project)
    run_script(script, project)


@pytest.mark.parametrize("original", [
    'mv $SRC/*.zip $SRC/*.dict $SRC/*.options $OUT\n',
    'mv $SRC/{*.zip,*.dict,*.options} $OUT\n',
])
def test_mupdf_resources_survive_two_compilations(tmp_path, original):
    source = tmp_path / 'src'
    output = tmp_path / 'out'
    source.mkdir()
    output.mkdir()
    for suffix in ('zip', 'dict', 'options'):
        (source / ('fixture.' + suffix)).write_text(suffix)
    script = container.stable_arvo_build(original, str(tmp_path), '/src/mupdf')
    for _ in range(2):
        run_script(script, tmp_path, SRC=str(source), OUT=str(output))
        assert sorted(p.name for p in source.iterdir()) == sorted(p.name for p in output.iterdir())


@pytest.mark.parametrize('project', ['util-linux', 'selinux'])
def test_host_container_launcher_is_removed_but_tests_remain(project):
    script = 'docker run -it --rm --entrypoint /bin/bash n132/arvo:${localid}-vul\nmake check\n'
    assert repair_test_script(script, '/src/' + project, online=False) == 'make check\n'


def test_python_installs_remain_online_only():
    script = 'python3 -m pip install --user --upgrade "pip<21"\npip3 install "tftpy<0.9"\nmake check\n'
    assert repair_test_script(script, '/src/openvswitch', online=True).endswith(script)
    offline = repair_test_script(script, '/src/openvswitch', online=False)
    assert 'pip install' not in offline and 'pip3 install' not in offline
    assert offline.endswith('make check\n')


def test_cached_inputs_have_fixed_hashes_and_corruption_fails(tmp_path, monkeypatch):
    from tools.arvo_images import recipe_repairs
    copied = tmp_path / 'fixtures'
    import shutil
    shutil.copytree(recipe_repairs.FIXTURES, copied)
    monkeypatch.setattr(recipe_repairs, 'FIXTURES', copied)
    records = install_fixed_assets(tmp_path / 'context', '/src/mupdf')
    assert records[0]['filename'] == 'mupdf-sample.pdf'
    assert (tmp_path / 'context/svb/offline-assets/mupdf-sample.pdf').read_bytes().startswith(b'%PDF')
    (copied / 'mupdf-sample.pdf').write_bytes(b'wrong input')
    with pytest.raises(ValueError, match='checksum mismatch'):
        install_fixed_assets(tmp_path / 'other', '/src/mupdf')


def test_openvswitch_build_uses_local_dictionary_without_network():
    source = 'wget -O $OUT/json.dict https://raw.githubusercontent.com/rc0r/afl-fuzz/master/dictionaries/json.dict\nmake oss-fuzz-targets\n'
    script = container.stable_arvo_build(source, '/src/openvswitch', '/src/openvswitch')
    assert 'wget' not in script
    assert 'cp /opt/svb/offline-assets/openvswitch-json.dict $OUT/json.dict' in script
    assert 'make oss-fuzz-targets' in script
