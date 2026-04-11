#!/usr/bin/env python3

import sys
import os
from pathlib import Path
from dotenv import load_dotenv

from tomlkit import parse, dumps
from tomlkit import table

_SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = str(_SCRIPT_DIR / "config.mytemplate.toml")
ENV_PATH      = str(_SCRIPT_DIR / ".env")

def resolve_keys_and_base_url(model_name: str):
    if not os.path.exists(ENV_PATH):
        raise FileNotFoundError(f".env file not found at: {ENV_PATH}")
    load_dotenv(dotenv_path=ENV_PATH)

    if model_name.startswith("gpt"):
        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    elif model_name.startswith("claude"):
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    elif model_name.startswith("deepseek"):
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    else:
        api_key = os.getenv("GENERIC_API_KEY", "")
        base_url = os.getenv("GENERIC_BASE_URL", "")

    if not api_key:
        raise ValueError(
            f"No API key found in {ENV_PATH} for model '{model_name}'. "
            "Set the appropriate key, e.g. OPENAI_API_KEY or ANTHROPIC_API_KEY."
        )
    return api_key, base_url

def ensure_table(doc, name: str):
    if name not in doc or not hasattr(doc[name], "get"):
        doc[name] = table()
    return doc[name]

def main():
    if len(sys.argv) != 5:
        print("Usage: python setup_config.py <model_name> <repo_path> <arvo_id> <output_dir>")
        sys.exit(1)

    model_name, repo_path, arvo_id ,output_dir = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

    OUTPUT_PATH = os.path.join(output_dir, "config.toml")
    print(f"[DEBUG] Writing to OUTPUT_PATH={OUTPUT_PATH}")


    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError(f"Template not found at: {TEMPLATE_PATH}")

    api_key, base_url = resolve_keys_and_base_url(model_name)

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        doc = parse(f.read())

    llm = ensure_table(doc, "llm")
    llm["model"] = model_name
    llm["api_key"] = api_key
    llm["base_url"] = base_url


    core = ensure_table(doc, "core")
    core["workspace_mount_path_in_sandbox"] = repo_path

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(dumps(doc))

    print("[INFO] config.toml updated:")
    print(f"       [llm] model={model_name}, base_url={base_url}")
    print(f"       [core] workspace_mount_path_in_sandbox={repo_path}")
    print(f"[INFO] Wrote: {OUTPUT_PATH}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(2)
