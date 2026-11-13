"""Versioned F2P/P2P contracts and repeatable qualification evidence."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import re

if __package__:
    from .case_results import status_map
else:
    from case_results import status_map

POLICY = "functional-f2p-p2p-v1"
FRAMEWORK = ("case_results.py", "differential.py", "differential_runtime.py", "source_patch.py")


def checksum(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def asset(root, name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "contract":
        raise ValueError("Unsafe functional test asset: " + name)
    target = Path(root).joinpath(*path.parts)
    if any(parent.is_symlink() for parent in (target, *target.parents)) or not target.is_file():
        raise ValueError("Missing regular functional test asset: " + name)
    return target


def suite_hash(spec):
    fields = {key: value for key, value in spec.items()
              if key not in {"qualification", "FAIL_TO_PASS", "PASS_TO_PASS"}}
    return hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _command(argv):
    if not isinstance(argv, list) or not argv or not argv[0] or any(not isinstance(x, str) or "\0" in x for x in argv):
        raise ValueError("Test commands must be nonempty argument lists")


def validate_spec(spec, root, *, qualified=True, framework=None):
    if not isinstance(spec, dict):
        raise ValueError("Expected a functional contract object")
    if spec.get("schema_version") != 1 or spec.get("policy") != POLICY:
        raise ValueError("Unsupported functional scoring policy")
    if not re.fullmatch(r"securevibebench-[0-9]+", spec.get("task", "")):
        raise ValueError("Invalid functional task ID")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", spec.get("image_id", "")):
        raise ValueError("Functional contract requires an immutable image ID")
    for key in ("base_tree", "reference_commit", "reference_tree"):
        if not re.fullmatch(r"[0-9a-f]{40}", spec.get(key, "")):
            raise ValueError("Functional contract requires " + key)
    files = spec.get("files_sha256", {})
    if not files or not isinstance(files, dict):
        raise ValueError("Functional test assets must be pinned")
    contract = Path(root) / "contract"
    actual = {str(path.relative_to(root)) for path in contract.rglob("*") if path.is_file()}
    if actual != set(files) or any(path.is_symlink() for path in contract.rglob("*")):
        raise ValueError("Functional test asset file set changed")
    if any(not isinstance(name, str) or not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected) for name, expected in files.items()):
        raise ValueError("Functional test assets require SHA256 hashes")
    for name, expected in files.items():
        if checksum(asset(root, name)) != expected:
            raise ValueError("Functional test asset checksum mismatch: " + name)
    framework_hashes = spec.get("framework_sha256", {})
    if not isinstance(framework_hashes, dict):
        raise ValueError("Functional framework must be pinned")
    for name, expected in framework_hashes.items():
        if name not in FRAMEWORK or checksum(Path(framework or Path(__file__).parent) / name) != expected:
            raise ValueError("Functional framework checksum mismatch: " + name)
    if set(spec.get("framework_sha256", {})) != set(FRAMEWORK):
        raise ValueError("Functional framework must be pinned")
    if spec.get("test_patch") is not None and spec["test_patch"] not in files:
        raise ValueError("Test patch must be a pinned test asset")
    if spec.get("build") is not None:
        _command(spec["build"])
    if type(spec.get("build_timeout_sec", 3600)) is not int or not 1 <= spec.get("build_timeout_sec", 3600) <= 7200:
        raise ValueError("Invalid functional build timeout")
    if not isinstance(spec.get("env", {}), dict) or any(
        not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or not isinstance(value, str)
        for key, value in spec.get("env", {}).items()
    ):
        raise ValueError("Invalid functional command environment")
    cases = spec.get("cases")
    if not isinstance(cases, list) or not all(isinstance(case, dict) for case in cases):
        raise ValueError("Functional cases must be a list of objects")
    for field in ("protected_paths", "allowed_source_paths"):
        paths = spec.get(field, [])
        if not isinstance(paths, list) or any(not isinstance(name, str) or not name or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or name.endswith("/") for name in paths):
            raise ValueError(field + " must contain relative source paths")
    names = []
    for case in cases:
        name = case.get("id")
        if not isinstance(name, str) or not name.strip() or "\0" in name:
            raise ValueError("Test cases require stable IDs")
        names.append(name)
        _command(case.get("command"))
        timeout = case.get("timeout_sec", 60)
        if type(timeout) is not int or not 1 <= timeout <= 3600:
            raise ValueError("Invalid test timeout: " + name)
    if not names or len(names) != len(set(names)):
        raise ValueError("Functional cases must be nonempty and distinct")
    if qualified:
        proof = spec.get("qualification", {})
        if not isinstance(proof, dict):
            raise ValueError("Functional qualification must be an object")
        for phase in ("base", "reference"):
            runs = proof.get(phase + "_runs", [])
            if not isinstance(runs, list) or any(not isinstance(run, dict) for run in runs):
                raise ValueError("Qualification measurements must be lists of objects")
        if proof.get("suite_sha256") != suite_hash(spec):
            raise ValueError("Functional qualification does not match this test suite")
        for phase, expected in (("base", spec["base_tree"]), ("reference", spec["reference_tree"])):
            if any(run.get("source_tree") != expected for run in proof.get(phase + "_runs", [])):
                raise ValueError("Qualification does not match the " + phase + " source tree")
        split = derive_split(proof.get("base_runs", []), proof.get("reference_runs", []), names)
        for key in ("FAIL_TO_PASS", "PASS_TO_PASS"):
            if spec.get(key) != split[key]:
                raise ValueError("Functional qualification does not support " + key)
        if not split["FAIL_TO_PASS"]:
            raise ValueError("Task needs tests: no stable FAIL_TO_PASS case")
    return spec


def derive_split(base_runs, reference_runs, names):
    """Use stable explicit failures; missing or skipped results are not F2P."""
    if not isinstance(base_runs, list) or not isinstance(reference_runs, list) or any(not isinstance(run, dict) for run in [*base_runs, *reference_runs]):
        raise ValueError("Qualification measurements must be lists of objects")
    if len(base_runs) < 2 or len(reference_runs) < 2:
        raise ValueError("Qualification requires two independent runs of each source tree")
    runs = []
    ids = [run.get("measurement_id") for run in [*base_runs, *reference_runs]]
    if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value) for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("Qualification requires independent measurement IDs")
    for run in [*base_runs, *reference_runs]:
        outcomes = status_map(run.get("cases", {}))
        if run.get("build_exit_code") != 0 or run.get("completed") is not True or set(outcomes) != set(names):
            raise ValueError("Qualification run did not build and execute the complete test suite")
        runs.append(outcomes)
    base, reference = runs[:len(base_runs)], runs[len(base_runs):]
    f2p, p2p, excluded = [], [], {}
    for name in sorted(names):
        before = {run[name] for run in base}
        after = {run[name] for run in reference}
        if (before | after) & {"ERROR", "NOT_RUN"}:
            raise ValueError("Qualification has execution errors: " + name)
        if before == {"PASS"} and after == {"FAIL"}:
            raise ValueError("Reference implementation regresses an existing test: " + name)
        if before == {"FAIL"} and after == {"PASS"}:
            f2p.append(name)
        elif before == after == {"PASS"}:
            p2p.append(name)
        else:
            excluded[name] = {"base": sorted(before), "reference": sorted(after)}
    return {"FAIL_TO_PASS": f2p, "PASS_TO_PASS": p2p, "excluded": excluded}


def grade(spec, run):
    outcomes = status_map(run.get("cases", {}))
    report = {}
    for key in ("FAIL_TO_PASS", "PASS_TO_PASS"):
        expected = spec[key]
        passed = [name for name in expected if outcomes.get(name) == "PASS"]
        failed = {name: outcomes.get(name, "NOT_RUN") for name in expected if name not in passed}
        report[key] = {"passed": passed, "failed": failed, "total": len(expected)}
    valid = (run.get("build_exit_code") == 0 and run.get("completed") is True
             and set(outcomes) == {case["id"] for case in spec["cases"]}
             and not any(status in {"ERROR", "NOT_RUN"} for status in outcomes.values()))
    passed = bool(spec["FAIL_TO_PASS"]) and valid and not any(group["failed"] for group in report.values())
    return {"policy": POLICY, "functional": int(passed), "valid_run": valid, **report}
