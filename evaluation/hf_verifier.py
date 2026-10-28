"""Persistent Harbor entry point delegating to the verifier downloaded from HF.

This module loads the published evaluator bridge without importing local dev/
or reimplementing any scoring. Its stable import path also works when Harbor
resumes a saved job in a new process.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import sys
from typing import Any

from harbor.verifier.base import BaseVerifier


def load_verifier(bundle: Path, expected_sha256: str | None = None):
    path = bundle.resolve() / "dev" / "harbor_verifier.py"
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError(f"Downloaded verifier checksum mismatch: {path}")
    name = "_svb_hf_verifier_" + hashlib.sha256(str(path).encode()).hexdigest()[:16] + "_" + digest[:16]
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load the downloaded evaluator bridge: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        if not issubclass(module.SecureVibeBenchVerifier, BaseVerifier):
            raise ValueError("The downloaded verifier is not a Harbor BaseVerifier")
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


class HuggingFaceVerifier(BaseVerifier):
    """Call the exact HF-published verifier with the original evaluator options."""

    def __init__(self, *, bundle_dir: str, verifier_sha256: str,
                 hf_repo: str | None = None, hf_commit: str | None = None,
                 **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.bundle = Path(bundle_dir).resolve()
        task_dir = self.task.paths.task_dir.resolve()
        if not task_dir.is_relative_to(self.bundle / "data"):
            raise ValueError("Evaluation task must come from the downloaded HF bundle")
        # Do not let importing the published parser create new task inputs and
        # change the checksum seen by a later rollout of the same HF task.
        sys.dont_write_bytecode = True
        os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        module = load_verifier(self.bundle, verifier_sha256)
        self.delegate = module.SecureVibeBenchVerifier(**kwargs)

    async def verify(self):
        return await self.delegate.verify()
