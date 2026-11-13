"""Exercise resumable test authoring without real models or Docker."""

import json
from pathlib import Path
import shutil
import signal
import subprocess
from types import SimpleNamespace
import uuid

import pytest

from tools.functional import authoring, batch, sources
from tools.functional import qualify as qualification
from securevibebench_evaluation.images import read_task


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def author_result():
    return {"status": "ready", "summary": "Behavior assertions", "reason": "", "context_paths": []}


def review_result(level="behavior"):
    return {"approved": True, "reason": "Exercises candidate code", "test_level": level, "missing_coverage": []}


def draft(root):
    root.mkdir(parents=True, exist_ok=True)
    write(root / "spec.json", {
        "reference_tree": "d" * 40,
        "cases": [{"id": name, "command": ["bash", "/tests/contract/check.sh", name]}
                  for name in ["feature", "regression"]],
    })
    (root / "check.sh").write_text("#!/bin/bash\nexit 0\n")


@pytest.fixture
def codex_stub(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-value-that-must-not-be-used")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://unused-endpoint.example.test")
    monkeypatch.setenv("CUSTOM_ACCESS_TOKEN", "test-token-value-that-must-not-be-used")
    login = {"text": "Logged in using ChatGPT", "code": 0}
    response = {"code": 0, "events": '{"type":"thread.started"}\n', "stderr": "", "timeout": False}

    def status(command, **kwargs):
        calls.append(("login", command, kwargs))
        assert command == ["codex", "login", "status"]
        return SimpleNamespace(returncode=login["code"], stdout=login["text"], stderr="")

    class Process:
        pid = 100001

        def __init__(self, command, **kwargs):
            self.command, self.kwargs = command, kwargs
            self.returncode = response["code"]
            self.timed_out = False
            calls.append(("exec", command, kwargs))

        def communicate(self, prompt=None, timeout=None):
            if response["timeout"] and not self.timed_out:
                self.timed_out = True
                raise subprocess.TimeoutExpired(self.command, timeout)
            self.kwargs["stdout"].write(response["events"])
            self.kwargs["stderr"].write(response["stderr"])
            if response["code"] == 0 and not response["timeout"] and response.get("save_result", True):
                output = Path(self.command[self.command.index("--output-last-message") + 1])
                readonly = self.command[self.command.index("--sandbox") + 1] == "read-only"
                write(output, review_result() if readonly else author_result())
            return None, None

    monkeypatch.setattr(authoring.subprocess, "run", status)
    monkeypatch.setattr(authoring.subprocess, "Popen", Process)
    return calls, login, response


@pytest.mark.parametrize("review", [False, True])
def test_codex_uses_subscription_and_records_each_isolated_session(tmp_path, codex_stub, review):
    calls, _, _ = codex_stub
    job = tmp_path / "workspace"
    job.mkdir()
    result = authoring.run_codex(job, tmp_path / "session", review=review)
    executions = [(command, kwargs) for kind, command, kwargs in calls if kind == "exec"]
    assert len(executions) == 1
    command, kwargs = executions[0]
    assert "--ignore-user-config" in command and "resume" not in command
    assert command[command.index("--sandbox") + 1] == ("read-only" if review else "workspace-write")
    assert 'web_search="disabled"' in command and 'approval_policy="never"' in command
    assert kwargs["start_new_session"] is True
    assert kwargs["env"]["CODEX_HOME"] == str(tmp_path / "codex-home")
    for _, _, options in calls:
        environment = options.get("env", {})
        assert "OPENAI_API_KEY" not in environment
        assert "OPENAI_BASE_URL" not in environment
        assert "CUSTOM_ACCESS_TOKEN" not in environment
    assert any(kind == "login" for kind, _, _ in calls)
    assert (tmp_path / "session/trajectory.jsonl").read_text() == '{"type":"thread.started"}\n'
    assert json.loads((tmp_path / "session/process.json").read_text())["exit_code"] == 0
    assert result == (review_result() if review else author_result())


@pytest.mark.parametrize("login_text", ["Logged in using an API key", "Not logged in"])
def test_api_or_missing_login_never_starts_an_author(tmp_path, codex_stub, login_text):
    calls, login, _ = codex_stub
    login["text"] = login_text
    job = tmp_path / "workspace"
    job.mkdir()
    with pytest.raises((ValueError, RuntimeError), match="ChatGPT|subscription|login|auth"):
        authoring.run_codex(job, tmp_path / "session")
    assert not any(kind == "exec" for kind, _, _ in calls)


def test_quota_failure_is_retryable_and_keeps_trajectory(tmp_path, codex_stub):
    _, _, response = codex_stub
    response.update(code=1, events='{"type":"error","message":"usage_limit_reached"}\n')
    job = tmp_path / "workspace"
    job.mkdir()
    with pytest.raises(authoring.QuotaWait):
        authoring.run_codex(job, tmp_path / "session")
    assert "usage_limit_reached" in (tmp_path / "session/trajectory.jsonl").read_text()
    assert json.loads((tmp_path / "session/process.json").read_text())["exit_code"] == 1


def test_error_about_quota_source_is_not_an_account_limit(tmp_path, codex_stub):
    _, _, response = codex_stub
    response.update(code=1, stderr="Could not spawn the compiler for quota.c")
    job = tmp_path / "workspace"
    job.mkdir()
    with pytest.raises(RuntimeError) as error:
        authoring.run_codex(job, tmp_path / "session")
    assert not isinstance(error.value, authoring.QuotaWait)


def test_zero_exit_quota_event_without_final_result_still_waits(tmp_path, codex_stub):
    _, _, response = codex_stub
    response.update(code=0, events='{"type":"error","message":"usage_limit_reached"}\n', save_result=False)
    job = tmp_path / "workspace"
    job.mkdir()
    with pytest.raises(authoring.QuotaWait):
        authoring.run_codex(job, tmp_path / "session")


def test_timed_out_session_kills_its_process_group(tmp_path, codex_stub, monkeypatch):
    _, _, response = codex_stub
    response.update(timeout=True)
    killed = []
    monkeypatch.setattr(authoring.os, "killpg", lambda pid, sig: killed.append((pid, sig)))
    job = tmp_path / "workspace"
    job.mkdir()
    with pytest.raises(RuntimeError, match="124"):
        authoring.run_codex(job, tmp_path / "session", timeout=1)
    assert killed == [(100001, signal.SIGKILL)]
    assert json.loads((tmp_path / "session/process.json").read_text())["exit_code"] == 124


class Clock:
    def __init__(self):
        self.value = 1000.0
        self.waits = []

    def time(self):
        return self.value

    def time_ns(self):
        return int(self.value * 1_000_000_000)

    def sleep(self, seconds):
        assert seconds >= 0
        self.waits.append(seconds)
        self.value += seconds


@pytest.fixture
def batch_job(tmp_path, monkeypatch):
    root = tmp_path / "run"
    source = tmp_path / "sources/992"
    context = {"task": "992", "repo": "/src/file", "reference": "reference",
               "reference_tree": "d" * 40, "prepared_image": "sha256:" + "a" * 64,
               "parent_image": "sha256:" + "e" * 64}
    write(source / "context.json", context)
    write(source / "sources.json", {"diff": "production change\n",
                                    "files": {"base:src/feature.c": "int old;\n", "reference:src/feature.c": "int new;\n"},
                                    "headers": {"src/feature.h": "int public_api(void);\n"}})
    (source / "instruction.md").write_text("Implement the requested feature.\n")
    args = SimpleNamespace(output=root, sources=source.parent, tasks=tmp_path / "tasks",
                           framework_ready=tmp_path / "ready.json", workers=1, ids=["992"],
                           attempts=1, author_timeout=60, quota_retry=30)
    write(args.framework_ready, {"state": "ready"})
    clock = Clock()
    monkeypatch.setattr(batch, "time", clock)
    monkeypatch.setattr(batch.Batch, "wait_for_framework", lambda self, identifier: None)
    return args, source, context, clock


def fake_qualification(task, contract, patch, output, **kwargs):
    output.mkdir(parents=True)
    report = {"task": task.name, "state": "qualified", "task_path": str(output / "tasks" / task.name),
              "f2p": ["feature"], "p2p": ["regression"]}
    write(output / "qualification.json", report)
    return report


def test_workspace_preserves_both_revisions_and_header_context(tmp_path, batch_job):
    _, source, _, _ = batch_job
    target = tmp_path / "workspace"
    batch.workspace(source, target)
    assert (target / "context/base/src/feature.c").read_text() == "int old;\n"
    assert (target / "context/reference/src/feature.c").read_text() == "int new;\n"
    assert (target / "context/headers/src/feature.h").read_text() == "int public_api(void);\n"
    assert (target / "instruction.md").read_text() == (source / "instruction.md").read_text()


@pytest.mark.parametrize("name", ["../outside.c", "/etc/passwd", "src/../../outside.c", ".git/config"])
def test_requested_context_stays_within_the_repository(name):
    with pytest.raises(ValueError, match="Unsafe"):
        batch.checked_path(name)


def test_generated_contract_cannot_choose_image_or_reference_identity(tmp_path):
    contract = tmp_path / "contract"
    draft(contract)
    spec = json.loads((contract / "spec.json").read_text())
    spec.update(qualification={"forged": True}, FAIL_TO_PASS=["invented"], PASS_TO_PASS=[],
                image_id="forged", base_tree="forged", reference_tree="forged", policy="forged")
    write(contract / "spec.json", spec)
    actual = batch.contract_draft(contract, {"reference_tree": "d" * 40})
    assert actual["reference_tree"] == "d" * 40
    assert not ({"qualification", "FAIL_TO_PASS", "PASS_TO_PASS", "image_id", "base_tree", "policy"} & actual.keys())


@pytest.mark.parametrize("marker", ["/reference.patch", "/context/base/source.c", "sources.json", "git rev-parse"])
def test_contract_cannot_measure_source_identity_instead_of_behavior(tmp_path, marker):
    contract = tmp_path / "contract"
    draft(contract)
    (contract / "check.sh").write_text(marker)
    with pytest.raises(ValueError, match="snapshots or identities"):
        batch.contract_draft(contract, {"reference_tree": "d" * 40})


def test_restart_reuses_a_completed_author_result(tmp_path, batch_job, monkeypatch):
    args, source, _, _ = batch_job
    job = args.output / "tasks/992/workspace"
    batch.workspace(source, job)
    draft(job / "contract")
    attempt = args.output / "tasks/992/attempts/01"
    write(attempt / "author/result.json", author_result())
    write(attempt / "author/process.json", {"exit_code": 0})
    called = []

    def codex(workspace, output, *, review=False, **kwargs):
        assert review, "A completed author must not be called again"
        called.append("review")
        output.mkdir(parents=True)
        write(output / "result.json", review_result())
        return review_result()

    monkeypatch.setattr(batch, "run_codex", codex)
    monkeypatch.setattr(batch, "qualify", fake_qualification)
    controller = batch.Batch(args)
    controller.one("992")
    assert called == ["review"]
    assert controller.tasks["992"]["state"] == "qualified"


def test_review_quota_retries_the_review_without_reauthoring(batch_job, monkeypatch):
    args, _, _, clock = batch_job
    calls = []

    def codex(job, output, *, review=False, **kwargs):
        output.mkdir(parents=True)
        if not review:
            calls.append("author")
            draft(job / "contract")
            write(output / "result.json", author_result())
            return author_result()
        calls.append("review")
        if calls.count("review") == 1:
            raise authoring.QuotaWait("usage_limit_reached")
        write(output / "result.json", review_result())
        return review_result()

    monkeypatch.setattr(batch, "run_codex", codex)
    monkeypatch.setattr(batch, "qualify", fake_qualification)
    controller = batch.Batch(args)
    controller.one("992")
    assert calls == ["author", "review", "review"]
    assert controller.tasks["992"]["state"] == "qualified"
    assert sum(clock.waits) >= args.quota_retry


def test_restart_retains_the_shared_quota_deadline(batch_job):
    args, _, _, clock = batch_job
    write(args.output / "progress.json", {"tasks": {"992": {"state": "quota-wait", "retry_at": 1050.0}}})
    controller = batch.Batch(args)
    assert controller.quota_until >= 1050.0
    controller.wait_for_quota("992")
    assert clock.time() >= 1050.0
    assert sum(clock.waits) == 50.0


@pytest.mark.parametrize("target", ["instruction.md", "context.json", "context/base/src/feature.c"])
def test_author_cannot_rewrite_the_inputs_seen_by_independent_review(batch_job, monkeypatch, target):
    args, _, _, _ = batch_job
    reviews = []
    original = {}

    def codex(job, output, *, review=False, **kwargs):
        output.mkdir(parents=True)
        if not review:
            original[target] = (job / target).read_bytes()
            (job / target).write_text("author-rewritten input")
            draft(job / "contract")
            write(output / "result.json", author_result())
            return author_result()
        reviews.append(True)
        return review_result()

    monkeypatch.setattr(batch, "run_codex", codex)
    monkeypatch.setattr(batch, "qualify", fake_qualification)
    controller = batch.Batch(args)
    controller.one("992")
    assert not reviews, "A changed requirement/source snapshot must be rejected before independent review"
    assert controller.tasks["992"]["state"] != "qualified"
    assert (args.output / "tasks/992/workspace" / target).read_bytes() == original[target]


def test_invalid_review_level_cannot_be_signed_as_qualified(batch_job, monkeypatch):
    args, _, _, _ = batch_job

    def codex(job, output, *, review=False, **kwargs):
        output.mkdir(parents=True)
        if review:
            return review_result("invalid")
        draft(job / "contract")
        return author_result()

    monkeypatch.setattr(batch, "run_codex", codex)
    monkeypatch.setattr(batch, "qualify", fake_qualification)
    controller = batch.Batch(args)
    controller.one("992")
    assert controller.tasks["992"]["state"] != "qualified"


def test_prepared_reference_tree_comes_from_actual_image_index(tmp_path, monkeypatch):
    root = tmp_path / "runs/implementation/batch-sources"
    task = tmp_path / "tasks/securevibebench-992"
    shutil.copytree(Path(__file__).parents[1] / "example/securevibebench-992", task)
    (task / "instruction.md").write_text("Published instruction")
    row = {"task": "992", "project": "file", "original_base_commit": "base^",
           "reference_commit": "reference", "image": {"id": read_task(task)["metadata"]["image"]["id"]}}
    commands = []

    def probe(command, folder, name):
        commands.append(command)
        if name == "source":
            return {"diff": "reference diff\n", "changed_files": ["src/feature.c"],
                    "files": {}, "headers": {}, "reference_original_tree": "c" * 40}
        return {"base_tree": "b" * 40, "reference_tree": "d" * 40}

    monkeypatch.setattr(sources, "run", probe)
    context = sources.prepare(row, "foundation-image", task, root)
    assert context["reference_tree"] == "d" * 40
    assert context["original_reference_tree"] == "c" * 40
    assert commands[0][commands[0].index("--entrypoint") + 2] == "foundation-image"
    assert row["image"]["id"] in commands[1]
    assert all(command[command.index("--network") + 1] == "none" for command in commands)
    assert all("--pull=never" in command for command in commands)


@pytest.fixture
def qualification_input(tmp_path):
    task = tmp_path / "tasks/securevibebench-992"
    shutil.copytree(Path(__file__).parents[1] / "example/securevibebench-992", task)
    shutil.rmtree(task / "tests/contract", ignore_errors=True)
    (task / "tests/functional.json").unlink(missing_ok=True)
    contract = tmp_path / "contract"
    draft(contract)
    patch = tmp_path / "reference.patch"
    patch.write_text("reference change")
    return task, contract, patch


def mock_qualification(monkeypatch):
    from securevibebench_evaluation.images import read_task
    commands = []

    def inspect(identifier):
        return {"Id": identifier, "Os": "linux", "Architecture": "amd64"}

    def output(command, **kwargs):
        assert command[0] == "docker"
        commands.append(command)
        return "b" * 40 + "\n"

    def run(command, **kwargs):
        assert command[0] == "docker"
        commands.append(command)
        volumes = [command[i + 1] for i, token in enumerate(command) if token == "-v"]
        logs = next(Path(value.rsplit(":/logs/verifier", 1)[0]) for value in volumes if value.endswith(":/logs/verifier"))
        reference = "--reference-patch" in command
        result = {"build_exit_code": 0, "completed": True, "measurement_id": uuid.uuid4().hex,
                  "source_tree": ("d" if reference else "b") * 40,
                  "cases": {"feature": "PASS" if reference else "FAIL", "regression": "PASS"}}
        write(logs / "measure.json", result)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(qualification, "inspect_image", inspect)
    monkeypatch.setattr(qualification.subprocess, "check_output", output)
    monkeypatch.setattr(qualification.subprocess, "run", run)
    return commands


def test_qualification_uses_four_fresh_offline_runs_and_hides_reference_from_base(tmp_path, qualification_input, monkeypatch):
    from securevibebench_evaluation.functional import require_contract
    task, contract, patch = qualification_input
    commands = mock_qualification(monkeypatch)
    report = qualification.qualify(task, contract, patch, tmp_path / "qualified")
    spec = require_contract(Path(report["task_path"]))
    assert spec["FAIL_TO_PASS"] == ["feature"]
    assert spec["PASS_TO_PASS"] == ["regression"]
    measurements = [command for command in commands if "measure" in command]
    assert len(measurements) == 4
    assert len({command[command.index("--name") + 1] for command in measurements}) == 4
    for command in measurements:
        assert command[command.index("--network") + 1] == "none" and "--pull=never" in command
        reference_volumes = [value for value in command if value.endswith(":/reference.patch:ro")]
        assert bool(reference_volumes) == ("--reference-patch" in command)
    runs = spec["qualification"]["base_runs"] + spec["qualification"]["reference_runs"]
    assert len({run["measurement_id"] for run in runs}) == 4


@pytest.mark.parametrize("writer", [sources.write_json, authoring.write_json])
def test_json_readers_never_observe_a_truncated_status_file(tmp_path, monkeypatch, writer):
    path = tmp_path / "state.json"
    write(path, {"state": "before"})
    observed = []
    original = Path.open

    def opening(self, mode="r", *args, **kwargs):
        stream = original(self, mode, *args, **kwargs)
        if "w" in mode:
            with original(path) as reader:
                try:
                    observed.append(json.load(reader))
                except ValueError:
                    observed.append("partial JSON")
        return stream

    monkeypatch.setattr(Path, "open", opening)
    writer(path, {"state": "after"})
    assert "partial JSON" not in observed
    assert json.loads(path.read_text()) == {"state": "after"}


def test_failed_author_still_restores_original_inputs(batch_job, monkeypatch):
    args, _, _, _ = batch_job
    original = {}

    def codex(job, output, **kwargs):
        output.mkdir(parents=True)
        original["instruction"] = (job / "instruction.md").read_text()
        (job / "instruction.md").write_text("rewritten before a transport failure")
        raise RuntimeError("Model transport failed after writing partial output")

    monkeypatch.setattr(batch, "run_codex", codex)
    monkeypatch.setattr(batch, "qualify", lambda *a, **k: pytest.fail("Failed author reached qualification"))
    controller = batch.Batch(args)
    controller.one("992")
    assert controller.tasks["992"]["state"] != "qualified"
    assert (args.output / "tasks/992/workspace/instruction.md").read_text() == original["instruction"]


def test_cached_review_cannot_authorize_different_contract_bytes(batch_job, monkeypatch):
    args, source, _, _ = batch_job
    job = args.output / "tasks/992/workspace"
    batch.workspace(source, job)
    draft(job / "contract")
    attempt = args.output / "tasks/992/attempts/01"
    write(attempt / "author/result.json", author_result())
    write(attempt / "author/process.json", {"exit_code": 0})
    shutil.copytree(job / "contract", attempt / "authored-contract")
    write(attempt / "review/result.json", review_result())
    write(attempt / "review/process.json", {"exit_code": 0})
    reviewed = [(job / "contract/check.sh").read_text()]
    (job / "contract/check.sh").write_text("#!/bin/bash\necho 'different assertions'\nexit 0\n")
    qualified = []

    def codex(workspace, output, *, review=False, **kwargs):
        assert review
        reviewed.append((workspace / "contract/check.sh").read_text())
        output.mkdir(parents=True)
        write(output / "result.json", review_result())
        write(output / "process.json", {"exit_code": 0})
        return review_result()

    def qualify(task, contract, patch, output, **kwargs):
        qualified.append((contract / "check.sh").read_text())
        return fake_qualification(task, contract, patch, output, **kwargs)

    monkeypatch.setattr(batch, "run_codex", codex)
    monkeypatch.setattr(batch, "qualify", qualify)
    controller = batch.Batch(args)
    controller.one("992")
    assert qualified, "Recovery should review or restore the approved contract and finish"
    assert qualified[-1] in reviewed


@pytest.fixture
def source_preparation(tmp_path, qualification_input, monkeypatch):
    task, _, _ = qualification_input
    root = tmp_path / "arbitrary-audit-location/batch-sources"
    row = {"task": "992", "project": "file", "original_base_commit": "base^",
           "reference_commit": "reference", "image": {"id": read_task(task)["metadata"]["image"]["id"]}}
    calls = []

    def probe(command, folder, name):
        calls.append(command)
        if name == "source":
            return {"diff": "reference change\n", "changed_files": ["src/feature.c"],
                    "files": {}, "headers": {}, "reference_original_tree": "c" * 40}
        return {"base_tree": "b" * 40, "reference_tree": "d" * 40}

    monkeypatch.setattr(sources, "run", probe)
    return task, root, row, calls


def test_source_cache_is_bound_to_the_prepared_image(source_preparation):
    task, root, row, calls = source_preparation
    sources.prepare(row, "foundation", task, root)
    replacement = {**row, "image": {"id": "sha256:" + "e" * 64}}
    from securevibebench_evaluation.images import read_task
    from securevibebench_evaluation.harbor_native import write_config
    config = read_task(task)
    config["metadata"]["image"]["id"] = replacement["image"]["id"]
    write_config(task / "task.toml", config)
    context = sources.prepare(replacement, "foundation", task, root)
    assert context["prepared_image"] == replacement["image"]["id"]
    assert len(calls) == 4


def test_ready_context_is_published_after_the_instruction(source_preparation, monkeypatch):
    task, root, row, _ = source_preparation
    writer = sources.write_json

    def observe(path, value):
        if path.name == "context.json":
            assert (path.parent / "instruction.md").is_file(), "A reader must not see ready context before its inputs exist"
        writer(path, value)

    monkeypatch.setattr(sources, "write_json", observe)
    sources.prepare(row, "foundation", task, root)


def test_partial_source_cache_is_repaired_on_resume(source_preparation):
    task, root, row, _ = source_preparation
    sources.prepare(row, "foundation", task, root)
    (root / "992/instruction.md").unlink()
    sources.prepare(row, "foundation", task, root)
    assert (root / "992/instruction.md").is_file()


def test_source_probe_timeout_cleans_its_named_container(tmp_path, monkeypatch):
    command = ["docker", "run", "--name", "junkai-context-test", "source-image"]
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        if argv[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        assert argv == ["docker", "rm", "-f", "junkai-context-test"]
        return SimpleNamespace(returncode=0, stdout="removed\n", stderr="")

    monkeypatch.setattr(sources.subprocess, "run", run)
    with pytest.raises(subprocess.TimeoutExpired):
        sources.run(command, tmp_path, "source")
    assert len(calls) == 2
    assert (tmp_path / "source-exit.txt").read_text().strip() == "124"
    assert (tmp_path / "source-timeout-cleanup.log").read_text() == "removed\n"


def test_qualification_can_replace_old_test_assets_in_its_staged_copy(tmp_path, qualification_input, monkeypatch):
    task, contract, patch = qualification_input
    old = task / "tests/contract/old-check.c"
    old.parent.mkdir()
    old.write_text("old test source\n")
    mock_qualification(monkeypatch)
    report = qualification.qualify(task, contract, patch, tmp_path / "qualified")
    assert old.read_text() == "old test source\n"
    assert not (Path(report["task_path"]) / "tests/contract/old-check.c").exists()


def test_qualification_timeout_cleans_container_and_records_failure(tmp_path, qualification_input, monkeypatch):
    task, contract, patch = qualification_input
    mock_qualification(monkeypatch)
    cleaned = []

    def run(command, **kwargs):
        if command[:2] == ["docker", "rm"]:
            cleaned.append(command[-1])
            return SimpleNamespace(returncode=0, stdout="removed\n", stderr="")
        raise subprocess.TimeoutExpired(command, 1)

    monkeypatch.setattr(qualification.subprocess, "run", run)
    output = tmp_path / "qualified"
    with pytest.raises((subprocess.TimeoutExpired, RuntimeError)):
        qualification.qualify(task, contract, patch, output)
    assert cleaned == ["junkai-f2p-securevibebench-992-base-0"]
    assert (output / "evidence/base-0/container.exit").read_text().strip() == "124"
