#!/usr/bin/env python3
"""Like extract_info.py, but loads task fields from the Hugging Face dataset."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from datasets import load_dataset  # type: ignore[reportMissingImports]

parser = argparse.ArgumentParser(
    description=(
        "Extract info from the SecureVibeBench Hugging Face dataset for shell usage "
        "(same key=value output as extract_info.py, and compatible with its JSON-path "
        "CLI call pattern)."
    )
)
parser.add_argument(
    "task_ref",
    help=(
        "Task localid (e.g. 992), or a legacy task JSON path like no_github/data/992.json"
    ),
)
parser.add_argument(
    "--split",
    default="train",
    help="Dataset split (default: train)",
)
args = parser.parse_args()

clone_repo_base = "./clone_repo"
HF_DATASET_ID = "iCSawyer/SecureVibeBench"


def get_repo_name_from_url(repo_url: str | None) -> str:
    path = urlparse(repo_url or "").path
    return path.strip("/").replace(".git", "").replace("/", "_")


def shell_print(key: str, value: object | None) -> None:
    if value is None:
        print(f"{key}=")
    else:
        print(f"{key}={shlex.quote(str(value))}")


def resolve_localid(task_ref: str) -> str:
    target = str(task_ref).strip()
    path = Path(target).expanduser()

    # Compatibility mode for callers like run_instance.sh, which pass a task JSON path.
    if path.suffix.lower() == ".json" or path.exists():
        if path.is_file():
            try:
                with path.open("r", encoding="utf-8") as f:
                    legacy_data = json.load(f)
                localid = legacy_data["1_szz_info"]["localid"]
                return str(localid).strip()
            except Exception:
                # Fall back to the file stem so paths like ".../992.json" still work.
                pass

        stem = path.stem.strip()
        if stem:
            return stem

    return target


def load_row_by_localid(localid: str) -> dict:
    target = str(localid).strip()
    try:
        ds = load_dataset(HF_DATASET_ID, split=args.split)
        src_desc = f"{HF_DATASET_ID!r} split={args.split!r}"
    except Exception as e:
        print(
            f"ERROR=Failed to load dataset: {shlex.quote(str(e))}",
            file=sys.stderr,
        )
        sys.exit(1)

    for i in range(len(ds)):
        row = ds[i]
        if str(row.get("localid", "")).strip() == target:
            return row

    print(
        f"ERROR=No row with localid={shlex.quote(target)} in {src_desc}",
        file=sys.stderr,
    )
    sys.exit(1)


data = load_row_by_localid(resolve_localid(args.task_ref))

vic = data.get("vic")
arvo_id = data.get("localid")
repo_url = data.get("repo_url")
repo_name = get_repo_name_from_url(repo_url)
repo_path = os.path.join(clone_repo_base, repo_name)

if not os.path.isdir(repo_path):
    try:
        print(f"Cloning repo: {repo_url} into {repo_path}", file=sys.stderr)
        subprocess.run(["git", "clone", repo_url, repo_path], check=True)
    except subprocess.CalledProcessError as e:
        print(f"ERROR=Failed to clone repo: {e}", file=sys.stderr)
        sys.exit(1)


try:
    pvic = subprocess.check_output(
        ["git", "rev-parse", f"{vic}^"],
        cwd=repo_path,
        text=True,
    ).strip()
except subprocess.CalledProcessError:
    pvic = None

find_entry_cwd_value = data.get("repo_cwd")
task_description = data.get("description")

# === Output (shell friendly key=value); same keys as extract_info.py ===
shell_print("VIC", vic)
shell_print("PVIC", pvic)
shell_print("REPO_URL", repo_url)
shell_print("ARVO_ID", arvo_id)
shell_print("FIND_ENTRY_CWD", find_entry_cwd_value)
shell_print("TASK_DESCRIPTION", task_description)
