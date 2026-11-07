"""A registry rename must preserve task content, image identity and manifests."""

from pathlib import Path
import shutil

import pytest

from securevibebench_evaluation.images import read_task
from tools.image_build.references import retarget


def inputs(tmp_path):
    task = tmp_path / "securevibebench-992"
    shutil.copytree(Path(__file__).parents[1] / "example/securevibebench-992", task)
    image = dict(read_task(task)["metadata"]["image"], task="992")
    reference = (
        "ghcr.io/icsawyer/securevibebench@" + image["reference"].split("@", 1)[1]
    )
    row = {
        "task": "992",
        "image_id": image["id"],
        "reference": reference,
        "tag": "ghcr.io/icsawyer/securevibebench:arvo-992-test",
        "anonymous_pull_verified": True,
        "manifest_preserved": True,
    }
    return task, {"images": [image]}, {"images": [row]}


def test_retarget_keeps_image_and_task_behavior(tmp_path):
    task, catalog, mapping = inputs(tmp_path)
    before = read_task(task)
    content = {
        name: (task / name).read_bytes() for name in ["instruction.md", "tests/test.sh"]
    }
    retarget(tmp_path, catalog, mapping)
    after = read_task(task)
    assert after["metadata"]["image"]["id"] == before["metadata"]["image"]["id"]
    assert after["agent"] == before["agent"] and after["verifier"] == before["verifier"]
    assert after["environment"]["docker_image"] == mapping["images"][0]["reference"]
    assert all((task / name).read_bytes() == data for name, data in content.items())


def test_wrong_digest_blocks_all_contract_writes(tmp_path):
    task, catalog, mapping = inputs(tmp_path)
    before = (task / "task.toml").read_bytes()
    mapping["images"][0]["reference"] = (
        "ghcr.io/icsawyer/securevibebench@sha256:" + "a" * 64
    )
    with pytest.raises(ValueError, match="manifest digest"):
        retarget(tmp_path, catalog, mapping)
    assert (task / "task.toml").read_bytes() == before


def test_unverified_target_cannot_become_a_runtime_contract(tmp_path):
    task, catalog, mapping = inputs(tmp_path)
    mapping["images"][0]["anonymous_pull_verified"] = False
    with pytest.raises(ValueError, match="anonymous acceptance"):
        retarget(tmp_path, catalog, mapping)
