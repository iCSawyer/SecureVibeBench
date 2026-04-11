#!/usr/bin/env python3
import json
from pathlib import Path
import os
import subprocess
from urllib.parse import urlparse
import shlex
import argparse
import sys

parser = argparse.ArgumentParser(
    description="Extract info from task JSON for shell usage; optionally override task description from a TXT file."
)
parser.add_argument("json_path", type=Path, help="Path to the task log JSON file")
args = parser.parse_args()

clone_repo_base = "./clone_repo"

try:
    with args.json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
except Exception as e:
    print(f"ERROR=Failed to read JSON: {shlex.quote(str(e))}")
    sys.exit(1)

def safe_get(d, *keys):
    for key in keys:
        if isinstance(d, dict) and key in d:
            d = d[key]
        else:
            return None
    return d

def get_repo_name_from_url(repo_url):
    path = urlparse(repo_url or "").path
    return path.strip("/").replace(".git", "").replace("/", "_")

def shell_print(key, value):
    if value is None:
        print(f"{key}=")
    else:
        print(f"{key}={shlex.quote(str(value))}")

vic = safe_get(data, "1_szz_info", "vic")
arvo_id                        = safe_get(data, "1_szz_info", "localid")
repo_url                       = safe_get(data, "1_szz_info", "repo_url")
repo_name                      = get_repo_name_from_url(repo_url)
repo_path                      = os.path.join(clone_repo_base, repo_name)

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
        text=True
    ).strip()
except subprocess.CalledProcessError:
    pvic = None

find_entry_cwd_value = safe_get(
    data, "2_validate_result", "PVIC", "log", "2_check_repo_cwd", "output"
)

json_real = args.json_path.resolve()
task_description = safe_get(data, "5_final_description")

# === Output (shell friendly key=value) ===
shell_print("VIC", vic)
shell_print("PVIC", pvic)
shell_print("REPO_URL", repo_url)
shell_print("ARVO_ID", arvo_id)
shell_print("FIND_ENTRY_CWD", find_entry_cwd_value)
shell_print("TASK_DESCRIPTION", task_description)
