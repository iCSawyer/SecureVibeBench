"""Thin native Harbor generation wrapper with optional independent evaluation."""

import json
import os
import re
from pathlib import Path
import subprocess
import sys
from .harbor_native import HOSTS, summarize_job
from .images import acquire, read_task, stage_task


def authentication_environment(agent, auth, auth_file=None):
    """Select a billing/authentication mode without saving credential values."""
    env = os.environ.copy()
    if auth == "chatgpt":
        if agent != "codex":
            raise ValueError("ChatGPT subscription authentication is for Codex only")
        path = (auth_file or Path.home() / ".codex/auth.json").expanduser().resolve()
        credential = json.loads(path.read_text())
        if credential.get("auth_mode") != "chatgpt" or not credential.get(
            "tokens", {}
        ).get("access_token"):
            raise ValueError(
                "A local ChatGPT Codex login is required; run codex login first"
            )
        for name in [
            "OPENAI_API_KEY",
            "CODEX_API_KEY",
            "OPENAI_BASE_URL",
            "OPENAI_API_BASE",
            "CODEX_ACCESS_TOKEN",
        ]:
            env.pop(name, None)
        env["CODEX_AUTH_JSON_PATH"] = str(path)
        env["CODEX_FORCE_AUTH_JSON"] = "true"
    elif auth == "api":
        env.pop("CODEX_AUTH_JSON_PATH", None)
        env.pop("CODEX_FORCE_AUTH_JSON", None)
    else:
        raise ValueError("Unknown authentication mode")
    return env


def stage_tasks(tasks, destination, allow_hosts=()):
    for task in tasks:
        stage_task(task, destination / task.name, allow_hosts=allow_hosts)
    return [destination / task.name for task in tasks]


def generate(
    task,
    agent,
    model,
    output,
    auth=None,
    auth_file=None,
    jobs=1,
    base_url=None,
    api_key_name=None,
    api_format=None,
    local_only=False,
    agent_kwargs=None,
    agent_env=None,
    allow_hosts=(),
):
    from urllib.parse import urlsplit

    tasks = task if isinstance(task, list) else [task]
    provider = {"codex": "openai", "claude-code": "anthropic"}.get(agent)
    if provider and not model.startswith(provider + "/"):
        raise ValueError("Use the official provider prefix: " + provider + "/")
    auth = auth or ("chatgpt" if agent == "codex" else "api")
    runtime_env = authentication_environment(agent, auth, auth_file)
    runtime_env["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    allowed = set(HOSTS) | set(allow_hosts)
    for item in tasks:
        allowed.update(read_task(item)["agent"].get("allowed_hosts", []))
    if base_url and urlsplit(base_url).hostname not in allowed:
        raise ValueError(
            "Model endpoint is not in the task allowlist; pass generate --allow-model-host HOST"
        )
    for name in ["OPENAI_BASE_URL", "ANTHROPIC_BASE_URL"]:
        value = runtime_env.get(name)
        if value and urlsplit(value).hostname not in allowed:
            raise ValueError(name + " is outside the model API allowlist")
    output.mkdir(parents=True, exist_ok=False)
    acquire(tasks, output / "images", local_only=local_only, agent=agent)
    tasks = stage_tasks(tasks, output / "tasks", allow_hosts)
    config_path = output / "job-input.json"
    config_path.write_text(
        json.dumps(
            {"tasks": [{"path": str(item.resolve())} for item in tasks]}, indent=2
        )
        + "\n"
    )
    command = [
        str(Path(sys.executable).with_name("harbor")),
        "run",
        "-c",
        str(config_path),
        "-a",
        agent,
        "-m",
        model,
        "-n",
        str(jobs),
        "--disable-verification",
        "--ak",
        "disable_web_search=true",
        "--jobs-dir",
        str(output / "jobs"),
        "--job-name",
        "generation",
    ]
    for name in agent_env or []:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) or name not in runtime_env:
            raise ValueError(
                "Agent environment variable must name a set host variable: " + name
            )
        command += ["--ae", name + "=${" + name + "}"]
    for option in agent_kwargs or []:
        if "=" not in option:
            raise ValueError("Native agent options require KEY=VALUE")
        command += ["--ak", option]
    for flag, value in [
        ("--base-url", base_url),
        ("--api-key-name", api_key_name),
        ("--api-format", api_format),
    ]:
        if value:
            command += [flag, value]
    (output / "command.json").write_text(json.dumps(command, indent=2) + "\n")
    (output / "authentication.json").write_text(
        json.dumps(
            {
                "mode": auth,
                "agent": agent,
                "auth_file": runtime_env.get("CODEX_AUTH_JSON_PATH"),
                "api_key_forwarded": auth == "api",
            },
            indent=2,
        )
        + "\n"
    )
    with (output / "harbor.log").open("w") as log:
        result = subprocess.run(
            command, stdout=log, stderr=subprocess.STDOUT, env=runtime_env
        )
    from .redaction import redact_artifacts

    redacted = redact_artifacts(output, runtime_env)
    (output / "redaction.json").write_text(
        json.dumps({"files": redacted}, indent=2) + "\n"
    )
    records = summarize_job(output / "jobs/generation")
    expected = {
        read_task(task)["task"]["name"].rsplit("/", 1)[-1]
        for task in (task if isinstance(task, list) else [task])
    }
    actual = [str(record["task"]).rsplit("/", 1)[-1] for record in records]
    failed = (
        len(actual) != len(expected)
        or set(actual) != expected
        or any(record["exception_type"] for record in records)
    )
    code = result.returncode or int(failed)
    submission = output / "submission"
    packaging_error = None
    if code == 0:
        from .submissions import package_job

        try:
            package_job(output / "jobs/generation", submission)
        except (ValueError, OSError) as exc:
            packaging_error = str(exc)
            code = 1
    (output / "summary.json").write_text(
        json.dumps(
            {
                "harbor_exit_code": result.returncode,
                "generation_exit_code": code,
                "submission": str(submission) if code == 0 else None,
                "packaging_error": packaging_error,
                "results": records,
            },
            indent=2,
        )
        + "\n"
    )
    if code == 0:
        print("Submission:", submission, flush=True)
    return code
