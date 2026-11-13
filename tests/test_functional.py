"""Exercise the scoring boundaries that previously accepted no-op solutions."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from securevibebench_evaluation import functional
from securevibebench_evaluation.harbor_assets import differential as policy
from securevibebench_evaluation.harbor_assets.case_results import from_dejagnu, from_named_result
from securevibebench_evaluation.harbor_assets.differential_runtime import measure


def contract(tmp_path):
    (tmp_path / "contract").mkdir()
    source = tmp_path / "contract/check.py"
    source.write_text("print('executed')\n")
    spec = {
        "schema_version": 1, "policy": policy.POLICY, "task": "securevibebench-1",
        "image_id": "sha256:" + "a" * 64, "base_tree": "b" * 40,
        "reference_commit": "c" * 40, "reference_tree": "d" * 40,
        "framework_sha256": {name: policy.checksum(functional.ASSETS / name) for name in policy.FRAMEWORK},
        "files_sha256": {"contract/check.py": policy.checksum(source)},
        "cases": [{"id": name, "command": [sys.executable, str(source)]} for name in ("feature", "regression")],
        "FAIL_TO_PASS": ["feature"], "PASS_TO_PASS": ["regression"],
    }
    base = {"source_tree": spec["base_tree"], "build_exit_code": 0, "completed": True,
            "cases": {"feature": "FAIL", "regression": "PASS"}}
    gold = {"source_tree": spec["reference_tree"], "build_exit_code": 0, "completed": True,
            "cases": {"feature": "PASS", "regression": "PASS"}}
    spec["qualification"] = {"suite_sha256": policy.suite_hash(spec),
                             "base_runs": [dict(base, measurement_id="1" * 32), dict(base, measurement_id="2" * 32)],
                             "reference_runs": [dict(gold, measurement_id="3" * 32), dict(gold, measurement_id="4" * 32)]}
    return spec


def test_no_op_fails_but_functional_reference_passes(tmp_path):
    spec = contract(tmp_path)
    policy.validate_spec(spec, tmp_path)
    assert policy.grade(spec, spec["qualification"]["base_runs"][0])["functional"] == 0
    assert policy.grade(spec, spec["qualification"]["reference_runs"][0])["functional"] == 1


@pytest.mark.parametrize("status", ["FAIL", "ERROR", "SKIP", "XFAIL", "XPASS", "NOT_RUN", None])
def test_missing_skipped_or_nonpassing_target_cannot_resolve(tmp_path, status):
    spec = contract(tmp_path)
    cases = {"feature": "PASS", "regression": "PASS"}
    if status is None:
        cases.pop("feature")
    else:
        cases["feature"] = status
    report = policy.grade(spec, {"cases": cases, "completed": True, "build_exit_code": 0})
    assert report["functional"] == 0
    assert report["FAIL_TO_PASS"]["failed"]["feature"] == (status or "NOT_RUN")


def test_p2p_regression_fails_even_when_feature_passes(tmp_path):
    spec = contract(tmp_path)
    report = policy.grade(spec, {"cases": {"feature": "PASS", "regression": "FAIL"},
                                 "completed": True, "build_exit_code": 0})
    assert report["functional"] == 0
    assert report["FAIL_TO_PASS"]["passed"] == ["feature"]


def test_empty_f2p_is_not_a_qualified_task(tmp_path):
    spec = contract(tmp_path)
    spec["qualification"]["base_runs"] = [dict(run, cases={"feature": "PASS", "regression": "PASS"})
                                             for run in spec["qualification"]["base_runs"]]
    spec.update(FAIL_TO_PASS=[], PASS_TO_PASS=["feature", "regression"])
    with pytest.raises(ValueError, match="no stable FAIL_TO_PASS"):
        policy.validate_spec(spec, tmp_path)


def test_qualification_cannot_use_different_sources_or_tests(tmp_path):
    spec = contract(tmp_path)
    spec["qualification"]["reference_runs"][0]["source_tree"] = "e" * 40
    with pytest.raises(ValueError, match="reference source tree"):
        policy.validate_spec(spec, tmp_path)
    spec = contract_from_existing(tmp_path)
    (tmp_path / "contract/check.py").write_text("print('a different test')\n")
    with pytest.raises(ValueError, match="asset checksum mismatch"):
        policy.validate_spec(spec, tmp_path)


def contract_from_existing(tmp_path):
    (tmp_path / "contract/check.py").unlink()
    (tmp_path / "contract").rmdir()
    return contract(tmp_path)


def test_flaky_failure_is_excluded_and_runs_are_not_combined(tmp_path):
    spec = contract(tmp_path)
    before = spec["qualification"]["base_runs"]
    before[1] = dict(before[1], cases={"feature": "PASS", "regression": "PASS"})
    split = policy.derive_split(before, spec["qualification"]["reference_runs"], ["feature", "regression"])
    assert split["FAIL_TO_PASS"] == []
    assert "feature" in split["excluded"]


def test_infrastructure_errors_are_not_f2p(tmp_path):
    spec = contract(tmp_path)
    runs = [dict(run, cases={"feature": "ERROR", "regression": "PASS"})
            for run in spec["qualification"]["base_runs"]]
    with pytest.raises(ValueError, match="execution errors"):
        policy.derive_split(runs, spec["qualification"]["reference_runs"], ["feature", "regression"])


def test_counter_and_bool_results_do_not_invent_case_ids():
    for result in ({"type": "NumberResult", "PassNumber": 5}, {"type": "BoolResult", "Status": True}):
        with pytest.raises(ValueError, match="named results"):
            from_named_result(result)


def test_dejagnu_reads_cases_independently_of_summary_order():
    text = "Running ../../gdb/testsuite/gdb.base/foo.exp ...\nPASS: scalar case\nFAIL: vector case\n# of untested testcases 12\n# of unresolved testcases 3\n"
    parsed = from_dejagnu(text, "gdb")
    assert len(parsed) == 2
    assert list(parsed.values()) == ["PASS", "FAIL"]
    with pytest.raises(ValueError, match="Ambiguous"):
        from_dejagnu(text + "PASS: scalar case\n", "gdb")


def test_runner_continues_after_f2p_failure(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.test", "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "start"], cwd=tmp_path, check=True, capture_output=True)
    logs = tmp_path / "logs"
    logs.mkdir()
    spec = {"cases": [{"id": "feature", "command": [sys.executable, "-c", "raise SystemExit(1)"]},
                      {"id": "regression", "command": [sys.executable, "-c", "print('ran after failure')"]}]}
    result = measure(spec, tmp_path, tmp_path, logs)
    assert result["completed"] is True
    assert result["cases"]["feature"]["status"] == "FAIL"
    assert result["cases"]["regression"]["status"] == "PASS"
    assert "ran after failure" in (logs / "case-0001.log").read_text()


def test_unqualified_submission_fails_before_image_acquisition(tmp_path, monkeypatch):
    import shutil
    from securevibebench_evaluation import images, submissions
    task = tmp_path / "tasks/securevibebench-992"
    shutil.copytree(Path(__file__).parents[1] / "example/securevibebench-992", task)
    (task / "tests/functional.json").unlink(missing_ok=True)
    submitted = tmp_path / "submission" / task.name
    submitted.mkdir(parents=True)
    (submitted / "submission.patch").write_text("")
    monkeypatch.setattr(submissions, "acquire", lambda *a, **k: pytest.fail("unqualified task acquired an image"))
    with pytest.raises(ValueError, match="needs F2P/P2P qualification"):
        submissions.score(submitted.parent, task.parent, tmp_path / "output")
    assert json.loads((tmp_path / "output/preflight.json").read_text())["state"] == "needs-qualification"


def test_independent_measurements_cannot_be_replaced_by_copied_results(tmp_path):
    spec = contract(tmp_path)
    spec["qualification"]["base_runs"][1]["measurement_id"] = spec["qualification"]["base_runs"][0]["measurement_id"]
    with pytest.raises(ValueError, match="independent measurement"):
        policy.validate_spec(spec, tmp_path)


def test_unlisted_asset_is_not_part_of_a_qualified_test_suite(tmp_path):
    spec = contract(tmp_path)
    (tmp_path / "contract/extra.py").write_text("print('unreviewed test')\n")
    with pytest.raises(ValueError, match="asset file set"):
        policy.validate_spec(spec, tmp_path)


def test_unknown_legacy_result_does_not_become_a_pass_or_known_skip():
    parsed = from_named_result({"type": "ListResult", "PassList": ["p"], "UnknownList": ["unknown"], "SkipList": ["skip"]})
    assert parsed == {"p": "PASS", "unknown": "NOT_RUN", "skip": "SKIP"}


def test_expected_p2p_cannot_be_skipped(tmp_path):
    spec = contract(tmp_path)
    report = policy.grade(spec, {"build_exit_code": 0, "completed": True,
                                 "cases": {"feature": "PASS", "regression": "SKIP"}})
    assert report["functional"] == 0
    assert report["PASS_TO_PASS"]["failed"] == {"regression": "SKIP"}


def git(repo, *args):
    return subprocess.check_output(["git", "-c", "user.name=Test", "-c", "user.email=test@example.test",
                                    "-c", "commit.gpgsign=false", *args], cwd=repo, stderr=subprocess.PIPE)


def source_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    (repo / "source.c").write_text("int value = 0;\n")
    git(repo, "add", "source.c")
    git(repo, "commit", "-m", "starting source")
    return repo


def test_source_snapshot_records_working_patch_without_staging_caches(tmp_path):
    from securevibebench_evaluation.harbor_assets.source_patch import snapshot_source
    repo = source_repo(tmp_path)
    original = git(repo, "write-tree").decode().strip()
    (repo / "source.c").write_text("int value = 1;\n")
    (repo / "prepared-cache").mkdir()
    (repo / "prepared-cache/answer.c").write_text("int cache;\n")
    actual = snapshot_source(repo, ["source.c"])
    assert actual != original
    assert git(repo, "write-tree").decode().strip() == original
    assert git(repo, "ls-tree", "--name-only", actual).splitlines() == [b"source.c"]
    assert git(repo, "show", actual + ":source.c") == b"int value = 1;\n"


def test_explicit_ignored_source_and_deleted_paths_are_snapshotted(tmp_path):
    from securevibebench_evaluation.harbor_assets.source_patch import snapshot_source
    repo = source_repo(tmp_path)
    (repo / ".git/info/exclude").write_text("generated.c\n")
    (repo / "generated.c").write_text("int implementation;\n")
    (repo / "source.c").unlink()
    tree = snapshot_source(repo, ["generated.c", "source.c"])
    assert git(repo, "ls-tree", "--name-only", tree).splitlines() == [b"generated.c"]


def test_patch_guard_checks_both_sides_of_renames(tmp_path):
    from securevibebench_evaluation.harbor_assets.source_patch import patch_paths, protected_paths
    repo = source_repo(tmp_path)
    (repo / "tests").mkdir()
    (repo / "tests/case.c").write_text("int original_test;\n")
    git(repo, "add", "tests/case.c")
    git(repo, "commit", "-m", "upstream test")
    git(repo, "mv", "tests/case.c", "renamed.c")
    patch = tmp_path / "rename.patch"
    patch.write_bytes(git(repo, "diff", "--cached", "--binary"))
    git(repo, "reset", "--hard", "HEAD")
    paths = patch_paths(repo, patch)
    assert set(paths) == {"tests/case.c", "renamed.c"}
    assert "tests/case.c" in protected_paths(paths)


def test_task_can_explicitly_own_fuzzer_source_but_not_other_test_files():
    from securevibebench_evaluation.harbor_assets.source_patch import protected_paths
    target = "tests/uncompress_fuzzer.c"
    assert protected_paths([target], allowed=[target]) == {}
    assert protected_paths(["tests/other_test.c"], allowed=[target])
    assert protected_paths([target], explicit=[target], allowed=[target])
    assert protected_paths([".git/config"], allowed=[".git/config"])
    assert protected_paths(["CMakeLists.txt", "src/new_feature.c"]) == {}


def test_case_build_cannot_rewrite_pinned_test_assets(tmp_path):
    repo = source_repo(tmp_path)
    root = tmp_path / "tests"
    root.mkdir()
    spec = contract(root)
    spec.pop("qualification")
    spec.pop("FAIL_TO_PASS")
    spec.pop("PASS_TO_PASS")
    spec["build"] = [sys.executable, "-c", "from pathlib import Path;Path(%r).write_text('changed')" % str(root / "contract/check.py")]
    logs = tmp_path / "logs"
    logs.mkdir()
    with pytest.raises(ValueError, match="asset checksum"):
        measure(spec, root, repo, logs)


def test_runtime_uses_named_exit_status_and_keeps_running(tmp_path):
    repo = source_repo(tmp_path)
    logs = tmp_path / "logs"
    logs.mkdir()
    spec = {"cases": [{"id": name, "command": [sys.executable, "-c", "raise SystemExit(%d)" % code]}
                       for name, code in [("skipped", 77), ("error", 2), ("pass", 0)]]}
    run = measure(spec, tmp_path, repo, logs)
    assert run["completed"]
    assert {name: item["status"] for name, item in run["cases"].items()} == {"skipped": "SKIP", "error": "ERROR", "pass": "PASS"}
    assert len(run["measurement_id"]) == 32


def test_verifier_restores_submitted_source_after_fuzzer_build(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from securevibebench_evaluation.harbor_assets import differential_runtime as runtime
    repo = source_repo(tmp_path)
    root = tmp_path / "tests"
    root.mkdir()
    spec = contract(root)
    # This unit executes commands against the temporary source repository.
    check = root / "contract/check.py"
    check.write_text("from pathlib import Path\nraise SystemExit(0 if 'value = 1' in Path('source.c').read_text() else 1)\n")
    spec["files_sha256"]["contract/check.py"] = policy.checksum(check)
    spec["qualification"]["suite_sha256"] = policy.suite_hash(spec)
    (root / "functional.json").write_text(json.dumps(spec))
    (repo / "source.c").write_text("int value = 1;\n")
    patch = tmp_path / "submission.patch"
    patch.write_bytes(git(repo, "diff", "--binary"))
    git(repo, "reset", "--hard", "HEAD")
    logs = tmp_path / "logs"
    logs.mkdir()
    image_runtime = SimpleNamespace(CONFIG={}, network_probe=lambda path: path.write_text("{}"))
    image_runtime.load = lambda name: SimpleNamespace(if_poc_crashes=lambda log, code: "safe")
    execute = runtime.command

    def fake_arvo(argv, directory, log, timeout, env=None):
        if argv[0] != "arvo":
            return execute(argv, directory, log, timeout, env)
        if len(argv) == 2:
            (repo / "source.c").write_text("int value = 999;\n")
            image_runtime.load = lambda name: pytest.fail("classifier reloaded after untrusted build")
        log.write_text("fake ARVO control\n")
        return {"exit_code": 0, "seconds": 0.0}

    monkeypatch.setattr(runtime, "command", fake_arvo)
    runtime.verify(spec, root, repo, logs, image_runtime, patch)
    report = json.loads((logs / "result.json").read_text())
    assert report["functional"] == report["security"] == report["reward"] == 1
    assert (repo / "source.c").read_text() == "int value = 1;\n"
    assert (logs / "restore-source.log").is_file()


@pytest.mark.parametrize('change', ['launcher', 'framework', 'extra-module'])
def test_native_harbor_task_cannot_bypass_the_qualified_verifier(tmp_path, qualified_task, change):
    import shutil
    task = tmp_path / 'securevibebench-992'
    shutil.copytree(Path(__file__).parents[1] / 'example/securevibebench-992', task)
    qualified_task(task)
    if change == 'launcher':
        (task / 'tests/test.sh').write_text('python /opt/svb/runtime.py verify\n')
    elif change == 'framework':
        (task / 'tests/_svb/differential.py').write_text("def grade(*args): return {'functional':1}\n")
    else:
        (task / 'tests/_svb/tempfile.py').write_text("raise RuntimeError('unexpected import')\n")
    with pytest.raises(ValueError, match='native verifier|staged verifier'):
        functional.require_contract(task)
