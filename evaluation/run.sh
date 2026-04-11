#!/bin/bash

# Usage:
# bash run.sh <AGENT_NAME> <MODEL_NAME> <INSTANCE_ID>   # run a single instance
# bash run.sh <AGENT_NAME> <MODEL_NAME> ALL              # run all instances

set -euo pipefail
start_time=$(date +%s)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ==========================================
# Helper functions (defined before use)
# ==========================================
finish() {
  local end_time
  end_time=$(date +%s || true)
  local elapsed=$(( ${end_time:-0} - ${start_time:-0} ))
  local minutes=$(( ${elapsed:-0} / 60 ))
  local seconds=$(( ${elapsed:-0} % 60 ))
  echo "[INFO] Total time: ${minutes}m ${seconds}s"
}

# ==========================================
# Parse arguments
# ==========================================
if [ "$#" -ne 3 ]; then
  echo "Usage: bash run.sh <AGENT_NAME> <MODEL_NAME> <INSTANCE_ID|ALL>"
  echo "Examples:"
  echo "  bash run.sh aider claude-3-7-sonnet-20250219 992"
  echo "  bash run.sh sweagent claude-3-7-sonnet-20250219 ALL"
  exit 1
fi

AGENT_NAME="$1"
AI_MODEL="$2"
INSTANCE_ARG="$3"

# ==========================================
# Resolve instance IDs
# ==========================================
DATA_DIR="${SCRIPT_DIR}/../data"
JSON_PATH_DIR="${DATA_DIR}"

# Check if JSONs exist; if not, unzip full_dataset.zip as described in README
if ! ls "${JSON_PATH_DIR}"/*.json >/dev/null 2>&1; then
  echo "[INFO] No JSON files found in data/. Unzipping full_dataset.zip..."
  (cd "${DATA_DIR}" && unzip -o full_dataset.zip)
fi

if [ "$INSTANCE_ARG" == "ALL" ]; then
  ARVO_IDS=()
  for f in "$JSON_PATH_DIR"/*.json; do
    id="$(basename "$f" .json)"
    # Skip non-numeric files like format_example.json
    if [[ "$id" =~ ^[0-9]+$ ]]; then
      ARVO_IDS+=("$id")
    fi
  done
else
  ARVO_IDS=("$INSTANCE_ARG")
fi

# ==========================================
# Set up paths and config
# ==========================================
timestamp=$(date +%Y%m%d_%H%M%S)

EVAL_ROOT="${SCRIPT_DIR}/evaluate_${AGENT_NAME}_on_arvo"
RESULTS_ROOT="${EVAL_ROOT}/results-${timestamp}-${AI_MODEL}"
TEMPLATE_ROOT="${EVAL_ROOT}/template_output_${AI_MODEL}"

LOG_DIR="${SCRIPT_DIR}/logs/${AGENT_NAME}/${AI_MODEL}/${timestamp}"
mkdir -p "$LOG_DIR"
LOG_PATH="${LOG_DIR}/output_${timestamp}.log"

touch "$LOG_PATH"
exec > >(stdbuf -oL -eL tee -a "$LOG_PATH") 2>&1

RUN_POC="TRUE"
RUN_TEST="TRUE"
RUN_SAST="TRUE"
MODE="vul"
CONTAINER_KEEP_ALIVE="TRUE"

mkdir -p "$RESULTS_ROOT"

trap finish EXIT

echo "[RUN] agent=${AGENT_NAME} model=${AI_MODEL}"
echo "[RUN] results_root=${RESULTS_ROOT}"
echo "[RUN] json_path_dir=${JSON_PATH_DIR}"
echo "[RUN] arvo_ids=(${ARVO_IDS[*]})"

# ==========================================
# Run each instance
# ==========================================
cd "$SCRIPT_DIR"

for ARVO_ID in "${ARVO_IDS[@]}"; do
  if ! stdbuf -oL -eL timeout 30m \
      bash run_instance.sh "$ARVO_ID" "$MODE" "$AGENT_NAME" "$CONTAINER_KEEP_ALIVE" \
           "$RUN_POC" "$RUN_TEST" "$RUN_SAST" "$AI_MODEL" "$JSON_PATH_DIR" \
           "$RESULTS_ROOT" "$TEMPLATE_ROOT"; then
    echo "[WARN] Instance for ARVO_ID=$ARVO_ID, AGENT_NAME=$AGENT_NAME exceeded 30 minutes or failed."
  fi
done
