#!/bin/bash
set -euo pipefail

# ==========================================
# 1. Load Arguments
# ==========================================
ARVO_ID="$1"
MODE="$2"
REPO_NAME="$3"
BASE_COMMIT="$4"
PROBLEM_STATEMENT="$5"
AGENT_IMAGE_NAME="$6"
RESULTS_ROOT="$7"
AI_MODEL="$8"
TEMPLATE_ROOT="$9"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EVAL_DIR="$(dirname "$SCRIPT_DIR")"

# ==========================================
# 2. Load API Key
# ==========================================
source "${EVAL_DIR}/.env"
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "[ERROR] ANTHROPIC_API_KEY is not set in the .env file"
    exit 1
fi

# ==========================================
# 3. Set up paths
# ==========================================
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
TEMPLATE_PATH="${TEMPLATE_ROOT}/${ARVO_ID}"
OUTPUT_DIR="${RESULTS_ROOT}/${ARVO_ID}/${MODE}/output_${ARVO_ID}_${MODE}_${TIMESTAMP}"

mkdir -p "${TEMPLATE_PATH}"
mkdir -p "${OUTPUT_DIR}"

# ==========================================
# 4. Build Docker image
# ==========================================
bash "${EVAL_DIR}/my_utils/build_image.sh" \
  "$ARVO_ID" "$MODE" "claudecode" "$AGENT_IMAGE_NAME" "$TEMPLATE_PATH"
echo "build finished"

# ==========================================
# 5. Prepare Prompt
# ==========================================
PROMPT_TEMPLATE_PATH="${EVAL_DIR}/my_utils/prompt_template.txt"

RAW_TEMPLATE="$(cat "$PROMPT_TEMPLATE_PATH")"
FILLED_PROMPT="${RAW_TEMPLATE//\{\{working_dir\}\}/\/${REPO_NAME#/}}"
FILLED_PROMPT="${FILLED_PROMPT//\{\{problem_statement\}\}/$PROBLEM_STATEMENT}"

echo "[DEBUG] FINAL PROMPT:"
echo "$FILLED_PROMPT"

# ==========================================
# 6. Run Docker + agent_run.sh
# ==========================================
CONTAINER_NAME="${ARVO_ID}_${MODE}_claudecode_container_${TIMESTAMP}"

echo "start running claude-agent"

docker run --rm --init -t \
  --name "$CONTAINER_NAME" \
  -v "$OUTPUT_DIR":/host_output:rw \
  -v "$HOME/.claude":/tmp/host_claude_dir:ro \
  -v "$HOME/.claude.json":/tmp/host_claude_file.json:ro \
  -v "${SCRIPT_DIR}/agent_run.sh":/workspace/agent_run.sh:ro \
  -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  -e TASK_PROMPT="$FILLED_PROMPT" \
  -e REPO_NAME="$REPO_NAME" \
  -e BASE_COMMIT="$BASE_COMMIT" \
  "$AGENT_IMAGE_NAME" \
  bash -lc '
  set -euo pipefail
  set -x

  rm -rf /root/agent/.claude /home/agent/.claude.json
  mkdir -p /home/agent/.claude
  cp -rf /tmp/host_claude_dir/* /home/agent/.claude/ 2>/dev/null || true
  cp /tmp/host_claude_file.json /home/agent/.claude.json 2>/dev/null || true
  chown -R agent:agent /home/agent/.claude /home/agent/.claude.json

  chmod 777 /host_output || true

  if [ -d "$REPO_NAME" ]; then
    chown -R agent:agent "$REPO_NAME" || true
  fi

  su agent -c "bash /workspace/agent_run.sh"

'
