"""ARVO build scripts must retain the base image's working directory."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "container_prepare",
    Path(__file__).parents[1] / "tools/arvo_images/container_prepare.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_relative_arvo_commands_keep_the_base_directory():
    source = "#!/bin/bash\ntar -xvzf libpcap-1.9.1.tar.gz\ncd json-c\nmkdir build\nmake install\n"
    expected = "#!/bin/bash\ncd /src\ntar -xvzf libpcap-1.9.1.tar.gz\ncd json-c\nmkdir -p build\nmake install\n"
    assert module.stable_arvo_build(source, "/src") == expected
    assert module.stable_arvo_build(expected, "/src") == expected


def test_project_working_directory_is_preserved_and_quoted():
    assert (
        module.stable_arvo_build("./ossfuzz.sh\n", "/src/curl_fuzzer")
        == "cd /src/curl_fuzzer\n./ossfuzz.sh\n"
    )
    assert module.stable_arvo_build("make\n", "/src/project tree").startswith(
        "cd '/src/project tree'\n"
    )
    with pytest.raises(ValueError, match="absolute"):
        module.stable_arvo_build("make\n", "relative/path")


def test_failed_online_preparation_emits_logs_and_preserves_the_error(tmp_path, capsys):
    (tmp_path / "reference.log").write_text("reference tests completed\n")
    (tmp_path / "compile.log").write_text("missing source archive\n")
    failure = RuntimeError("compile failed")

    class Runtime:
        def prepare(self):
            raise failure

    with pytest.raises(RuntimeError) as error:
        module.prepare_online(Runtime(), tmp_path)
    assert error.value is failure
    output = capsys.readouterr().out
    assert "reference tests completed" in output and "missing source archive" in output


def test_ndpi_fuzz_build_keeps_library_and_all_fuzz_targets():
    source = "cd ndpi\nsh autogen.sh\n./configure --enable-fuzztargets\nmake\nls fuzz/fuzz* | while read i; do cp $i $OUT/; done\n"
    result = module.stable_arvo_build(source, "/src", "/src/ndpi")
    assert "./configure --enable-fuzztargets" in result
    assert 'make -j"$(nproc)" -C src/lib' in result
    assert 'make -j"$(nproc)" -C fuzz' in result
    assert "if [ -f Makefile ]; then make distclean; fi" in result
    assert "ls fuzz/fuzz* | while read i; do cp $i $OUT/; done" in result
    assert module.stable_arvo_build(result, "/src", "/src/ndpi") == result
