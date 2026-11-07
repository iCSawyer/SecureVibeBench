#!/usr/bin/env python3
"""Package native tasks, offline host wheels, and image provenance."""

import argparse
import gzip
import json
from pathlib import Path
import shutil
import sys
import tarfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "cpython_image"))
from complete_bundle import checksum, framework_tag


def build(output, host_bundle, source_tasks, bundle_name="securevibebench-arvo-10"):
    if Path(bundle_name).name != bundle_name or bundle_name in {"", ".", ".."}:
        raise ValueError("Use a single bundle directory name")
    output = Path(output).resolve()
    root = output / "distribution"
    root.mkdir(exist_ok=True)
    all_states = [
        json.loads(path.read_text())
        for path in sorted((output / "tasks").glob("*/status.json"))
    ]
    states = [state for state in all_states if state["state"] == "completed"]
    if len(states) != 10 or any(
        state["state"] != "completed"
        or state.get("registry", {}).get("visibility") != "private"
        for state in states
    ):
        raise RuntimeError("Require ten completed, verified private images")
    for name in ["wheels", "requirements-host.lock", "framework", "licenses"]:
        source = host_bundle / name
        target = root / name
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)
    # Maintainer recipes import these helpers outside the installed runtime.
    shutil.copytree(HERE.parent / "image_build", root / "tools/image_build",
                    ignore=shutil.ignore_patterns("__pycache__"), dirs_exist_ok=True)
    recipe = root / "recipe"
    recipe.mkdir(exist_ok=True)
    for name in ["arvo_images", "cpython_image"]:
        shutil.copytree(
            HERE.parent / name,
            recipe / name,
            ignore=shutil.ignore_patterns("__pycache__"),
            dirs_exist_ok=True,
        )
    shutil.copy2(HERE / "README.md", root / "README.md")
    if bundle_name != "securevibebench-arvo-10":
        readme = root / "README.md"
        text = (
            readme.read_text()
            .replace(
                "securevibebench-arvo-10-offline.tar.gz",
                bundle_name + "-offline.tar.gz",
            )
            .replace("cd securevibebench-arvo-10", "cd " + bundle_name)
        )
        readme.write_text(text)
    shutil.copy2(HERE / "import_images.py", root / "import_images.py")
    for name in [
        "selection.json",
        "provenance.json",
        "unit-tests-final.log",
        "lint.log",
    ]:
        source = output / name
        if source.is_file():
            destination = root / "evidence" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    entries = []
    for state in states:
        identifier = state["task"]
        taskname = "securevibebench-" + identifier
        private = output / "tasks" / identifier
        shutil.copytree(
            private / "bundle/tasks" / taskname,
            root / "tasks" / taskname,
            dirs_exist_ok=True,
        )
        shutil.copytree(
            source_tasks / taskname,
            recipe / "inputs" / taskname,
            ignore=shutil.ignore_patterns(
                "toolchain", "__pycache__", "resolv.conf", "docker-compose.yaml"
            ),
            dirs_exist_ok=True,
        )
        input_dockerfile = recipe / "inputs" / taskname / "environment/Dockerfile"
        input_lines = input_dockerfile.read_text().splitlines()
        input_lines[0] = "FROM " + state["base_image"]
        input_dockerfile.write_text("\n".join(input_lines) + "\n")
        evidence = root / "evidence" / identifier
        shutil.copytree(private / "bundle/evidence", evidence, dirs_exist_ok=True)
        for name in ["package-inventory.log"]:
            if (private / "logs" / name).exists():
                shutil.copy2(private / "logs" / name, evidence / name)
        shutil.copy2(private / "work/baseline.json", evidence / "gold/baseline.json")
        if (private / "functional-before.sh").exists():
            shutil.copy2(
                private / "functional-before.sh", evidence / "functional-before.sh"
            )
        verifier = evidence / "empty-submission-verifier"
        verifier.mkdir(exist_ok=True)
        for path in (private / "work/empty-submission-eval").rglob(
            "verifier/network.json"
        ):
            for source in path.parent.iterdir():
                if source.is_file() and (source.suffix in (".json", ".exit")):
                    shutil.copy2(source, verifier / source.name)
        if (private / "reference-before.sh").exists():
            shutil.copy2(
                private / "reference-before.sh", evidence / "reference-before.sh"
            )
        if (private / "reference-failure-diagnostics").exists():
            shutil.copytree(
                private / "reference-failure-diagnostics",
                evidence / "reference-failures-before-repair",
                dirs_exist_ok=True,
            )
        baseline = json.loads((private / "work/baseline.json").read_text())
        entries.append(
            {
                "task": identifier,
                "image_id": state["frozen_image"],
                "base_image": state["base_image"],
                "base_image_id": state["base_image_id"],
                "reference": json.loads((evidence / "gold/source.json").read_text()),
                "starting_source": json.loads(
                    (evidence / "start/source.json").read_text()
                ),
                "offline_reference": {
                    "passed": len(baseline.get("PassList", [])),
                    "failed": len(baseline.get("FailList", [])),
                    "skipped": len(baseline.get("UnknownList", [])),
                    "status": baseline.get("Status"),
                    "exit_code": int(
                        (evidence / "gold/offline-reference.log.exit").read_text()
                    ),
                },
                "reference_baseline_sha256": state["offline_gold_baseline_sha256"],
                "image_audit": state["image_audit"],
                "verification": state["verification"],
                "repairs": state.get("repair", {}),
                "registry": state["registry"],
                "toolchain": state["toolchain"],
                "native_mini_version": json.loads(
                    (evidence / "native-install/result.json").read_text()
                )["agent_info"]["version"],
            }
        )
    from catalog import export_task
    original_tasks = recipe / "generated-tasks"
    original_tasks.mkdir(exist_ok=True)
    for entry in entries:
        name = "securevibebench-" + entry["task"]
        source = root / "tasks" / name
        saved = original_tasks / name
        if saved.exists():
            raise FileExistsError("Use a new distribution directory")
        source.rename(saved)
        export_task(saved, source, entry)
    framework = json.loads((host_bundle / "manifest.json").read_text())[
        "framework_images"
    ]
    if framework_tag() not in {item["local_tag"] for item in framework}:
        raise RuntimeError("Harbor firewall image changed")
    manifest = {
        "schema_version": 1,
        "created_at": __import__("datetime")
        .datetime.now(__import__("datetime").timezone.utc)
        .isoformat(),
        "platform": "linux/amd64",
        "host_python": "3.12",
        "resources_per_task": {"cpus": 4, "memory_mb": 8192},
        "images": entries,
        "framework_images": framework,
        "files_sha256": {
            str(path.relative_to(root)): checksum(path)
            for path in sorted(root.rglob("*"))
            if path.is_file() and path.name not in ["manifest.json", "SHA256SUMS"]
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    archive = output / (bundle_name + "-offline.tar.gz")
    with (
        archive.open("wb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as gz,
        tarfile.open(fileobj=gz, mode="w") as tar,
    ):
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            member = tar.gettarinfo(
                str(path),
                arcname=bundle_name + "/" + str(path.relative_to(root)),
            )
            member.uid = member.gid = member.mtime = 0
            member.uname = member.gname = ""
            with path.open("rb") as stream:
                tar.addfile(member, stream)
    result = {
        "state": "completed",
        "count": len(entries),
        "bundle": str(archive),
        "sha256": checksum(archive),
        "bytes": archive.stat().st_size,
        "images": [item["registry"] for item in entries],
    }
    (output / "distribution-ready.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host-bundle", type=Path, required=True)
    parser.add_argument("--source-tasks", type=Path, required=True)
    parser.add_argument("--name", default="securevibebench-arvo-10")
    args = parser.parse_args()
    print(
        json.dumps(
            build(args.output, args.host_bundle, args.source_tasks, args.name), indent=2
        )
    )
