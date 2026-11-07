#!/usr/bin/env python3
"""Refresh selected-task progress from the individual stage journals."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
root = args.output.resolve()
selection = json.loads((root / "selection.json").read_text())
rows = []
for identifier in selection["selected"]:
    path = root / "tasks" / identifier / "status.json"
    state = json.loads(path.read_text()) if path.exists() else {"state": "queued"}
    if not state.get("stages") and state.get("error", "").startswith(
        "FileExistsError:"
    ):
        state = {"state": "queued"}
    rows.append(
        {
            "task": identifier,
            "state": state["state"],
            "phase": next(
                (
                    name
                    for name, value in state.get("stages", {}).items()
                    if value["state"] == "running"
                ),
                None,
            ),
            "registry": state.get("registry"),
            "error": state.get("error"),
        }
    )
result = {
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "total": len(rows),
    "completed": sum(row["state"] == "completed" for row in rows),
    "failed": sum(row["state"] == "failed" for row in rows),
    "tasks": rows,
}
(root / "progress.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
