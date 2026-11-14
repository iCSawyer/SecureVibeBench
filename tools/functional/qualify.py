#!/usr/bin/env python3
"""Qualify one test contract on repeated fresh offline base/reference containers."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess

from securevibebench_evaluation.functional import ASSETS, require_contract, stage_verifier
from securevibebench_evaluation.harbor_assets.case_results import status_map
from securevibebench_evaluation.harbor_assets.differential import (
    FRAMEWORK, POLICY, checksum, derive_split, suite_hash, validate_spec,
)
from securevibebench_evaluation.harbor_native import write_config
from securevibebench_evaluation.images import read_task, validate_image, inspect_image


def require_case_outcomes(result, spec, source, directory):
    """Accept only outcomes that can become complete scoring obligations."""
    try:
        outcomes = status_map(result.get("cases"))
    except ValueError as error:
        raise RuntimeError("Invalid named case outcomes; see " + str(directory)) from error
    declared = {case["id"] for case in spec["cases"]}
    extra = set(outcomes) - declared
    if extra:
        raise RuntimeError("Unexpected case outcomes: " + ", ".join(sorted(extra))
                           + "; see " + str(directory))
    allowed = {"PASS", "FAIL"} if source == "base" else {"PASS"}
    rejected = {name: outcomes.get(name, "NOT_RUN") for name in declared
                if outcomes.get(name, "NOT_RUN") not in allowed}
    if rejected:
        expected = "Base cases need PASS or FAIL" if source == "base" else "Reference cases must PASS"
        details = ", ".join(name + "=" + rejected[name] for name in sorted(rejected))
        raise RuntimeError(expected + ": " + details + "; see " + str(directory))


def qualify(task, contract, reference_patch, output, repeats=2):
    if repeats < 2:
        raise ValueError("Qualification needs at least two runs per source tree")
    config = read_task(task)
    image = config["metadata"]["image"]
    info = inspect_image(image["id"])
    if info is None:
        raise ValueError("Missing local image for qualification: " + image["id"])
    validate_image(info, image["id"])
    output.mkdir(parents=True, exist_ok=False)
    target = output / "tasks" / task.name
    shutil.copytree(task, target)
    root = target / "tests"
    if (root / "contract").exists():
        (root / "contract").rename(output / "previous-contract")
    if (root / "functional.json").exists():
        (root / "functional.json").rename(output / "previous-functional.json")
    shutil.copytree(contract, root / "contract")
    draft = json.loads((root / "contract/spec.json").read_text())
    for field in ("qualification", "FAIL_TO_PASS", "PASS_TO_PASS"):
        draft.pop(field, None)
    # This hash is taken from the actual starting image, not a mutable tag.
    tree_cmd = ["docker", "run", "--rm", "--pull=never", "--network", "none",
                "--entrypoint", "/usr/bin/git", image["id"], "-C",
                config["metadata"]["repo_cwd"], "rev-parse", "svb-start^{tree}"]
    (output / "source-command.json").write_text(json.dumps(tree_cmd, indent=2) + "\n")
    tree = subprocess.check_output(tree_cmd, text=True).strip()
    spec = {**draft, "schema_version": 1, "policy": POLICY, "task": task.name,
            "image_id": image["id"], "base_tree": tree,
            "reference_commit": config["metadata"]["vic"],
            "framework_sha256": {name: checksum(ASSETS / name) for name in FRAMEWORK},
            "files_sha256": {str(p.relative_to(root)): checksum(p)
                             for p in sorted((root / "contract").rglob("*")) if p.is_file()}}
    validate_spec(spec, root, qualified=False, framework=ASSETS)
    (root / "functional.json").write_text(json.dumps(spec, indent=2) + "\n")
    stage_verifier(target)
    proof = {"base_runs": [], "reference_runs": [], "evidence": [],
             "reference_patch_sha256": checksum(reference_patch)}
    for source in ("base", "reference"):
        for index in range(repeats):
            directory = output / "evidence" / (source + "-%d" % index)
            directory.mkdir(parents=True)
            command = ["docker", "run", "--rm", "--pull=never", "--network", "none",
                       "--name", "junkai-f2p-" + task.name + "-" + source + "-%d" % index,
                       "--cpus", str(config["environment"].get("cpus", 4)),
                       "--memory", str(config["environment"].get("memory_mb", 8192)) + "m",
                       "-v", str(root.resolve()) + ":/tests:ro",
                       "-v", str(directory.resolve()) + ":/logs/verifier",
                       "--entrypoint", "/opt/svb/python/bin/python3", image["id"],
                       "-I", "/tests/_svb/differential_runtime.py", "measure"]
            if source == "reference":
                position = command.index("--entrypoint")
                command[position:position] = ["-v", str(reference_patch.resolve()) + ":/reference.patch:ro"]
                command.extend(["--reference-patch", "/reference.patch"])
            (directory / "command.json").write_text(json.dumps(command, indent=2) + "\n")
            timeout = min(int(config["verifier"].get("timeout_sec", 7200)),
                          spec.get("build_timeout_sec", 3600) + sum(case.get("timeout_sec", 60) for case in spec["cases"]) + 600)
            with (directory / "container.log").open("w") as log:
                try:
                    process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
                except subprocess.TimeoutExpired:
                    name = command[command.index("--name") + 1]
                    subprocess.run(["docker", "rm", "-f", name], stdout=log, stderr=subprocess.STDOUT, timeout=30)
                    (directory / "container.exit").write_text("124\n")
                    raise RuntimeError("Qualification timed out; see " + str(directory))
            (directory / "container.exit").write_text(str(process.returncode) + "\n")
            if process.returncode:
                raise RuntimeError("Qualification failed; see " + str(directory))
            try:
                result = json.loads((directory / "measure.json").read_text())
            except (OSError, ValueError) as error:
                raise RuntimeError("Missing or invalid measurement; see " + str(directory)) from error
            if not isinstance(result, dict):
                raise RuntimeError("Measurement is not an object; see " + str(directory))
            if result.get("build_exit_code") != 0 or result.get("completed") is not True:
                raise RuntimeError("Test suite did not build and finish (build_exit_code=%r, completed=%r); see %s"
                                   % (result.get("build_exit_code"), result.get("completed"), directory))
            require_case_outcomes(result, spec, source, directory)
            proof[source + "_runs"].append(result)
            proof["evidence"].append({"source": source, "run": index,
                                       "result_sha256": checksum(directory / "measure.json")})
    split = derive_split(proof["base_runs"], proof["reference_runs"], [case["id"] for case in spec["cases"]])
    spec.update({key: split[key] for key in ("FAIL_TO_PASS", "PASS_TO_PASS")})
    proof.update(suite_sha256=suite_hash(spec), excluded=split["excluded"],
                 qualified_at=datetime.now(timezone.utc).isoformat())
    spec["qualification"] = proof
    (root / "functional.json").write_text(json.dumps(spec, indent=2) + "\n")
    config["metadata"]["reward_policy"] = POLICY
    config["task"]["version"] = "3.0.0"
    write_config(target / "task.toml", config)
    try:
        require_contract(target, config)
    except (OSError, ValueError) as error:
        raise RuntimeError("Contract is not scorable: " + str(error)
                           + "; see " + str(output)) from error
    report = {"task": task.name, "policy": POLICY, "state": "qualified",
              "f2p": spec["FAIL_TO_PASS"], "p2p": spec["PASS_TO_PASS"],
              "excluded": split["excluded"], "task_path": str(target.resolve())}
    (output / "qualification.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--reference-patch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()
    print(json.dumps(qualify(args.task.resolve(), args.contract.resolve(), args.reference_patch.resolve(),
                             args.output.resolve(), args.repeats), indent=2))
