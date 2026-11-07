#!/usr/bin/env python3
"""Link existing GHCR packages through a label-only auxiliary image version."""

from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import urllib.request

from dotenv import dotenv_values

SOURCE_LABEL = "org.opencontainers.image.source"


class Linker:
    def __init__(self, args):
        self.args = args
        self.root = args.output.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.before = json.loads(args.audit.read_text())
        self.target = self.before["target_repository"]
        self.url = self.before["target_repository_url"]
        if self.target.lower() != "icsawyer/securevibebench":
            raise ValueError("Unexpected target repository")
        self.token = dotenv_values(Path(__file__).resolve().parents[2] / ".env").get(
            "GITHUB_DOCKER"
        )
        if not self.token:
            raise ValueError("Set GITHUB_DOCKER in the project .env")
        self.lock = threading.Lock()
        path = self.root / "status.json"
        self.state = (
            json.loads(path.read_text())
            if path.exists()
            else {"state": "running", "packages": {}}
        )

    def save(self):
        with self.lock:
            data = {**self.state, "updated_at": datetime.now(timezone.utc).isoformat()}
            temporary = self.root / ".status.json.tmp"
            temporary.write_text(json.dumps(data, indent=2) + "\n")
            temporary.replace(self.root / "status.json")

    def api(self, path):
        request = urllib.request.Request(
            "https://api.github.com/" + path,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.load(response)

    def run(self, name, stage, command):
        folder = self.root / name
        folder.mkdir(exist_ok=True)
        with (folder / (stage + ".log")).open("w") as log:
            subprocess.run(
                command,
                env=self.environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
            )

    def inspect(self, image):
        return json.loads(
            subprocess.check_output(["docker", "image", "inspect", image], text=True)
        )[0]

    def verify_original(self, item):
        image = self.inspect(item["image_id"])
        if image["RootFS"]["Layers"] != item["filesystem_layers"]:
            raise ValueError("Original filesystem changed")
        path = (
            "users/iCSawyer/packages/container/"
            + item["name"]
            + "/versions?per_page=100"
        )
        versions = self.api(path)
        digest = item["digest_reference"].split("@", 1)[1]
        original = next((row for row in versions if row["name"] == digest), None)
        if (
            not original
            or "offline-20261107" not in original["metadata"]["container"]["tags"]
        ):
            raise ValueError(
                "Original evaluation digest or tag changed: " + item["name"]
            )

    def link(self, item):
        name = item["name"]
        record = {
            **self.state["packages"].get(name, {}),
            "name": name,
            "state": "running",
            "original_image_id": item["image_id"],
            "original_digest_reference": item["digest_reference"],
        }
        record.pop("error", None)
        self.state["packages"][name] = record
        self.save()
        try:
            endpoint = "users/iCSawyer/packages/container/" + name
            package = self.api(endpoint)
            if (package.get("repository") or {}).get(
                "full_name", ""
            ).lower() == self.target.lower():
                record["already_linked"] = True
            else:
                folder = self.root / name
                context = folder / "context"
                context.mkdir(parents=True, exist_ok=True)
                original = self.inspect(item["image_id"])
                if original["Config"].get("OnBuild"):
                    raise ValueError("Refuse a base image with ONBUILD instructions")
                base = (
                    "junkai-svb-link-base-"
                    + str(item["task"])
                    + ":"
                    + item["image_id"][7:19]
                )
                auxiliary = (
                    item["digest_reference"].split("@", 1)[0]
                    + ":repository-link-20261107"
                )
                self.run(name, "tag-base", ["docker", "tag", item["image_id"], base])
                (context / "Dockerfile").write_text(
                    "FROM " + base + "\nLABEL " + SOURCE_LABEL + "=" + self.url + "\n"
                )
                self.run(
                    name,
                    "build-label",
                    [
                        "docker",
                        "build",
                        "--pull=false",
                        "--network=none",
                        "-t",
                        auxiliary,
                        str(context),
                    ],
                )
                linked = self.inspect(auxiliary)
                if linked["RootFS"]["Layers"] != original["RootFS"]["Layers"]:
                    raise ValueError("Label-only version changed filesystem layers")
                for field in (
                    "Env",
                    "Entrypoint",
                    "Cmd",
                    "WorkingDir",
                    "User",
                    "Volumes",
                ):
                    if linked["Config"].get(field) != original["Config"].get(field):
                        raise ValueError(
                            "Label-only version changed runtime config: " + field
                        )
                if linked["Config"]["Labels"][SOURCE_LABEL] != self.url:
                    raise ValueError("Repository source label missing")
                record.update(
                    auxiliary_tag=auxiliary,
                    auxiliary_image_id=linked["Id"],
                    filesystem_unchanged=True,
                )
                self.save()
                self.run(name, "push", ["docker", "push", auxiliary])
                self.run(name, "remove-base-tag", ["docker", "image", "rm", base])
                for attempt in range(8):
                    package = self.api(endpoint)
                    linked_repository = (package.get("repository") or {}).get(
                        "full_name", ""
                    )
                    if linked_repository.lower() == self.target.lower():
                        break
                    if attempt < 7:
                        time.sleep(2)
                if (package.get("repository") or {}).get(
                    "full_name", ""
                ).lower() != self.target.lower():
                    raise RuntimeError(
                        "Source label was pushed but repository association was not confirmed"
                    )
                info = self.inspect(auxiliary)
                record["auxiliary_digest_reference"] = next(
                    value
                    for value in info["RepoDigests"]
                    if value.startswith(auxiliary.split(":")[0] + "@")
                )
            self.verify_original(item)
            record.update(
                state="completed",
                repository=package["repository"]["full_name"],
                visibility=package["visibility"],
                original_digest_and_tag_preserved=True,
            )
            print(name, "linked; evaluation digest preserved", flush=True)
        except Exception as error:
            record.update(
                state="failed", error=type(error).__name__ + ": " + str(error)
            )
            print(name, record["error"], flush=True)
        self.save()
        return record

    def execute(self):
        selected = [
            row
            for row in self.before["packages"]
            if not self.args.task or str(row["task"]) in self.args.task
        ]
        if not selected:
            raise ValueError("No matching image packages")
        for row in selected:
            if not re.fullmatch(r"securevibebench-arvo-[0-9]+", row["name"]):
                raise ValueError("Unexpected package name")
            prefix = "ghcr.io/icsawyer/" + row["name"] + "@sha256:"
            if not re.fullmatch(
                re.escape(prefix) + r"[0-9a-f]{64}", row["digest_reference"]
            ):
                raise ValueError(
                    "Package digest points outside the requested namespace"
                )
        self.state.update(
            state="running", selected_packages=[row["name"] for row in selected]
        )
        self.save()
        with tempfile.TemporaryDirectory(prefix="junkai-svb-ghcr-auth-") as temporary:
            config = Path(temporary) / "config.json"
            auth = base64.b64encode(("iCSawyer:" + self.token).encode()).decode()
            config.write_text(json.dumps({"auths": {"ghcr.io": {"auth": auth}}}))
            config.chmod(0o600)
            self.environment = {**os.environ, "DOCKER_CONFIG": temporary}
            with ThreadPoolExecutor(max_workers=self.args.workers) as workers:
                futures = [workers.submit(self.link, row) for row in selected]
                records = [future.result() for future in as_completed(futures)]
        self.state["state"] = (
            "completed"
            if all(row["state"] == "completed" for row in records)
            else "failed"
        )
        self.save()
        return int(self.state["state"] != "completed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task", nargs="*")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    return Linker(args).execute()


if __name__ == "__main__":
    raise SystemExit(main())
