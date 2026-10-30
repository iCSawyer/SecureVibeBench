#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname -- "$SCRIPT_DIR")"
MINI_SOURCE="$SCRIPT_DIR/mini-swe-agent"
MINI_REPOSITORY="https://github.com/SWE-agent/mini-swe-agent.git"
MINI_TAG="v2.4.6"
MINI_COMMIT="a83fcae82d2a08f0ee0c688f9d137b3566c097f8"

export UV_PROJECT_ENVIRONMENT="${SVB_EVAL_VENV:-$REPO_ROOT/dev/.venv}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$REPO_ROOT/dev/.uv-cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$REPO_ROOT/dev/.uv-python}"
export PYTHONDONTWRITEBYTECODE=1
export PATH="$REPO_ROOT/dev/tools/uv:$PATH"

if ! command -v uv >/dev/null 2>&1; then
    echo "Run bash evaluation/prepare.sh first to install uv and prepare the dataset." >&2
    exit 1
fi

mkdir -p "$REPO_ROOT/dev/build-metadata"
if [[ ! -e "$MINI_SOURCE" ]]; then
    git clone --depth 1 --branch "$MINI_TAG" "$MINI_REPOSITORY" "$MINI_SOURCE"
    ACTUAL_COMMIT="$(git -C "$MINI_SOURCE" rev-parse HEAD)"
    if [[ "$ACTUAL_COMMIT" != "$MINI_COMMIT" ]]; then
        echo "Unexpected mini-swe-agent release commit: $ACTUAL_COMMIT" >&2
        exit 1
    fi
elif [[ ! -f "$MINI_SOURCE/pyproject.toml" ]]; then
    echo "The editable mini-swe-agent source is incomplete: $MINI_SOURCE" >&2
    exit 1
fi
# Preserve an existing checkout and any local edits. The lockfile governs
# dependency versions; this script never resets or replaces editable source.
uv sync --project "$REPO_ROOT" --locked --python "${SVB_EVAL_PYTHON:-3.12}"
