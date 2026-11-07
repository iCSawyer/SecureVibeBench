"""Run online preparation, then independent offline reference and start checks."""

import argparse
import json
from pathlib import Path
import subprocess
import shutil
import sys

sys.path.insert(0, "/opt/svb")
import runtime

phase = argparse.ArgumentParser()
phase.add_argument("phase", choices=["online", "gold", "start", "probe"])
args = phase.parse_args()
metadata = json.loads(Path("/opt/svb/image-metadata.json").read_text())
logs = Path("/opt/svb/preparation")
logs.mkdir(exist_ok=True)


def git(*values):
    return subprocess.check_output(
        ["git", *values], cwd=runtime.REPO, text=True
    ).strip()


if args.phase == "online":
    # Keep history only in the private preparation stage, for offline gold checkout.
    runtime.reset_repository_history = lambda *values: None
    runtime.prepare()
else:
    runtime.network_probe(logs / "network.json")
    if args.phase in ("gold", "start"):
        commit = metadata["vic"] if args.phase == "gold" else metadata["base_commit"]
        runtime.command(["git", "reset", "--hard", commit], logs / "checkout.log")
        (logs / "source.json").write_text(
            json.dumps(
                {
                    "commit": git("rev-parse", "HEAD"),
                    "tree": git("rev-parse", "HEAD^{tree}"),
                },
                indent=2,
            )
            + "\n"
        )
    if args.phase == "gold":
        code = runtime.functional(logs, "offline-reference", check=False)
        baseline = runtime.parse(
            logs / "offline-reference.log", Path("/opt/svb/baseline.json")
        )
        if baseline.get("FailList") or baseline.get("Status") is False:
            reports = logs / "reference-failure-reports"
            reports.mkdir(exist_ok=True)
            diagnostic_text = (logs / "offline-reference.log").read_text(
                errors="replace"
            )
            for source in Path(runtime.REPO).rglob("test-suite.log"):
                target = reports / source.relative_to(runtime.REPO)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                diagnostic_text += source.read_text(errors="replace")
            missing = [
                marker
                for marker in [
                    "Unknown font function implementation",
                    "ModuleNotFoundError:",
                    "error while loading shared libraries",
                ]
                if marker in diagnostic_text
            ]
            if missing:
                raise RuntimeError(
                    "Missing reference-test dependency: " + ", ".join(missing)
                )
        if not (baseline.get("PassList") or baseline.get("Status") is True):
            raise RuntimeError(
                "Offline reference has no positive test evidence; exit=" + str(code)
            )
    elif args.phase == "start":
        runtime.command(["arvo", "compile"], logs / "compile.log", timeout=7200)
        runtime.command(
            ["git", "reset", "--hard", metadata["base_commit"]],
            logs / "reset-after-compile.log",
        )
        runtime.reset_repository_history(runtime.REPO, logs)
        untracked = git("ls-files", "--others", "--exclude-standard", "-z").split("\0")
        with (Path(runtime.REPO) / ".git/info/exclude").open("a") as stream:
            for name in untracked:
                if name:
                    stream.write(
                        "/"
                        + "".join("\\" + c if c in "*?[]!#\\ " else c for c in name)
                        + "\n"
                    )
        runtime.command(["dpkg-query", "-W"], logs / "packages.log")
    else:
        runtime.probe()
