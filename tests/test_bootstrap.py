"""Verify source installation and release-resource downloads."""

import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock
from urllib.parse import unquote

from securevibebench_evaluation import bootstrap


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(tempfile.TemporaryDirectory(prefix="svb-bootstrap-test-"))
        self.root = Path(temporary)
        self.cache = self.root / "cache"
        self.commit = "a" * 40
        self.events = []
        self.responses = {
            "habour/harbor.yaml": b"agents: []\n",
            "habour/dev/harbor_verifier.py": b"# Original evaluator fixture\n",
            "habour/data/securevibebench-1/task.toml": b'schema_version = "1.4"\n',
        }
        record = {"task_count": 1, "files_sha256": {
            name: hashlib.sha256(content).hexdigest() for name, content in self.responses.items()
        }}
        self.responses["habour/preview-manifest.json"] = json.dumps(record).encode()
        (self.root / "resources.json").write_text(json.dumps({
            "hf_repo": "fixture/SecureVibeBench", "hf_commit": self.commit, "task_count": 1,
        }))
        (self.root / "pyproject.toml").write_text(
            '[dependency-groups]\ndev = ["build>=1.2.2", "twine>=6.0"]\n'
        )
        self.enterContext(mock.patch.object(bootstrap, "HERE", self.root))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def open_url(self, request, timeout):
        name = unquote(request.full_url.split(f"/resolve/{self.commit}/", 1)[1])
        self.events.append("http:" + name)
        return io.BytesIO(self.responses[name])

    def http_fixture(self):
        return mock.patch.object(bootstrap, "build_opener", return_value=types.SimpleNamespace(open=self.open_url))

    def test_source_install_uses_uv_without_a_separate_dataset_download(self):
        with mock.patch.object(bootstrap, "download_dataset", side_effect=AssertionError("unexpected download")), \
                mock.patch.object(bootstrap.shutil, "which", return_value="/tools/uv"), \
                mock.patch.object(bootstrap.subprocess, "run") as process:
            bootstrap.install(self.root)
        process.assert_called_once_with(["/tools/uv", "sync", "--no-dev", "--no-editable"],
                                        cwd=self.root, check=True)

    def test_explicit_pip_install_does_not_require_uv(self):
        with mock.patch.object(bootstrap, "download_dataset") as download, \
                mock.patch.object(bootstrap.shutil, "which") as which, \
                mock.patch.object(bootstrap.subprocess, "run") as process:
            bootstrap.install(self.root, installer="pip")
        download.assert_not_called()
        which.assert_not_called()
        process.assert_called_once_with([sys.executable, "-m", "pip", "install", str(self.root)],
                                        cwd=self.root, check=True)

    def test_bad_checksum_discards_partial_resource_download(self):
        self.responses["habour/harbor.yaml"] = b"corrupted\n"
        with self.http_fixture():
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                bootstrap.download_dataset(self.cache)
        self.assertFalse((self.cache / self.commit).exists())
        self.assertEqual(list(self.cache.glob(".hf-dataset-*")), [])

    def test_pip_development_install_works_when_uv_is_absent(self):
        with mock.patch.object(bootstrap, "download_dataset") as download, \
                mock.patch.object(bootstrap.shutil, "which", return_value=None), \
                mock.patch.object(bootstrap.subprocess, "run") as process:
            bootstrap.install(self.root, dev=True)
        download.assert_not_called()
        process.assert_called_once_with(
            [sys.executable, "-m", "pip", "install", "-e", str(self.root), "build>=1.2.2", "twine>=6.0"],
            cwd=self.root, check=True,
        )

    def test_cached_snapshot_is_reused_offline_and_still_verified(self):
        with self.http_fixture():
            snapshot = bootstrap.download_dataset(self.cache)
        with mock.patch.object(bootstrap, "build_opener", side_effect=AssertionError("unexpected network")):
            self.assertEqual(bootstrap.download_dataset(self.cache), snapshot)
            (snapshot / "habour/harbor.yaml").write_text("changed\n")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                bootstrap.download_dataset(self.cache)


if __name__ == "__main__":
    unittest.main()
