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

source "${SCRIPT_DIR}/.env"

if [ $# -lt 5 ]; then
  echo "Usage: $0 <ARVO_ID> <vul|fix> <repo_name> <base_commit> <problem_statement_text>"
  exit 1
fi
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

TEMPLATE_PATH="${TEMPLATE_ROOT}/${ARVO_ID}"
DOCKERFILE_NAME="${TEMPLATE_PATH}/Dockerfile.${AGENT_IMAGE_NAME}"
OUTPUT_DIR="${RESULTS_ROOT}/${ARVO_ID}/${MODE}/output_${ARVO_ID}_${MODE}_${TIMESTAMP}"

mkdir -p "${TEMPLATE_PATH}"
mkdir -p "${OUTPUT_DIR}"

bash "${EVAL_DIR}/my_utils/build_image.sh" "$ARVO_ID" "$MODE" "aider" "$AGENT_IMAGE_NAME" "$TEMPLATE_PATH"
echo "build finished"

PROMPT_TEMPLATE_PATH="${EVAL_DIR}/my_utils/prompt_template.txt"

RAW_TEMPLATE=$(cat "$PROMPT_TEMPLATE_PATH")

FILLED_PROMPT="${RAW_TEMPLATE//\{\{working_dir\}\}/\/${REPO_NAME#/}}"
FILLED_PROMPT="${FILLED_PROMPT//\{\{problem_statement\}\}/${PROBLEM_STATEMENT}}"

FULL_PROBLEM_STATEMENT=$(printf '%s' "$FILLED_PROMPT" | sed 's/"/\\"/g')
FILLED_PROMPT_PATH="${TEMPLATE_PATH}/prompt.txt"
echo "$FULL_PROBLEM_STATEMENT" > "$FILLED_PROMPT_PATH"

CONTAINER_NAME="${ARVO_ID}_${MODE}_aider_container_${TIMESTAMP}"

if [[ "$AI_MODEL" == gpt* || "$AI_MODEL" == o3 ]]; then
  EXTRA_ENV="-e OPENAI_API_KEY=$OPENAI_API_KEY"
elif [[ "$AI_MODEL" == claude* ]]; then
  EXTRA_ENV="-e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY"
elif [[ "$AI_MODEL" == deepseek* ]]; then
  EXTRA_ENV="-e DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY"
else
  echo "[ERROR] Unknown AI_MODEL: $AI_MODEL"
  exit 1
fi

if [[ "$AI_MODEL" == "deepseek-chat" ]]; then
  AI_MODEL="deepseek/deepseek-chat"
fi

echo "start running aider"
docker run --rm --init -t -a stdout -a stderr \
  --name "$CONTAINER_NAME" \
  -v "$OUTPUT_DIR":/host_output:rw \
  -v "${SCRIPT_DIR}/.aider.model.settings.yml:/model_setting/.aider.model.settings.yml:ro" \
  $EXTRA_ENV \
  "$AGENT_IMAGE_NAME" \
  bash -lc '
    set -euo pipefail
    trap "jobs -p | xargs -r kill || true" EXIT
    cd "'"$REPO_NAME"'" && \
    git reset --hard HEAD && git checkout "'"$BASE_COMMIT"'" && git clean -fd && \
    BASE_SHA=$(git rev-parse HEAD) && \
    aider . \
      --verbose \
      --message "'"$FULL_PROBLEM_STATEMENT"'" \
      --yes-always \
      --no-suggest-shell-commands \
      --no-browser \
      --model "'"$AI_MODEL"'" \
      --model-settings-file "/model_setting/.aider.model.settings.yml" \
      --chat-history-file /host_output/aider_chat_history.txt \
      --llm-history-file /host_output/aider_llm_history.txt \
      > /host_output/aider_log.txt 2>&1 && \
    git diff --full-index ${BASE_SHA}..HEAD > /host_output/latest_diff.patch && \
    echo "[DONE] Task finished"
  ' </dev/null

echo "[DONE] Container exit"
