"""Check task-script preservation and publication safety gates."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "arvo_image_prepare", Path(__file__).parents[1] / "tools/arvo_images/prepare.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_stable_script_preserves_tests():
    source = "mkdir build && cd build\nmake\nmake check\n# mkdir build\n"
    assert (
        module.stable_functional(source)
        == "mkdir -p build && cd build\nmake\nmake check\n# mkdir build\n"
    )
    assert module.stable_functional("mkdir builder\n") == "mkdir builder\n"


def test_publish_requires_verified_environment():
    builder = object.__new__(module.Builder)
    builder.state = {}
    with pytest.raises(RuntimeError, match="before offline verification"):
        builder.publish("sha256:fake")


def test_publication_uses_the_public_registry_policy(monkeypatch):
    builder = object.__new__(module.Builder)
    builder.state = {
        "verification": {"native_setup_offline": True},
        "image_audit": {"credentials_present": False},
    }
    expected = {"visibility": "public", "anonymous_pull_verified": True}
    monkeypatch.setattr(module, "publish_public", lambda target, image: expected)
    monkeypatch.setattr(builder, "save", lambda: None)
    assert builder.publish("sha256:verified") == expected
    assert builder.state["registry"] == expected


def test_oniguruma_cleans_sanitizer_objects_before_ordinary_build():
    source = "autoreconf -vfi\n./configure\nmake check\n"
    assert (
        module.stable_functional(source, "32340")
        == "if [ -f Makefile ]; then make distclean; fi\n" + source
    )
    assert module.stable_functional(source, "37334") == source


def test_harfbuzz_requires_the_backend_used_by_shape_tests():
    source = './configure LIBS="-lpthread"\nmake check\n'
    assert "--with-freetype=yes" in module.stable_functional(source, "58663")
    reference = "apt-get install -y libfreetype6-dev libtool libtool-dev\nmake check\n"
    assert (
        module.stable_reference(reference, "58663")
        == "apt-get install -y libfreetype6-dev libtool\nmake check\n"
    )
    assert module.stable_reference(reference, "10724") == reference


def test_installer_release_requires_an_audited_snapshot():
    builder = object.__new__(module.Builder)
    builder.state = {}
    with pytest.raises(RuntimeError, match="before an audited snapshot"):
        builder.release_installation("unused", {"State": {"Running": False}})


def test_installer_release_never_touches_running_or_foreign_containers():
    builder = object.__new__(module.Builder)
    builder.id = "32345"
    builder.state = {
        "frozen_image": "sha256:verified",
        "image_audit": {"credentials_present": False},
    }
    with pytest.raises(RuntimeError, match="running"):
        builder.release_installation("unused", {"State": {"Running": True}})
    with pytest.raises(RuntimeError, match="ownership"):
        builder.release_installation(
            "unused",
            {
                "State": {"Running": False},
                "Config": {"Labels": {"com.docker.compose.project": "foreign"}},
            },
        )


def test_zstd_cli_runner_preserves_full_tests_and_native_interface():
    source = 'make\nZSTD_BIN="$(pwd)/programs/zstd" \\\nDATAGEN_BIN="$(pwd)/tests/datagen" \\\n./tests/playTests.sh\nmake -C tests fullbench && ./tests/fullbench\nmake -C tests zstreamtest && ./tests/zstreamtest\n'
    result = module.stable_functional(source, "3522")
    assert "cd tests" in result
    assert 'ZSTD="$(pwd)/../programs/zstd"' in result
    assert "./playTests.sh" in result
    assert "make -C tests fullbench && ./tests/fullbench" in result
    assert "make -C tests zstreamtest && ./tests/zstreamtest" in result


def test_ndpi_ordinary_tests_prefer_system_dependencies():
    source = "./autogen.sh\nmake check\n"
    prepared = module.stable_functional(source, "48883")
    assert 'export PKG_CONFIG_LIBDIR="$PKG_CONFIG_PATH"' in prepared
    assert "/usr/lib/x86_64-linux-gnu" in prepared
    assert "make distclean" in prepared
    assert prepared.endswith(source)
    assert "make check" in module.stable_reference(source, "48883")


def test_opensc_ordinary_tests_remove_fuzzer_tool_objects():
    original = "./configure\nmake check\n"
    updated = module.stable_functional(original, "64898")
    assert "make -C src/tools clean" in updated and "make distclean" in updated
    assert updated.endswith(original)
    assert module.stable_functional(updated, "64898") == updated


def test_build_directories_and_relative_repository_entry_are_repeatable():
    source = "cd curl\nmkdir build-autotools && cd build-autotools\n../configure\nmake test\n"
    expected = "cd /src/curl\nmkdir -p build-autotools && cd build-autotools\n../configure\nmake test\n"
    assert module.stable_functional(source, "8000", "/src/curl") == expected
    assert module.stable_reference(source, "8000", "/src/curl") == expected
    assert module.stable_functional(expected, "8000", "/src/curl") == expected
    assert module.stable_functional("mkdir builder\n") == "mkdir builder\n"


def test_mruby_clean_keeps_downloaded_gems_and_rebuilds_ordinary_objects():
    source = 'cd /src/mruby\nrake -j"$(nproc)"\nrake test --verbose\n'
    result = module.stable_functional(source, "15603", "/src/mruby")
    assert "rake clean\n" in result and "deep_clean" not in result
    assert "export CC=gcc CXX=g++" in result
    assert result.endswith('rake -j"$(nproc)"\nrake test --verbose\n')
    assert module.stable_functional(result, "15603", "/src/mruby") == result


def test_miniz_invocations_keep_roundtrip_assertions_and_log_real_cases():
    source = "../bin/example4 compressed_file.zlib\ndiff my_original_file.txt another_decompressed_file.txt\n../bin/example5 c my_original_file.txt\n../bin/example5 d compressed_by_example5.zlib\ndiff my_original_file.txt decompressed_by_example5.txt\n"
    result = module.stable_functional(source, "27413", "/src/miniz")
    assert result.startswith("set -e\n")
    assert (
        "../bin/example4 compressed_file.zlib another_decompressed_file.txt" in result
    )
    assert (
        "../bin/example5 c my_original_file.txt compressed_by_example5.zlib" in result
    )
    assert (
        "../bin/example5 d compressed_by_example5.zlib decompressed_by_example5.txt"
        in result
    )
    assert (
        "diff my_original_file.txt decompressed_by_example5.txt\necho SVB_MINIZ_CASE example5-roundtrip PASS"
        in result
    )
    assert module.stable_functional(result, "27413", "/src/miniz") == result


def test_provenance_uses_the_context_hashes_after_shared_sources_change(tmp_path):
    import tomllib
    from types import SimpleNamespace

    builder = object.__new__(module.Builder)
    builder.config = tomllib.loads(
        (
            Path(__file__).parents[1] / "example/securevibebench-992/task.toml"
        ).read_text()
    )
    frozen = {
        "runtime.py": "a" * 64,
        "parse_test_report.py": "b" * 64,
        "semantics.py": "c" * 64,
    }
    builder.state = {"shared_assets_sha256": frozen}
    builder.args = SimpleNamespace(cpus=4, memory_mb=8192)
    environment = tmp_path / "environment"
    environment.mkdir()
    (environment / "Dockerfile").write_text("FROM scratch\n")
    result = builder.task_config("sha256:" + "1" * 64, tmp_path, prepared=True)
    assert result["metadata"]["preparation_shared_assets"] == frozen
