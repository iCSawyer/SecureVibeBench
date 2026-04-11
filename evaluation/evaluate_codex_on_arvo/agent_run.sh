#!/bin/bash
set -euo pipefail

export PATH="/opt/conda/envs/codex_env/bin:/opt/conda/bin:$PATH"
export HOME="/home/agent"

echo "[DEBUG] PATH = $PATH"
which codex || echo "[ERROR] codex not found in PATH" >&2

echo "[DEBUG] ===== Running as agent ====="
echo "[DEBUG] whoami = $(whoami)"
echo "[DEBUG] HOME = $HOME"
echo "[DEBUG] AI_MODEL = ${AI_MODEL:-"(unset)"}"
echo "[DEBUG] TASK_PROMPT = $TASK_PROMPT"
echo "[DEBUG] REPO_NAME = ${REPO_NAME:-"(unset)"}"
echo "[DEBUG] BASE_COMMIT = ${BASE_COMMIT:-"(unset)"}"

# 1. git baseline
if [ -d "$REPO_NAME" ]; then
  cd "$REPO_NAME"
  git reset --hard HEAD || true
  git checkout "$BASE_COMMIT" || true
  git clean -fd || true
  BASE_SHA=$(git rev-parse HEAD)
  echo "[DEBUG] BASE_SHA = $BASE_SHA"
  cd - >/dev/null 2>&1 || true
else
  echo "[WARN] REPO_NAME directory not found: $REPO_NAME"
fi

# 2. Run Codex
echo "[DEBUG] Starting Codex main task..."

START_TIME=$(date +%s)

codex exec "$TASK_PROMPT" \
  --model "${AI_MODEL}" \
  --cd "$REPO_NAME" \
  --dangerously-bypass-approvals-and-sandbox \
  --json \
  --output-last-message /host_output/codex_last_message.txt \
  | tee /host_output/codex_run_stdout.jsonl

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
echo "{ \"event\": \"wall_time\", \"seconds\": $ELAPSED }" \
    >> /host_output/codex_run_stdout.jsonl

# 3. Generate patch
echo "========== [PATCH] START =========="

if [ -d "$REPO_NAME" ] && [ -n "${BASE_SHA:-}" ]; then
  echo "[PATCH] cd into repo: $REPO_NAME"
  cd "$REPO_NAME" || {
    echo "[PATCH][ERROR] cd $REPO_NAME failed"
    exit 0
  }

  echo "[PATCH] pwd = $(pwd)"
  echo "[PATCH] BASE_SHA = $BASE_SHA"

  echo "------ [PATCH] git status BEFORE intent-to-add ------"
  git status --short || echo "[PATCH] git status failed (before add)"

  echo "------ [PATCH] git add --intent-to-add . ------"
  git add --intent-to-add . >/dev/null 2>&1 || echo "[PATCH] intent-to-add failed"

  echo "------ [PATCH] git status AFTER intent-to-add ------"
  git status --short || echo "[PATCH] git status failed (after add)"

  echo "------ [PATCH] Show HEAD commit ------"
  git log -1 --oneline || echo "[PATCH] git log failed"

  echo "------ [PATCH] diff from BASE_SHA to working tree ------"
  git diff --full-index "$BASE_SHA" | tee /host_output/latest_diff.patch

  echo "------ [PATCH] patch file size ------"
  wc -c /host_output/latest_diff.patch || true

  echo "------ [PATCH] patch file preview (first 30 lines) ------"
  head -n 30 /host_output/latest_diff.patch || true

  echo "========== [PATCH] END =========="

else
  echo "[PATCH][WARN] REPO_NAME=$REPO_NAME not found OR BASE_SHA empty"
fi

echo "[DONE] agent_run.sh finished"
