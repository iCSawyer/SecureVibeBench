"""Publish verified images only to an existing public GHCR package."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values

from .metadata import REPOSITORY_URL

DEFAULT_PACKAGE = "securevibebench"

ACCEPT = "application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json"


def credential():
    token = dotenv_values(Path(__file__).resolve().parents[2] / ".env").get(
        "GITHUB_DOCKER"
    )
    if not token:
        raise ValueError("Set GITHUB_DOCKER in the project .env")
    return token


def api(endpoint):
    request = urllib.request.Request(
        "https://api.github.com/" + endpoint,
        headers={
            "Authorization": "Bearer " + credential(),
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def public_package(owner, name):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9-]*", owner):
        raise ValueError("Invalid registry owner")
    if not re.fullmatch(r"securevibebench(?:-arvo(?:-[0-9]+)?)?", name):
        raise ValueError("Use a SecureVibeBench ARVO package")
    package = api("users/" + owner + "/packages/container/" + name)
    if not package or package.get("visibility") != "public":
        raise RuntimeError(
            "Publication requires an existing Public package; no image was pushed"
        )
    repository = (package.get("repository") or {}).get("html_url", "")
    if repository.rstrip("/").lower() != REPOSITORY_URL.lower():
        raise RuntimeError("Public package must be linked to " + REPOSITORY_URL)
    return package


def anonymous_manifest(repository, reference, *, missing_ok=False):
    query = urllib.parse.urlencode(
        {"service": "ghcr.io", "scope": "repository:" + repository + ":pull"}
    )
    with urllib.request.urlopen(
        "https://ghcr.io/token?" + query, timeout=45
    ) as response:
        token = json.load(response)["token"]
    request = urllib.request.Request(
        "https://ghcr.io/v2/" + repository + "/manifests/" + reference,
        headers={"Authorization": "Bearer " + token, "Accept": ACCEPT},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            content = response.read()
            declared = response.headers.get("Docker-Content-Digest")
    except urllib.error.HTTPError as error:
        if error.code == 404 and missing_ok:
            return None
        raise
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    if (declared and declared != digest) or (
        reference.startswith("sha256:") and reference != digest
    ):
        raise ValueError("Registry manifest digest mismatch")
    image_id = json.loads(content).get("config", {}).get("digest", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("Expected a single-platform image manifest")
    return {"digest": digest, "image_id": image_id, "anonymous": True}


def publish(builder, image):
    verification = builder.state.get("verification", {})
    audit = builder.state.get("image_audit", {})
    if (
        verification.get("native_setup_offline") is not True
        or audit.get("credentials_present") is not False
    ):
        raise RuntimeError(
            "Public publication requires offline verification and a clean credential audit"
        )
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image) or not builder.id.isdigit():
        raise ValueError("Invalid image identity or task ID")
    owner = builder.args.owner.lower()
    name = getattr(builder.args, "package", None) or DEFAULT_PACKAGE
    package = public_package(owner, name)
    repository = owner + "/" + name
    label = (
        "arvo-"
        + builder.id
        + "-offline-"
        + datetime.now(UTC).strftime("%Y%m%d")
        + "-"
        + image[7:19]
    )
    tag = "ghcr.io/" + repository + ":" + label
    previous = anonymous_manifest(repository, label, missing_ok=True)
    if previous and previous["image_id"] != image:
        raise RuntimeError("Refuse to overwrite an existing image tag")
    builder.run("registry-tag", ["docker", "tag", image, tag])
    with tempfile.TemporaryDirectory(prefix="junkai-ghcr-publish-") as temporary:
        directory = Path(temporary)
        if not previous:
            authenticated = directory / "authenticated"
            authenticated.mkdir(mode=0o700)
            auth = base64.b64encode((owner + ":" + credential()).encode()).decode()
            config = authenticated / "config.json"
            config.write_text(json.dumps({"auths": {"ghcr.io": {"auth": auth}}}) + "\n")
            os.chmod(config, 0o600)
            builder.run(
                "registry-push", ["docker", "--config", str(authenticated), "push", tag]
            )
        published = anonymous_manifest(repository, label)
        if published["image_id"] != image:
            raise RuntimeError("Published image identity mismatch")
        reference = "ghcr.io/" + repository + "@" + published["digest"]
        confirmed = anonymous_manifest(repository, published["digest"])
        if confirmed != published:
            raise RuntimeError("Published digest verification differs")
        anonymous = directory / "anonymous"
        anonymous.mkdir()
        (anonymous / "config.json").write_text('{"auths":{}}\n')
        builder.run(
            "registry-pull-anonymous",
            ["docker", "--config", str(anonymous), "pull", reference],
        )
        import subprocess

        actual = subprocess.check_output(
            ["docker", "image", "inspect", "--format", "{{.Id}}", reference], text=True
        ).strip()
        if actual != image:
            raise RuntimeError("Anonymous pull image identity mismatch")
    public_package(owner, name)
    return {
        "tag": tag,
        "digest_reference": reference,
        "visibility": "public",
        "public_before_push": True,
        "anonymous_manifest_verified": True,
        "anonymous_pull_verified": True,
        "package_url": package["html_url"],
        "published_at": datetime.now(UTC).isoformat(),
    }
