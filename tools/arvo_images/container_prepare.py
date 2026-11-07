"""Run online preparation, then independent offline reference and start checks."""

import argparse
import json
import re
import shlex
from pathlib import Path
import subprocess
import shutil
import sys


def stable_arvo_build(source, directory, project=None):
    """Keep ARVO commands in the base image's declared working directory."""
    if not Path(directory).is_absolute():
        raise ValueError("ARVO build directory must be absolute")
    source = re.sub(r"(?m)^([ \t]*mkdir) build(?=\s|$)", r"\1 -p build", source)
    if project and Path(project).name.lower() == "ndpi":
        clean = "if [ -f Makefile ]; then make distclean; fi\n"
        if clean not in source:
            source = source.replace("sh autogen.sh\n", clean + "sh autogen.sh\n", 1)
        # Optional ordinary tools cannot link fuzzer-only coverage callbacks.
        source = re.sub(
            r"(?m)^make$",
            'make -j"$(nproc)" -C src/lib\nmake -j"$(nproc)" -C fuzz',
            source,
        )
    lines = source.splitlines(keepends=True)
    position = 1 if lines and lines[0].startswith("#!") else 0
    command = "cd " + shlex.quote(directory) + "\n"
    if len(lines) <= position or lines[position] != command:
        lines.insert(position, command)
    return "".join(lines)


def prepare_online(runtime, logs):
    """Retain preparation logs when Docker removes a failed build container."""
    try:
        runtime.prepare()
    except Exception:  # noqa: BLE001 -- Emit diagnostics and preserve the original error.
        for path in sorted(logs.rglob("*")):
            if path.is_file() and path.suffix in {".log", ".json", ".exit", ".sh"}:
                print("\nPreparation log: " + str(path.relative_to(logs)), flush=True)
                print(path.read_text(errors="replace"), flush=True)
        raise


def main():
    sys.path.insert(0, "/opt/svb")
    import runtime

    phase = argparse.ArgumentParser()
    phase.add_argument("phase", choices=["online", "gold", "start"])
    args = phase.parse_args()
    metadata = json.loads(Path("/opt/svb/image-metadata.json").read_text())
    logs = Path("/opt/svb/preparation")
    logs.mkdir(exist_ok=True)

    def git(*values):
        return subprocess.check_output(
            ["git", *values], cwd=runtime.REPO, text=True
        ).strip()

    if args.phase == "online":
        build_cwd = metadata["arvo_build_cwd"]
        build = Path("/src/build.sh")
        original = build.read_text()
        updated = stable_arvo_build(original, build_cwd, metadata["repo_cwd"])
        (logs / "arvo-build-before.sh").write_text(original)
        (logs / "arvo-build-after.sh").write_text(updated)
        build.write_text(updated)
        # Keep history only in the private preparation stage, for offline gold checkout.
        runtime.reset_repository_history = lambda *values: None
        prepare_online(runtime, logs)
    else:
        runtime.network_probe(logs / "network.json")
        if args.phase in ("gold", "start"):
            commit = (
                metadata["vic"] if args.phase == "gold" else metadata["base_commit"]
            )
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
            untracked = git("ls-files", "--others", "--exclude-standard", "-z").split(
                "\0"
            )
            with (Path(runtime.REPO) / ".git/info/exclude").open("a") as stream:
                for name in untracked:
                    if name:
                        stream.write(
                            "/"
                            + "".join("\\" + c if c in "*?[]!#\\ " else c for c in name)
                            + "\n"
                        )
            runtime.command(["dpkg-query", "-W"], logs / "packages.log")



if __name__ == "__main__":
    main()
