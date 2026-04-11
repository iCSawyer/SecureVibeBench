#!/usr/bin/env python3
import os
import sys
import argparse
from pathlib import Path
from string import Template

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString


def env_substitute(text: str, required_vars):
    """Perform ${VAR} substitution like envsubst, error if any required var missing."""
    missing = [v for v in required_vars if os.environ.get(v) is None]
    if missing:
        raise SystemExit(f"[ERROR] Missing required env vars: {', '.join(missing)}")
    tpl = Template(text)  # supports $VAR and ${VAR}
    return tpl.substitute({k: os.environ.get(k, "") for k in required_vars})


def main():
    p = argparse.ArgumentParser(description="Render YAML config with prompt + problem statement injected.")
    p.add_argument("--config-template", required=True, help="Path to YAML template (with ${VAR} placeholders)")
    p.add_argument("--prompt-template", required=True, help="Path to prompt_template.txt")
    p.add_argument("--problem-statement", required=True, help="Path to problem_statement.txt")
    p.add_argument("--output", required=True, help="Where to write the final YAML")
    p.add_argument("--require-vars", nargs="*", default=[
        "OUTPUT_DIR", "REPO_NAME", "BASE_COMMIT", "AGENT_IMAGE_NAME", "AI_MODEL"
    ], help="Env vars to require & substitute in the YAML template")
    args = p.parse_args()

    cfg_tmpl_path = Path(args.config_template)
    prompt_path = Path(args.prompt_template)
    ps_path = Path(args.problem_statement)
    out_path = Path(args.output)

    cfg_tmpl = cfg_tmpl_path.read_text(encoding="utf-8")
    prompt_text = prompt_path.read_text(encoding="utf-8")
    ps_text = args.problem_statement

    cfg_subst = env_substitute(cfg_tmpl, args.require_vars)

    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    data = yaml.load(cfg_subst)

    data["agent"]["templates"]["instance_template"] = LiteralScalarString(prompt_text)

    if "problem_statement" not in data or not isinstance(data["problem_statement"], dict):
        data["problem_statement"] = {}
    data["problem_statement"]["text"] = LiteralScalarString(ps_text)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)

    print(f"✅ Config written to: {out_path}")


if __name__ == "__main__":
    main()
