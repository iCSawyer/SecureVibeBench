#!/usr/bin/env python3
"""Prepare, verify, and privately publish native Harbor ARVO environments."""

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import tomllib
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "cpython_image"))
from prepare import Builder as CPythonBuilder
from freeze import native_install, audit_image
from complete_bundle import checksum
from securevibebench_evaluation.harbor_native import select_cpus, write_config
for parent in Path(__file__).resolve().parents:
    if (parent / 'tools/image_build').is_dir():
        sys.path.insert(0, str(parent))
        break
from tools.image_build.task_assets import materialize
from tools.image_build.toolchain import copy_uv, configure_package_installation


def now():
    return datetime.now(timezone.utc).isoformat()


def api(endpoint):
    config = json.loads((Path.home() / ".docker/config.json").read_text())
    _, token = (
        base64.b64decode(config["auths"]["ghcr.io"]["auth"]).decode().split(":", 1)
    )
    request = urllib.request.Request(
        "https://api.github.com/" + endpoint,
        headers={
            "Authorization": "Bearer " + token,
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


def image_info(image):
    return json.loads(
        subprocess.check_output(["docker", "image", "inspect", image], text=True)
    )[0]


FREETYPE_TASKS = {"58663", "58660", "58671", "60475", "58428", "60467"}
AUTOTOOLS_CLEAN_TASKS = {"32340", "32345", "20702", "48736", "59438", "64337"}


def zstd_cli_tests(text):
    command = '(\n  cd tests\n  ZSTD="$(pwd)/../programs/zstd" ZSTD_BIN="$(pwd)/../programs/zstd" DATAGEN_BIN="$(pwd)/datagen" ./playTests.sh\n)'
    return re.sub(
        r"ZSTD_BIN=.*?\./tests/playTests\.sh",
        lambda match: command,
        text,
        count=1,
        flags=re.DOTALL,
    )


def stable_functional(text, identifier=None):
    # Preserve test commands; permit rerunning scripts that create a build folder.
    result = re.sub(r"(?m)^mkdir build(?=\s|$)", "mkdir -p build", text)
    if identifier in AUTOTOOLS_CLEAN_TASKS:
        result = "if [ -f Makefile ]; then make distclean; fi\n" + result
    if identifier in FREETYPE_TASKS:
        result = result.replace(
            './configure LIBS="-lpthread"',
            './configure LIBS="-lpthread" --with-freetype=yes',
        )
    if identifier == "3522":
        result = "make clean\nunset CC CXX CFLAGS CXXFLAGS LDFLAGS\n" + zstd_cli_tests(
            result
        )
    return result


def stable_reference(text, identifier):
    if identifier in FREETYPE_TASKS:
        text = text.replace(" libtool-dev", "").replace(
            './configure LIBS="-lpthread"',
            './configure LIBS="-lpthread" --with-freetype=yes',
        )
    if identifier in AUTOTOOLS_CLEAN_TASKS:
        text = re.sub(
            r"(?m)^(git checkout[^\n]*\n)",
            r"\1if [ -f Makefile ]; then make distclean; fi\n",
            text,
            count=1,
        )
    if identifier == "3522":
        text = re.sub(
            r"(?m)^(git checkout[^\n]*\n)",
            r"\1make clean\nunset CC CXX CFLAGS CXXFLAGS LDFLAGS\n",
            text,
            count=1,
        )
    if identifier == "3522":
        text = zstd_cli_tests(text)
    return text


class Builder:
    run = CPythonBuilder.run
    save = CPythonBuilder.save
    collect = CPythonBuilder.collect
    task_config = CPythonBuilder.task_config

    def __init__(self, args, task):
        self.args = args
        self.source = task.resolve()
        self.config = tomllib.loads((self.source / "task.toml").read_text())
        self.id = str(self.config["metadata"]["localid"])
        self.output = args.output.resolve() / "tasks" / self.id
        self.bundle = self.output / "bundle"
        self.work = self.output / "work"
        self.logs = self.output / "logs"
        for path in (self.bundle, self.work, self.logs):
            path.mkdir(parents=True, exist_ok=True)
        self.task = self.bundle / "tasks" / self.source.name
        if not self.task.exists():
            shutil.copytree(
                self.source,
                self.task,
                ignore=shutil.ignore_patterns(
                    "toolchain", "__pycache__", "resolv.conf", "docker-compose.yaml"
                ),
            )
        self.cpus = select_cpus(self.output, args.cpus)
        self.suffix = hashlib.sha256(str(self.output).encode()).hexdigest()[:8]
        self.env = {
            k: v
            for k, v in os.environ.items()
            if not any(
                word in k.upper()
                for word in (
                    "TOKEN",
                    "SECRET",
                    "API_KEY",
                    "ACCESS_KEY",
                    "CODEX_AUTH",
                    "BASE_URL",
                    "API_BASE",
                )
            )
        }
        self.env["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
        state = self.output / "status.json"
        self.state = (
            json.loads(state.read_text())
            if state.exists()
            else {
                "state": "running",
                "task": self.id,
                "started_at": now(),
                "stages": {},
            }
        )
        self.save()

    def phase(self, name, image, *, create=False):
        container = "junkai-arvo-image-" + self.id + "-" + name + "-" + self.suffix
        existing = subprocess.run(
            ["docker", "inspect", container],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if existing.returncode == 0:
            info = json.loads(existing.stdout)[0]
            if info["State"]["Running"]:
                raise RuntimeError(
                    "Existing preparation container is still running: " + container
                )
            self.collect(container, "archive-" + name + "-" + str(time.time_ns()))
            self.run("archive-" + name, ["docker", "logs", container], check=False)
            self.run("remove-stopped-" + name, ["docker", "rm", container])
        command = [
            "docker",
            "create" if create else "run",
            "--name",
            container,
            "--network",
            "none",
            "--cpus",
            str(self.args.cpus),
            "--cpuset-cpus",
            ",".join(map(str, self.cpus)),
            "--memory",
            str(self.args.memory_mb) + "m",
            "--entrypoint",
            "/opt/svb/python/bin/python3",
            image,
            "/opt/svb/image_prepare.py",
            name,
        ]
        if create:
            self.run("create-" + name, command)
        else:
            result = self.run(name, command, check=False)
            self.collect(container, name)
            if result.returncode:
                raise RuntimeError(
                    "Container phase failed: "
                    + name
                    + "; see logs and collected preparation evidence"
                )
        return container

    def foundation(self):
        functional = stable_functional(
            (self.source / "environment/svb/functional.sh").read_text(), self.id
        )
        functional_sha = hashlib.sha256(functional.encode()).hexdigest()
        if self.state.get("foundation_image"):
            if self.state.get("functional_sha256") != functional_sha:
                previous = (self.work / "foundation/svb/functional.sh").read_text()
                if previous != functional:
                    if self.state.get("candidate_image"):
                        raise RuntimeError(
                            "Functional policy changed after snapshot; use a new output directory"
                        )
                    overlay = self.work / ("functional-overlay-" + str(time.time_ns()))
                    overlay.mkdir()
                    (overlay / "functional.sh").write_text(functional)
                    reference = stable_reference(
                        (self.source / "environment/svb/reference.sh").read_text(),
                        self.id,
                    )
                    (overlay / "reference.sh").write_text(reference)
                    (self.task / "environment/svb/reference.sh").write_text(reference)
                    (overlay / "Dockerfile").write_text(
                        "FROM "
                        + self.state["foundation_image"]
                        + "\nCOPY functional.sh reference.sh /opt/svb/\n"
                    )
                    tag = "junkai-arvo-foundation-" + self.id + ":" + self.suffix
                    self.run(
                        "functional-overlay",
                        ["docker", "build", "--pull=false", "-t", tag, str(overlay)],
                    )
                    self.state["foundation_image"] = image_info(tag)["Id"]
                    shutil.copy2(
                        self.work / "foundation/svb/functional.sh",
                        self.output / "functional-before.sh",
                    )
                (self.task / "environment/svb/functional.sh").write_text(functional)
                self.state["functional_sha256"] = functional_sha
                self.save()
            return self.state["foundation_image"]
        context = self.work / "foundation"
        if context.exists():
            context.rename(self.work / ("foundation-archive-" + str(time.time_ns())))
        materialize(self.task, context, self.config["metadata"])
        if self.id in {"20702", "48736", "59438"}:
            compatibility = context / "svb/prepare.sh"
            shutil.copy2(HERE / "file_prepare.sh", compatibility)
            shutil.copy2(compatibility, self.task / "environment/svb/prepare.sh")
        if self.id == "14529":
            compatibility = context / "svb/prepare.sh"
            shutil.copy2(HERE / "lwan_prepare.sh", compatibility)
            shutil.copy2(compatibility, self.task / "environment/svb/prepare.sh")
        reference = context / "svb/reference.sh"
        original_reference = reference.read_text()
        reference.write_text(stable_reference(original_reference, self.id))
        if reference.read_text() != original_reference:
            (self.output / "reference-before.sh").write_text(original_reference)
            shutil.copy2(reference, self.task / "environment/svb/reference.sh")
        functional = context / "svb/functional.sh"
        original = functional.read_text()
        functional.write_text(stable_functional(original, self.id))
        if original != functional.read_text():
            (self.output / "functional-before.sh").write_text(original)
            shutil.copy2(functional, self.task / "environment/svb/functional.sh")
        (context / "svb/image-metadata.json").write_text(
            json.dumps(self.config["metadata"], indent=2) + "\n"
        )
        shutil.copy2(HERE / "container_prepare.py", context / "svb/image_prepare.py")
        uv = context / "toolchain/bin/uv"
        uv.parent.mkdir(parents=True, exist_ok=True)
        self.state["toolchain"] = copy_uv(uv, self.args.output / "toolchain")
        base = (
            (context / "Dockerfile")
            .read_text()
            .splitlines()[0]
            .removeprefix("FROM ")
            .strip()
        )
        try:
            info = image_info(base)
        except subprocess.CalledProcessError:
            self.run("pull-base", ["docker", "pull", base])
            info = image_info(base)
        pinned = next(
            (
                value
                for value in info.get("RepoDigests", [])
                if value.startswith("n132/arvo@")
            ),
            info["Id"],
        )
        self.state["base_image"] = pinned
        self.state["base_image_id"] = info["Id"]
        source = (context / "Dockerfile").read_text().splitlines()
        source[0] = "FROM " + pinned
        source = [
            line.replace(
                "/opt/svb/runtime.py prepare", "/opt/svb/image_prepare.py online"
            )
            for line in source
        ]
        (context / "Dockerfile").write_text("\n".join(source) + "\n")
        configure_package_installation(context / "Dockerfile")
        tag = "junkai-arvo-foundation-" + self.id + ":" + self.suffix
        self.run(
            "online-preparation",
            [
                "docker",
                "build",
                "--pull=false",
                "--cpuset-cpus",
                ",".join(map(str, self.cpus)),
                "--memory",
                str(self.args.memory_mb) + "m",
                "-t",
                tag,
                str(context),
            ],
        )
        foundation = image_info(tag)["Id"]
        self.state["foundation_image"] = foundation
        self.state["functional_sha256"] = functional_sha
        self.save()
        return foundation

    def snapshot(self, foundation):
        if self.state.get("candidate_image"):
            self.candidate = self.state["candidate_image"]
            return self.candidate
        gold = self.phase("gold", foundation)
        baseline = self.work / "baseline.json"
        self.run(
            "copy-gold-baseline",
            ["docker", "cp", gold + ":/opt/svb/baseline.json", str(baseline)],
        )
        self.state["offline_gold_baseline_sha256"] = checksum(baseline)
        start = self.phase("start", foundation, create=True)
        self.run(
            "inject-gold-baseline",
            ["docker", "cp", str(baseline), start + ":/opt/svb/baseline.json"],
        )
        self.run("start", ["docker", "start", "-a", start])
        code = int(
            self.run(
                "start-exit",
                ["docker", "inspect", start, "--format", "{{.State.ExitCode}}"],
                capture=True,
            ).stdout.strip()
        )
        self.collect(start, "start")
        if code:
            raise RuntimeError("Start preparation failed: " + str(code))
        tag = "junkai-arvo-start-" + self.id + ":" + self.suffix
        self.run(
            "commit-start",
            [
                "docker",
                "commit",
                "--change",
                'ENTRYPOINT ["/usr/bin/env"]',
                "--change",
                'CMD ["bash","-c","sleep infinity"]',
                start,
                tag,
            ],
        )
        self.candidate = image_info(tag)["Id"]
        self.phase("probe", self.candidate)
        self.state["candidate_image"] = self.candidate
        self.save()
        return self.candidate

    def freeze(self):
        if self.state.get("frozen_image"):
            return self.state["frozen_image"]
        native = native_install(
            self,
            "native-install",
            self.state.get("agent_install_cache_image", self.candidate),
            public=True,
        )
        info = json.loads(
            subprocess.check_output(["docker", "inspect", native], text=True)
        )[0]
        if info["Config"].get("Volumes"):
            raise RuntimeError("Native snapshot contains file volumes")
        changes = [
            "ENV UV_OFFLINE=1",
            'ENTRYPOINT ["/usr/bin/env"]',
            'CMD ["bash","-c","sleep infinity"]',
        ]
        for value in info["Config"].get("Env", []):
            key, content = value.split("=", 1)
            if content and any(
                marker in key.upper()
                for marker in [
                    "API_KEY",
                    "AUTH_TOKEN",
                    "ACCESS_TOKEN",
                    "AWS_ACCESS_KEY",
                    "AWS_SECRET",
                    "GITHUB_TOKEN",
                    "GH_TOKEN",
                    "HF_TOKEN",
                ]
            ):
                raise RuntimeError("Credential in prepared image")
            if "proxy" in key.lower() or key.startswith("HARBOR_"):
                changes.append("ENV " + key + "=")
        for key in info["Config"].get("Labels") or {}:
            if key.startswith("com.docker.compose."):
                changes.append("LABEL " + key + '=""')
        tag = "securevibebench/arvo-" + self.id + ":offline-20261107"
        command = ["docker", "commit"]
        for value in changes:
            command += ["--change", value]
        self.run("freeze-native", command + [native, tag])
        image = image_info(tag)["Id"]
        self.state["image_audit"] = audit_image(self, image)
        self.state["frozen_image"] = image
        self.save()
        self.release_installation(native, info)
        return image

    def release_installation(self, container, info):
        """Release only this task's stopped installer after its audited snapshot."""
        if (
            not self.state.get("frozen_image")
            or self.state.get("image_audit", {}).get("credentials_present") is not False
        ):
            raise RuntimeError("Refuse installer release before an audited snapshot")
        if info["State"]["Running"]:
            raise RuntimeError("Installer unexpectedly running after snapshot")
        project = (info["Config"].get("Labels") or {}).get(
            "com.docker.compose.project", ""
        )
        if not project.startswith("securevibebench-" + self.id + "__"):
            raise RuntimeError("Installer ownership label differs")
        self.run("release-installer", ["docker", "rm", container])
        for name in info.get("NetworkSettings", {}).get("Networks", {}):
            network = json.loads(
                subprocess.check_output(
                    ["docker", "network", "inspect", name], text=True
                )
            )[0]
            if (network.get("Labels") or {}).get(
                "com.docker.compose.project"
            ) == project and not network.get("Containers"):
                self.run("release-installer-network", ["docker", "network", "rm", name])

    def verify(self, image):
        if self.state.get("verification"):
            return
        native_install(self, "offline-native-install", image, public=False)
        (self.task / "environment/Dockerfile").write_text(
            "FROM " + image + "\nWORKDIR " + self.config["metadata"]["repo_cwd"] + "\n"
        )
        self.task_config(image, self.task, prepared=True)
        submission = self.work / "empty-submission" / self.task.name
        submission.mkdir(parents=True, exist_ok=True)
        (submission / "submission.patch").write_text("")
        result = self.work / "empty-submission-eval"
        if result.exists():
            result.rename(
                self.work / ("empty-submission-eval-archive-" + str(time.time_ns()))
            )
        from tools.image_build.verify import score_local
        evaluation = score_local(self, submission.parent, result, image, "offline-empty-submission")
        records = evaluation.get("results", [])
        if len(records) != 1 or records[0].get("exception"):
            raise RuntimeError("Offline submission verification failed")
        network_logs = list(result.rglob("verifier/network.json"))
        if len(network_logs) != 1:
            raise RuntimeError("Missing verifier network evidence")
        for path in network_logs:
            if any(json.loads(path.read_text()).values()):
                raise RuntimeError("Verifier network reachable")
        self.state["verification"] = {
            "native_setup_offline": True,
            "empty_submission_rewards": records[0]["rewards"],
            "model_calls": 0,
        }
        self.run(
            "package-inventory",
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--entrypoint",
                "bash",
                image,
                "-lc",
                "uv tool list && uv pip freeze --python /root/.local/share/uv/tools/mini-swe-agent/bin/python",
            ],
            capture=True,
        )
        self.save()

    def publish(self, image):
        if not self.state.get("verification") or not self.state.get("image_audit"):
            raise RuntimeError(
                "Refuse publication before offline verification and credential audit"
            )
        if self.state.get("registry"):
            return self.state["registry"]
        name = "securevibebench-arvo-" + self.id
        endpoint = "users/" + self.args.owner + "/packages/container/" + name
        package = api(endpoint)
        if package and package.get("visibility") != "private":
            raise RuntimeError("Refuse to push to a non-private package")
        tag = "ghcr.io/" + self.args.owner.lower() + "/" + name + ":offline-20261107"
        self.run("registry-tag", ["docker", "tag", image, tag])
        self.run("registry-push", ["docker", "push", tag])
        package = api(endpoint)
        if not package or package.get("visibility") != "private":
            raise RuntimeError("Private visibility not verified")
        reference = next(
            item
            for item in image_info(tag)["RepoDigests"]
            if item.startswith(tag.split(":")[0] + "@")
        )
        self.run("registry-pull", ["docker", "pull", reference])
        if image_info(reference)["Id"] != image:
            raise RuntimeError("Registry image identity mismatch")
        self.state["registry"] = {
            "tag": tag,
            "digest_reference": reference,
            "visibility": "private",
            "package_url": package["html_url"],
        }
        self.save()
        return self.state["registry"]

    def execute(self):
        if self.state["state"] == "completed":
            return self.state
        try:
            if self.state.get("error"):
                self.state.setdefault("attempt_history", []).append(
                    {"error": self.state["error"], "at": now()}
                )
            self.state["state"] = "running"
            self.state.pop("error", None)
            self.save()
            foundation = self.foundation()
            self.candidate = self.snapshot(foundation)
            image = self.freeze()
            self.verify(image)
            registry = self.publish(image) if self.args.publish else None
            # Ship source recipes separately from Docker's content-addressed image.
            for name in ["resolv.conf", "docker-compose.yaml"]:
                (self.task / "environment" / name).unlink(missing_ok=True)
            (self.task / "environment/Dockerfile").write_text(
                "FROM "
                + (registry["digest_reference"] if registry else image)
                + "\nWORKDIR "
                + self.config["metadata"]["repo_cwd"]
                + "\n"
            )
            config = self.task_config(image, self.task, prepared=True)
            config["metadata"].update(
                network_runtime_verified=True,
                offline_reference_baseline_sha256=self.state[
                    "offline_gold_baseline_sha256"
                ],
            )
            write_config(self.task / "task.toml", config)
            self.state.update(state="completed", finished_at=now())
            self.save()
        except Exception as error:
            (self.logs / ("exception-" + str(time.time_ns()) + ".log")).write_text(
                traceback.format_exc()
            )
            self.state.update(
                state="failed", error=type(error).__name__ + ": " + str(error)
            )
            self.save()
        return self.state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--task", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--cpus", type=int, default=4)
    parser.add_argument("--memory-mb", type=int, default=8192)
    parser.add_argument("--owner", default="icsawyer")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.publish:
        user = api("user")
        if not user or user["login"].lower() != args.owner.lower():
            parser.error("Authenticated registry owner differs")
    (args.output / "command.json").write_text(json.dumps(sys.argv, indent=2) + "\n")
    states = {}
    lock = threading.Lock()

    def work(identifier):
        result = Builder(args, args.tasks / ("securevibebench-" + identifier)).execute()
        with lock:
            states[identifier] = result
            (args.output / "status.json").write_text(
                json.dumps(
                    {
                        "updated_at": now(),
                        "total": len(args.task),
                        "completed": sum(
                            v["state"] == "completed" for v in states.values()
                        ),
                        "failed": sum(v["state"] == "failed" for v in states.values()),
                        "workers": args.workers,
                        "tasks": states,
                    },
                    indent=2,
                )
                + "\n"
            )
        return identifier, result["state"]

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(work, identifier) for identifier in args.task]
        for future in as_completed(futures):
            print(future.result(), flush=True)
    if any(state["state"] != "completed" for state in states.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
