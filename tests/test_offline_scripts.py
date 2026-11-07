from tools.image_build.task_assets import offline_functional_script


def test_only_duplicate_installers_move_to_online_preparation():
    reference = 'apt-get update && apt-get install -y cmake\nmake test\n'
    result, removed = offline_functional_script(reference, reference)
    assert result == 'make test\n'
    assert removed == ['apt-get update && apt-get install -y cmake\n']
    assert offline_functional_script(result, reference) == (result, [])


def test_compound_build_commands_and_unprepared_packages_are_retained():
    script = 'apt-get install -y cmake && make test\napt-get install -y missing\n'
    reference = 'apt-get install -y cmake && make test\n'
    assert offline_functional_script(script, reference) == (script, [])


def test_continued_install_is_removed_as_one_block():
    script = 'apt-get install -y ' + '\\\n' + '  cmake ' + '\\\n' + '  ninja-build\nmake test\n'
    result, removed = offline_functional_script(script, script)
    assert result == 'make test\n'
    assert len(removed) == 1
