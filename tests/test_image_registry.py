"""Public publication must preserve existing tags and require anonymous access."""

import hashlib
import io
import json
from types import SimpleNamespace

import pytest

from tools.image_build import registry


@pytest.mark.parametrize("package", [None, {"visibility": "private"}])
def test_publication_rejects_missing_or_private_packages(monkeypatch, package):
    monkeypatch.setattr(registry, "api", lambda endpoint: package)
    with pytest.raises(RuntimeError, match="existing Public package"):
        registry.public_package("icsawyer", "securevibebench-arvo-992")


def test_public_package_requires_the_benchmark_repository(monkeypatch):
    monkeypatch.setattr(
        registry,
        "api",
        lambda endpoint: {
            "visibility": "public",
            "repository": {"html_url": "https://github.com/other/project"},
        },
    )
    with pytest.raises(RuntimeError, match="must be linked"):
        registry.public_package("icsawyer", "securevibebench-arvo-992")


def test_existing_tag_cannot_be_reassigned(monkeypatch):
    image = "sha256:" + "a" * 64
    builder = SimpleNamespace(
        id="123",
        args=SimpleNamespace(owner="icsawyer", package="securevibebench-arvo-992"),
        state={
            "verification": {"native_setup_offline": True},
            "image_audit": {"credentials_present": False},
        },
        run=lambda *args: pytest.fail(
            "Tag conflict must be detected before Docker mutation"
        ),
    )
    monkeypatch.setattr(
        registry, "public_package", lambda *args: {"visibility": "public"}
    )
    monkeypatch.setattr(
        registry,
        "anonymous_manifest",
        lambda *args, **kwargs: {"image_id": "sha256:" + "b" * 64},
    )
    with pytest.raises(RuntimeError, match="overwrite"):
        registry.publish(builder, image)


def test_a_failed_credential_audit_cannot_be_published():
    builder = SimpleNamespace(
        state={
            "verification": {"native_setup_offline": True},
            "image_audit": {"credentials_present": True},
        }
    )
    with pytest.raises(RuntimeError, match="clean credential audit"):
        registry.publish(builder, "sha256:" + "a" * 64)


def test_anonymous_manifest_checks_the_pinned_digest(monkeypatch):
    content = json.dumps({"config": {"digest": "sha256:" + "a" * 64}}).encode()
    digest = "sha256:" + hashlib.sha256(content).hexdigest()

    class Response(io.BytesIO):
        def __init__(self, content):
            super().__init__(content)
            self.headers = {"Docker-Content-Digest": digest}

    def request(value, **kwargs):
        if isinstance(value, str):
            return io.BytesIO(b'{"token":"anonymous-token"}')
        assert value.get_header("Authorization") == "Bearer anonymous-token"
        return Response(content)

    monkeypatch.setattr(registry.urllib.request, "urlopen", request)
    assert (
        registry.anonymous_manifest("icsawyer/securevibebench-arvo-992", digest)[
            "image_id"
        ]
        == "sha256:" + "a" * 64
    )
    with pytest.raises(ValueError, match="digest mismatch"):
        registry.anonymous_manifest(
            "icsawyer/securevibebench-arvo-992", "sha256:" + "c" * 64
        )


def test_canonical_package_name_is_accepted(monkeypatch):
    expected = {
        "visibility": "public",
        "repository": {"html_url": registry.REPOSITORY_URL},
    }
    seen = []

    def api(endpoint):
        seen.append(endpoint)
        return expected

    monkeypatch.setattr(registry, "api", api)
    assert registry.public_package("icsawyer", "securevibebench") is expected
    assert seen == ["users/icsawyer/packages/container/securevibebench"]


def test_new_publications_default_to_the_canonical_package(monkeypatch):
    builder = SimpleNamespace(
        id="123",
        args=SimpleNamespace(owner="icsawyer"),
        state={
            "verification": {"native_setup_offline": True},
            "image_audit": {"credentials_present": False},
        },
    )
    seen = []

    def target(owner, name):
        seen.append(name)
        return {"visibility": "public"}

    monkeypatch.setattr(registry, "public_package", target)
    monkeypatch.setattr(
        registry,
        "anonymous_manifest",
        lambda *args, **kwargs: {"image_id": "sha256:" + "b" * 64},
    )
    with pytest.raises(RuntimeError, match="overwrite"):
        registry.publish(builder, "sha256:" + "a" * 64)
    assert seen == ["securevibebench"]
