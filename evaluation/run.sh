#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/setup.sh"
if [[ $# -gt 0 && "$1" != -* ]]; then
    MODEL_NAME="$1"
    shift
    set -- --model "$MODEL_NAME" "$@"
fi
cd "$REPO_ROOT"
exec uv run --no-sync svb-evaluate "$@"
