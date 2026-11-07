"""Runtime tasks can be exported only from accepted Public images."""

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from securevibebench_evaluation.images import read_task


@pytest.fixture
def producer(tmp_path):
    run = tmp_path / "run"
    task = run / "tasks/992"
    source = task / "bundle/tasks/securevibebench-992"
    shutil.copytree(Path(__file__).parents[1] / "example/securevibebench-992", source)
    image = read_task(source)["metadata"]["image"]
    (run / "selection.json").write_text('{"selected":["992"]}')
    (task / "work").mkdir()
    baseline = task / "work/baseline.json"
    baseline.write_text('{"Status":true}')
    for name, value in {
        "native-install/result.json": {"agent_info": {"version": "1.0"}},
        "gold/source.json": {"commit": "reference"},
        "start/source.json": {"commit": "starting"},
    }.items():
        path = task / "bundle/evidence" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
    state = {
        "state": "completed",
        "frozen_image": image["id"],
        "base_image": "base",
        "base_image_id": image["id"],
        "offline_gold_baseline_sha256": hashlib.sha256(
            baseline.read_bytes()
        ).hexdigest(),
        "verification": {"native_setup_offline": True},
        "image_audit": {"credentials_present": False},
        "toolchain": {},
        "registry": {
            "digest_reference": image["reference"],
            "visibility": "public",
            "anonymous_pull_verified": True,
        },
    }
    (task / "status.json").write_text(json.dumps(state))
    spec = importlib.util.spec_from_file_location(
        "public_catalog", Path(__file__).parents[1] / "tools/arvo_images/catalog.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, run, tmp_path / "catalog", task, state


def test_export_keeps_the_task_contract_and_public_evidence(producer):
    module, run, output, task, state = producer
    module.export_run(run, output)
    contract = read_task(output / "securevibebench-992")
    catalog = json.loads((output / "image-catalog.json").read_text())
    assert catalog["task_count"] == 1
    assert (
        catalog["images"][0]["reference"] == contract["metadata"]["image"]["reference"]
    )
    assert catalog["images"][0]["visibility"] == "public"
    assert catalog["images"][0]["registry"]["anonymous_pull_verified"]
    assert not list(output.rglob("Dockerfile"))


def test_private_image_is_rejected_before_writing_tasks(producer):
    module, run, output, task, state = producer
    state["registry"]["visibility"] = "private"
    (task / "status.json").write_text(json.dumps(state))
    with pytest.raises(ValueError, match="Public image acceptance"):
        module.export_run(run, output)
    assert not output.exists()


def test_changed_reference_baseline_blocks_export(producer):
    module, run, output, task, state = producer
    (task / "work/baseline.json").write_text('{"Status":false}')
    with pytest.raises(ValueError, match="checksum mismatch"):
        module.export_run(run, output)
    assert not output.exists()
