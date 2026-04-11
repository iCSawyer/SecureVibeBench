#!/bin/bash

ARVO_ID=$1
MODE=$2
REPO_NAME=$3
BASE_COMMIT=$4
PROBLEM_STATEMENT=$5
AGENT_IMAGE_NAME=$6
RESULTS_ROOT=$7
AI_MODEL=$8
TEMPLATE_ROOT=$9

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EVAL_DIR="$(dirname "$SCRIPT_DIR")"

if [ $# -lt 5 ]; then
  echo "Usage: $0 <ARVO_ID> <vul|fix> <repo_name> <base_commit> <problem_statement_text>"
  exit 1
fi
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

TEMPLATE_PATH="${TEMPLATE_ROOT}/${ARVO_ID}"
DOCKERFILE_NAME="${TEMPLATE_PATH}/Dockerfile.${AGENT_IMAGE_NAME}"
OUTPUT_DIR="${RESULTS_ROOT}/${ARVO_ID}/${MODE}/output_${ARVO_ID}_${MODE}_${TIMESTAMP}"

mkdir -p "$TEMPLATE_PATH"
mkdir -p "$OUTPUT_DIR"

bash "${EVAL_DIR}/my_utils/build_image.sh" "$ARVO_ID" "$MODE" "openhands" "$AGENT_IMAGE_NAME" "$TEMPLATE_PATH"

PROMPT_TEMPLATE_PATH="${EVAL_DIR}/my_utils/prompt_template.txt"

RAW_TEMPLATE=$(cat "$PROMPT_TEMPLATE_PATH")

FILLED_PROMPT="${RAW_TEMPLATE//\{\{working_dir\}\}/\/${REPO_NAME#/}}"
FILLED_PROMPT="${FILLED_PROMPT//\{\{problem_statement\}\}/${PROBLEM_STATEMENT}}"

FULL_PROBLEM_STATEMENT=$(printf '%s' "$FILLED_PROMPT" | sed 's/"/\\"/g')
FILLED_PROMPT_PATH="${TEMPLATE_PATH}/prompt.txt"
CONFIG_PATH="${TEMPLATE_PATH}/config.toml"

echo "$FULL_PROBLEM_STATEMENT" > "$FILLED_PROMPT_PATH"

if [[ "$AI_MODEL" == "deepseek-chat" ]]; then
  AI_MODEL="deepseek/deepseek-chat"
fi

python "${SCRIPT_DIR}/setup_config.py" "${AI_MODEL}" "${REPO_NAME}" "${ARVO_ID}" "${TEMPLATE_PATH}"

CONTAINER_NAME="openhands_${ARVO_ID}_${MODE}_container_${TIMESTAMP}"
echo "Running container: $CONTAINER_NAME"
docker run --rm --init -t -a stdout -a stderr \
  --name "$CONTAINER_NAME" \
  -v "$OUTPUT_DIR":/host_output:rw \
  -v "$CONFIG_PATH":/openhands/code/config.toml:rw \
  -v "${SCRIPT_DIR}/OpenHands/openhands/llm/llm.py:/openhands/code/openhands/llm/llm.py:rw" \
  -e SANDBOX_VOLUMES="${REPO_NAME}":/workspace:777 \
  -e PYTHONUNBUFFERED=1 \
  "$AGENT_IMAGE_NAME" \
  bash -lc '
    set -euo pipefail
    trap "jobs -p | xargs -r kill || true" EXIT
    eval "$(/openhands/micromamba/bin/micromamba shell hook -s bash)"
    micromamba activate openhands
    cd "'"$REPO_NAME"'" && git reset --hard HEAD && git checkout "'"$BASE_COMMIT"'" && git clean -fd
    cd /openhands/code
    # -u (unbuffered) + stdbuf ensure immediate flush
    stdbuf -oL -eL poetry run python -u -m openhands.core.main -t "'"$FULL_PROBLEM_STATEMENT"'"
    cp -r /openhands/code/trajectories /host_output/ || true
    cd "'"$REPO_NAME"'" && git diff > /host_output/latest_diff.patch || true
    echo "[DONE] Task finished"
  ' </dev/null

echo "[DONE] Container exit"
