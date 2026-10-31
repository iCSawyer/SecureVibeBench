#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == eval ]]; then
    shift
fi
if [[ $# -gt 0 && "$1" != -* ]]; then
    MODEL_NAME="$1"
    shift
    set -- --model "$MODEL_NAME" "$@"
fi
exec python3 -m securevibebench_evaluation eval "$@"
