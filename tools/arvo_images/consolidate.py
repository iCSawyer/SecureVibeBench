"""Copy accepted task images to one Public package without changing digests."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
import base64

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.image_build.registry import (
    DEFAULT_PACKAGE,
    anonymous_manifest,
    credential,
    public_package,
)


class Consolidator:
    def __init__(self, args):
        self.args = args
        self.root = args.output.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.target = "ghcr.io/" + args.owner.lower() + "/" + args.package
        self.inventory = json.loads(args.inventory.read_text())["images"]
        self.lock = threading.RLock()
        path = self.root / "status.json"
        self.state = (
            json.loads(path.read_text())
            if path.exists()
            else {"target": self.target, "images": {}}
        )
        if self.state["target"] != self.target:
            raise ValueError("Run directory belongs to a different registry target")

    def save(self):
        with self.lock:
            self.state["updated_at"] = datetime.now(UTC).isoformat()
            self.state["completed"] = sum(
                row.get("state") == "completed" for row in self.state["images"].values()
            )
            for name, data in [
                ("status.json", self.state),
                (
                    "mapping.json",
                    {
                        "target": self.target,
                        "images": [
                            row
                            for row in self.state["images"].values()
                            if row.get("state") == "completed"
                        ],
                    },
                ),
            ]:
                path = self.root / name
                temporary = path.with_suffix(".tmp")
                temporary.write_text(json.dumps(data, indent=2) + "\n")
                temporary.replace(path)

    def run(self, folder, name, command, **kwargs):
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (name + ".log")
        if path.exists():
            archive = folder / "archive"
            archive.mkdir(exist_ok=True)
            path.rename(archive / (name + "-" + str(time.time_ns()) + ".log"))
        with path.open("w") as log:
            subprocess.run(
                command,
                env=self.environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                **kwargs,
            )

    def copy(self, row):
        identifier, image = str(row["task"]), row["image_id"]
        source = row["reference"]
        if not identifier.isdigit() or not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
            raise ValueError("Invalid task or image identity")
        prefix = "ghcr.io/" + self.args.owner.lower() + "/securevibebench"
        if not source.startswith(prefix) or not re.fullmatch(
            r"ghcr\.io/[a-z0-9/-]+@sha256:[0-9a-f]{64}", source
        ):
            raise ValueError("Source must be a pinned SecureVibeBench image")
        key = identifier + "-" + image[7:]
        previous = self.state["images"].get(key, {})
        tag = previous.get("tag") or (
            self.target
            + ":arvo-"
            + identifier
            + "-offline-"
            + self.args.version_date
            + "-"
            + image[7:19]
        )
        record = {
            "task": identifier,
            "image_id": image,
            "source_reference": source,
            "tag": tag,
            "state": "running",
        }
        with self.lock:
            self.state["images"][key] = record
            self.save()
        folder = self.root / "images" / key
        try:
            repository, digest = source.removeprefix("ghcr.io/").split("@", 1)
            source_manifest = anonymous_manifest(repository, digest)
            if source_manifest["image_id"] != image:
                raise ValueError(
                    "Source image identity differs from the accepted inventory"
                )
            target_repository = self.target.removeprefix("ghcr.io/")
            label = tag.split(":", 1)[1]
            existing = anonymous_manifest(target_repository, label, missing_ok=True)
            if existing and existing["digest"] != digest:
                raise ValueError("Refuse to overwrite a different image version")
            if not existing:
                self.run(
                    folder,
                    "copy",
                    [
                        str(self.args.crane.resolve()),
                        "copy",
                        "--no-clobber",
                        "--jobs",
                        "2",
                        source,
                        tag,
                    ],
                    timeout=3600,
                )
            target = anonymous_manifest(target_repository, digest)
            tagged = anonymous_manifest(target_repository, label)
            if target != source_manifest or tagged != source_manifest:
                raise ValueError(
                    "Migration changed the manifest digest or image identity"
                )
            reference = self.target + "@" + digest
            self.run(
                folder,
                "anonymous-pull",
                ["docker", "--config", str(self.anonymous), "pull", reference],
                timeout=600,
            )
            actual = subprocess.check_output(
                ["docker", "image", "inspect", "--format", "{{.Id}}", reference],
                text=True,
            ).strip()
            if actual != image:
                raise ValueError("Anonymous Docker pull changed the image identity")
            with self.lock:
                record.update(
                    state="completed",
                    reference=reference,
                    manifest_preserved=True,
                    anonymous_pull_verified=True,
                    completed_at=datetime.now(UTC).isoformat(),
                )
        except Exception as error:
            with self.lock:
                record.update(
                    state="failed", error=type(error).__name__ + ": " + str(error)
                )
        self.save()
        return record

    def execute(self):
        public_package(self.args.owner, self.args.package)
        with tempfile.TemporaryDirectory(
            prefix="junkai-registry-consolidation-"
        ) as temporary:
            directory = Path(temporary)
            auth = directory / "authenticated"
            auth.mkdir(mode=0o700)
            encoded = base64.b64encode(
                (self.args.owner + ":" + credential()).encode()
            ).decode()
            config = auth / "config.json"
            config.write_text(
                json.dumps({"auths": {"ghcr.io": {"auth": encoded}}}) + "\n"
            )
            os.chmod(config, 0o600)
            self.anonymous = directory / "anonymous"
            self.anonymous.mkdir()
            (self.anonymous / "config.json").write_text('{"auths":{}}\n')
            self.environment = {
                key: value
                for key, value in os.environ.items()
                if not any(
                    word in key.upper()
                    for word in [
                        "TOKEN",
                        "SECRET",
                        "API_KEY",
                        "GITHUB_DOCKER",
                        "DOCKER_AUTH_CONFIG",
                    ]
                )
            }
            self.environment["DOCKER_CONFIG"] = str(auth)
            with ThreadPoolExecutor(max_workers=self.args.workers) as pool:
                futures = [pool.submit(self.copy, row) for row in self.inventory]
                for future in as_completed(futures):
                    row = future.result()
                    print(row["task"], row["state"], flush=True)
        public_package(self.args.owner, self.args.package)
        return all(
            row.get("state") == "completed" for row in self.state["images"].values()
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--crane", type=Path, required=True)
    parser.add_argument("--owner", default="icsawyer")
    parser.add_argument("--package", default=DEFAULT_PACKAGE)
    parser.add_argument("--version-date", default=datetime.now(UTC).strftime("%Y%m%d"))
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]{8}", args.version_date) or args.workers < 1:
        parser.error("Use YYYYMMDD and a positive worker count")
    if not Consolidator(args).execute():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
