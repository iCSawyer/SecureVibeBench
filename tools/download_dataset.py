#!/usr/bin/env python3
"""Download and verify the pinned HF dataset for release maintenance."""

import importlib.util
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "evaluation/bootstrap.py"
spec = importlib.util.spec_from_file_location("svb_bootstrap", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

if __name__ == "__main__":
    raise SystemExit(module.main(download_only=True))
