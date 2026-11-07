#!/usr/bin/env python3
"""Repair task 58663 without changing its starting source or native agent layer."""

import argparse
import importlib.util
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("batch_images", HERE / "prepare.py")
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)


def repair(args):
    builder = batch.Builder(args, args.tasks / "securevibebench-58663")
    previous = json.loads(json.dumps(builder.state))
    folder = builder.work / "freetype-repair"
    folder.mkdir(exist_ok=True)
    (folder / "previous-state.json").write_text(json.dumps(previous, indent=2) + "\n")
    builder.state.update(
        state="running",
        repair={
            "reason": "Invalid libtool-dev package aborted the original apt transaction; FreeType was missing, disabling 69 shaping tests.",
            "previous_image": previous["frozen_image"],
            "previous_registry": previous["registry"],
        },
    )
    builder.save()
    functional = batch.stable_functional(
        (builder.source / "environment/svb/functional.sh").read_text(), "58663"
    )
    reference = batch.stable_reference(
        (builder.source / "environment/svb/reference.sh").read_text(), "58663"
    )
    (folder / "functional.sh").write_text(functional)
    (folder / "reference.sh").write_text(reference)
    (builder.output / "functional-before.sh").write_text(
        (builder.task / "environment/svb/functional.sh").read_text()
    )
    (builder.output / "reference-before.sh").write_text(
        (builder.task / "environment/svb/reference.sh").read_text()
    )
    for name in ["functional.sh", "reference.sh"]:
        shutil.copy2(folder / name, builder.task / "environment/svb" / name)
    dockerfile = (
        "FROM "
        + previous["frozen_image"]
        + "\nUSER root\nRUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends libfreetype6-dev && pkg-config --exists freetype2\nCOPY functional.sh reference.sh /opt/svb/\n"
    )
    (folder / "Dockerfile").write_text(dockerfile)
    tag = "junkai-arvo-freetype-58663:" + builder.suffix
    builder.run(
        "freetype-dependencies",
        [
            "docker",
            "build",
            "--pull=false",
            "--cpuset-cpus",
            ",".join(map(str, builder.cpus)),
            "--memory",
            str(args.memory_mb) + "m",
            "-t",
            tag,
            str(folder),
        ],
    )
    prepared = batch.image_info(tag)["Id"]
    old_command = previous["stages"]["gold"]["command"]
    old_gold = old_command[old_command.index("--name") + 1]
    git = folder / "original-git"
    builder.run(
        "copy-reference-git",
        ["docker", "cp", old_gold + ":/src/harfbuzz/.git", str(git)],
    )
    gold = "junkai-arvo-image-58663-freetype-gold-" + builder.suffix
    command = "rm -rf /src/harfbuzz/.git && cp -a /opt/svb/repair-original-git /src/harfbuzz/.git && exec /opt/svb/python/bin/python3 /opt/svb/image_prepare.py gold"
    builder.run(
        "create-freetype-gold",
        [
            "docker",
            "create",
            "--name",
            gold,
            "--network",
            "none",
            "--cpus",
            str(args.cpus),
            "--cpuset-cpus",
            ",".join(map(str, builder.cpus)),
            "--memory",
            str(args.memory_mb) + "m",
            "--entrypoint",
            "/bin/bash",
            prepared,
            "-lc",
            command,
        ],
    )
    builder.run(
        "inject-reference-git",
        ["docker", "cp", str(git), gold + ":/opt/svb/repair-original-git"],
    )
    builder.run("freetype-gold", ["docker", "start", "-a", gold])
    exit_code = int(
        builder.run(
            "freetype-gold-exit",
            ["docker", "inspect", gold, "--format", "{{.State.ExitCode}}"],
            capture=True,
        ).stdout.strip()
    )
    if exit_code:
        raise RuntimeError("Repaired reference did not finish normally")
    evidence = builder.bundle / "evidence/gold"
    evidence.rename(builder.bundle / "evidence/gold-before-freetype")
    builder.collect(gold, "gold")
    baseline = builder.work / "baseline.json"
    shutil.copy2(baseline, folder / "baseline-before.json")
    builder.run(
        "copy-freetype-baseline",
        ["docker", "cp", gold + ":/opt/svb/baseline.json", str(baseline)],
    )
    result = json.loads(baseline.read_text())
    if len(result.get("PassList", [])) <= 85 or len(result.get("FailList", [])) >= 69:
        raise RuntimeError("FreeType repair did not restore shaping-test coverage")
    final_context = folder / "final"
    final_context.mkdir(exist_ok=True)
    shutil.copy2(baseline, final_context / "baseline.json")
    (final_context / "Dockerfile").write_text(
        "FROM " + prepared + "\nCOPY baseline.json /opt/svb/baseline.json\n"
    )
    final_tag = "securevibebench/arvo-58663:offline-20261107"
    builder.run(
        "freeze-freetype-baseline",
        ["docker", "build", "--pull=false", "-t", final_tag, str(final_context)],
    )
    image = batch.image_info(final_tag)["Id"]
    builder.state["offline_gold_baseline_sha256"] = batch.checksum(baseline)
    builder.state["image_audit"] = batch.audit_image(builder, image)
    builder.state.update(frozen_image=image, candidate_image=image)
    builder.state.pop("verification", None)
    builder.state.pop("registry", None)
    builder.state["repair"].update(
        reference_passed=len(result.get("PassList", [])),
        reference_failed=len(result.get("FailList", [])),
        native_agent_layer_reused=True,
        probe_superseded_by_actual_verifier=True,
    )
    builder.save()
    builder.verify(image)
    registry = builder.publish(image)
    for name in ["resolv.conf", "docker-compose.yaml"]:
        (builder.task / "environment" / name).unlink(missing_ok=True)
    (builder.task / "environment/Dockerfile").write_text(
        "FROM " + registry["digest_reference"] + "\nWORKDIR /src/harfbuzz\n"
    )
    config = builder.task_config(image, builder.task, prepared=True)
    config["metadata"].update(
        network_runtime_verified=True,
        offline_reference_baseline_sha256=builder.state["offline_gold_baseline_sha256"],
        freetype_required=True,
    )
    batch.write_config(builder.task / "task.toml", config)
    builder.run(
        "system-package-inventory",
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "dpkg-query",
            image,
            "-W",
        ],
        capture=True,
    )
    packages = builder.bundle / "evidence/start/packages.log"
    shutil.copy2(packages, packages.with_name("packages-before-freetype.log"))
    shutil.copy2(builder.logs / "system-package-inventory.log", packages)
    builder.state.update(state="completed", finished_at=batch.now())
    builder.save()
    print(
        json.dumps(
            {"state": "completed", "reference": result, "registry": registry}, indent=2
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cpus", type=int, default=4)
    parser.add_argument("--memory-mb", type=int, default=8192)
    parser.add_argument("--owner", default="icsawyer")
    args = parser.parse_args()
    args.publish = True
    repair(args)
