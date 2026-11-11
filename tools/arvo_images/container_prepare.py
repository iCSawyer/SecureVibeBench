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
    prefix = ""
    if project and Path(project).name.lower() == "harfbuzz":
        # The original fuzz image has no system optional backends. Keep -m32
        # builds from discovering 64-bit libraries installed for ordinary tests.
        prefix = (
            'case " $CFLAGS $CXXFLAGS " in\n'
            '  *" -m32 "*) export PKG_CONFIG_PATH= PKG_CONFIG_LIBDIR=/opt/svb/fuzz-pkgconfig-empty ;;\n'
            "esac\n"
        )
        source = re.sub(r"(?m)^mkdir all-fonts(?=\s|$)", "mkdir -p all-fonts", source)
    if project and Path(project).name.lower() == "libsrtp":
        directory_arg = shlex.quote(project)
        prefix = (
            f"if [ -f {directory_arg}/Makefile ]; then "
            f"make -C {directory_arg} distclean; fi\n"
        )
    if project and Path(project).name == "mruby":
        source = source.replace("mkdir LPM &&", "mkdir -p LPM &&")
        source = re.sub(r"\bninja(?=\))", 'ninja -j"${CMAKE_BUILD_PARALLEL_LEVEL:-4}"', source)
    if project and Path(project).name == "miniz":
        clean = "rm -rf " + shlex.quote(str(Path(project) / "build")) + "\n"
        if clean not in source:
            prefix += clean
    if project and Path(project).name == "mupdf":
        source = source.replace(
            "mv $SRC/{*.zip,*.dict,*.options} $OUT",
            "cp $SRC/{*.zip,*.dict,*.options} $OUT",
        )
        source = re.sub(
            r"(?m)^mv (\$SRC|/src)/\*\.zip (\$SRC|/src)/\*\.dict (\$SRC|/src)/\*\.options (\$OUT|/out)[ \t]*$",
            lambda match: "cp" + match.group(0)[2:], source,
        )
    if project and Path(project).name == "openvswitch":
        clean = "if [ -f Makefile ]; then make distclean; fi\n"
        if clean not in source:
            prefix += clean
        source = re.sub(
            r"(?m)^wget -O (\$OUT|/out)/json\.dict https://raw\.githubusercontent\.com/rc0r/afl-fuzz/master/dictionaries/json\.dict[ \t]*$",
            lambda match: "cp /opt/svb/offline-assets/openvswitch-json.dict " + match.group(1) + "/json.dict",
            source,
        )
    lines = source.splitlines(keepends=True)
    position = 1 if lines and lines[0].startswith("#!") else 0
    command = "cd " + shlex.quote(directory) + "\n"
    if len(lines) <= position or lines[position] != command:
        lines.insert(position, command)
    if prefix and prefix not in source:
        lines.insert(position + 1, prefix)
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
            if (
                baseline.get("FailList")
                or baseline.get("Status") is False
                or baseline.get("FailNumber", 0)
                or baseline.get("UnknownNumber", 0)
            ):
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
            if not runtime.has_positive_evidence(baseline):
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
