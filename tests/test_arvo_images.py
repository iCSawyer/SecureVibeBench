"""Check task-script preservation and publication safety gates."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
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


def test_public_package_is_never_overwritten(monkeypatch):
    builder = object.__new__(module.Builder)
    builder.id = "992"
    builder.args = SimpleNamespace(owner="icsawyer")
    builder.state = {
        "verification": {"native_setup_offline": True},
        "image_audit": {"credentials_present": False},
    }
    monkeypatch.setattr(module, "api", lambda endpoint: {"visibility": "public"})
    monkeypatch.setattr(
        builder,
        "run",
        lambda *args, **kwargs: pytest.fail("Must not tag or push a public package"),
    )
    with pytest.raises(RuntimeError, match="non-private"):
        builder.publish("sha256:fake")


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
