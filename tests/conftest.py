"""Small qualified task fixtures for host-only staging and publishing tests."""

import json
from pathlib import Path
import shutil
import uuid

import pytest


@pytest.fixture
def qualified_task():
    def prepare(task):
        from securevibebench_evaluation import functional
        from securevibebench_evaluation.harbor_assets import differential
        from securevibebench_evaluation.harbor_native import write_config
        from securevibebench_evaluation.images import read_task
        task = Path(task)
        config = read_task(task)
        root = task / "tests"
        assets = root / "contract"
        if assets.exists():
            shutil.rmtree(assets)
        assets.mkdir()
        check = assets / "check.py"
        check.write_text("# Staging fixture; measurements below are synthetic test data.\n")
        spec = {
            "schema_version": 1, "policy": differential.POLICY, "task": task.name,
            "image_id": config["metadata"]["image"]["id"],
            "base_tree": "b" * 40, "reference_tree": "d" * 40,
            "reference_commit": config["metadata"]["vic"],
            "files_sha256": {"contract/check.py": differential.checksum(check)},
            "framework_sha256": {name: differential.checksum(functional.ASSETS / name) for name in differential.FRAMEWORK},
            "cases": [{"id": name, "command": ["/opt/svb/python/bin/python3", "/tests/contract/check.py"]}
                      for name in ["feature", "regression"]],
            "FAIL_TO_PASS": ["feature"], "PASS_TO_PASS": ["regression"],
        }
        proof = {}
        for phase in ["base", "reference"]:
            proof[phase + "_runs"] = [
                {"source_tree": spec[phase + "_tree"], "measurement_id": uuid.uuid4().hex,
                 "build_exit_code": 0, "completed": True,
                 "cases": {"feature": "FAIL" if phase == "base" else "PASS", "regression": "PASS"}}
                for _ in range(2)
            ]
        proof["suite_sha256"] = differential.suite_hash(spec)
        spec["qualification"] = proof
        (root / "functional.json").write_text(json.dumps(spec, indent=2) + "\n")
        config["metadata"]["reward_policy"] = differential.POLICY
        config["task"]["version"] = "3.0.0"
        write_config(task / "task.toml", config)
        functional.stage_verifier(task)
        functional.require_contract(task, config)
        return spec
    return prepare
