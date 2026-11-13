"""Inspect submitted source changes and snapshot the working tree."""

import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile

TEST_DIRECTORIES = frozenset({
    "test", "tests", "testing", "testcase", "testcases", "unittest", "unittests",
    "fuzz", "fuzzing", "fuzzer", "fuzzers", ".git",
})
TEST_FILE = re.compile(r"(?:^test[_\.].*|.*_(?:test|tests|unittest)\.[^.]+|test\.(?:c|cc|cpp|h|py|sh))$", re.I)


def git(repo, *args, env=None):
    result = subprocess.run(["git", *args], cwd=repo, env=env, capture_output=True, timeout=180)
    if result.returncode:
        raise ValueError(result.stderr.decode(errors="replace").strip() or "Git command failed")
    return result.stdout


def _index_environment(directory):
    keys = {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "LD_LIBRARY_PATH", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM"}
    return {**{key: value for key, value in os.environ.items() if key in keys},
            "GIT_INDEX_FILE": str(Path(directory) / "index"), "GIT_OPTIONAL_LOCKS": "0"}


def patch_paths(repo, patch):
    """Ask Git for both ends of renames without applying the patch to source."""
    with tempfile.TemporaryDirectory(prefix="svb-patch-index-") as directory:
        env = _index_environment(directory)
        git(repo, "read-tree", "HEAD", env=env)
        git(repo, "apply", "--cached", "--check", str(patch), env=env)
        git(repo, "apply", "--cached", str(patch), env=env)
        result = git(repo, "diff", "--cached", "--name-only", "--no-renames", "-z", "HEAD", env=env)
    return [name.decode("utf-8", "surrogateescape") for name in result.split(b"\0") if name]


def protected_paths(paths, explicit=(), allowed=()):
    """Reject evaluator/test edits while permitting production build changes."""
    rejected = {}
    for name in paths:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            rejected[name] = "unsafe source path"
        elif any(name == entry.rstrip("/") or name.startswith(entry.rstrip("/") + "/") for entry in explicit):
            rejected[name] = "protected by the functional contract"
        elif ".git" in {part.lower() for part in path.parts}:
            rejected[name] = "Git metadata"
        elif name in allowed:
            continue
        elif any(part.lower() in TEST_DIRECTORIES for part in path.parts):
            rejected[name] = "test or fuzz harness outside the declared task source"
        elif TEST_FILE.fullmatch(path.name):
            rejected[name] = "test source outside the declared task source"
    return rejected


def snapshot_source(repo, paths=()):
    """Stage the declared patch paths in a private index of the prepared tree."""
    with tempfile.TemporaryDirectory(prefix="svb-source-index-") as directory:
        env = _index_environment(directory)
        git(repo, "read-tree", "HEAD", env=env)
        # The immutable starting image supplies unchanged files. Do not scan or
        # stage its downloaded caches. Include deletions and ignored new source.
        for offset in range(0, len(paths), 200):
            git(repo, "add", "-A", "-f", "--",
                *(":(literal)" + name for name in paths[offset:offset + 200]), env=env)
        return git(repo, "write-tree", env=env).decode().strip()
