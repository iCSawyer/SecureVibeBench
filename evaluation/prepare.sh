#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname -- "$SCRIPT_DIR")"

# Help must work before any tools are installed or files downloaded.
for argument in "$@"; do
    if [[ "$argument" == --help || "$argument" == -h ]]; then
        cat <<'HELP'
Usage: bash evaluation/prepare.sh [OPTIONS]

Download and verify the HF tasks and evaluator first, then install uv if
missing and prepare Python and locked dependencies. No model API key is required.

Options:
  --hf-repo REPO          HF dataset (default: iCSawyer/SecureVibeBench)
  --hf-revision REVISION  Branch, tag or commit (default: habour-preview)
  --cache-dir PATH       HF cache (default: dev/cache/huggingface)

Prerequisites: Python 3.8+, Git and curl or wget (for installing uv).
Docker with Compose and a running daemon is required for evaluation only.
HELP
        exit 0
    fi
done

if ! command -v python3 >/dev/null 2>&1; then
    echo "Install Python 3.8+ to download the HF dataset before environment setup." >&2
    exit 1
fi
python3 -B "$SCRIPT_DIR/prepare.py" "$@"

if ! command -v git >/dev/null 2>&1; then
    echo "Install Git with your system package manager, then rerun this script." >&2
    exit 1
fi

export PATH="$REPO_ROOT/dev/tools/uv:$PATH"
if ! command -v uv >/dev/null 2>&1; then
    mkdir -p "$REPO_ROOT/dev/tools/uv"
    (
        installer="$(mktemp)"
        trap 'rm -f "$installer"' EXIT
        if command -v curl >/dev/null 2>&1; then
            curl --fail --location --silent --show-error https://astral.sh/uv/install.sh -o "$installer"
        elif command -v wget >/dev/null 2>&1; then
            wget -q https://astral.sh/uv/install.sh -O "$installer"
        else
            echo "Install curl or wget to download the uv installer." >&2
            exit 1
        fi
        UV_UNMANAGED_INSTALL="$REPO_ROOT/dev/tools/uv" sh "$installer"
    )
fi

source "$SCRIPT_DIR/setup.sh"
cd "$REPO_ROOT"

if ! command -v docker >/dev/null 2>&1; then
    echo "Before evaluation, install Docker Engine and Docker Compose."
else
    if ! docker compose version >/dev/null 2>&1; then
        echo "Before evaluation, install the Docker Compose plugin."
    fi
    if ! docker info >/dev/null 2>&1; then
        echo "Before evaluation, start Docker and ensure your user can access its daemon."
    fi
fi
echo "Preparation complete. Run: bash evaluation/run.sh '<provider/model>' --task 992"
