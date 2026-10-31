#!/usr/bin/env python3
"""Install the source checkout with uv or pip."""

import importlib.util
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "evaluation/bootstrap.py"
spec = importlib.util.spec_from_file_location("svb_bootstrap", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

if __name__ == "__main__":
    raise SystemExit(module.main())
