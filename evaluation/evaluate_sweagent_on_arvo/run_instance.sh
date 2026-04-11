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
OUTPUT_DIR="${RESULTS_ROOT}/${ARVO_ID}/${MODE}/output_${ARVO_ID}_${MODE}_${TIMESTAMP}"
CONFIG_TEMPLATE_PATH="${SCRIPT_DIR}/my_config_template.yaml"

CONFIG_OUTPUT_PATH="${TEMPLATE_PATH}/my_config_${ARVO_ID}_${MODE}.yaml"

mkdir -p "$TEMPLATE_PATH"
mkdir -p "$OUTPUT_DIR"

bash "${EVAL_DIR}/my_utils/build_image.sh" "$ARVO_ID" "$MODE" "sweagent" "$AGENT_IMAGE_NAME" "$TEMPLATE_PATH"

PROMPT_TEMPLATE_PATH="${EVAL_DIR}/my_utils/prompt_template.txt"

if [[ "$AI_MODEL" == "deepseek-chat" ]]; then
  AI_MODEL="deepseek/deepseek-chat"
fi

export OUTPUT_DIR REPO_NAME BASE_COMMIT AGENT_IMAGE_NAME AI_MODEL
python "${SCRIPT_DIR}/setup_config.py" \
  --config-template "$CONFIG_TEMPLATE_PATH" \
  --prompt-template "$PROMPT_TEMPLATE_PATH" \
  --problem-statement "$PROBLEM_STATEMENT" \
  --output "$CONFIG_OUTPUT_PATH"

{
  cd "${SCRIPT_DIR}/SWE-agent" && \
  sweagent run --config "$CONFIG_OUTPUT_PATH"
} || {
  echo "Failed to run sweagent in SWE-agent directory"
  exit 1
}
