#!/bin/bash
# Claude Code version: 2.0.54
# Model: claude-sonnet-4-5-20250929

set -euo pipefail

export PATH="/opt/conda/envs/claude_env/bin:/opt/conda/bin:$PATH"

echo "[DEBUG] PATH = $PATH"
which claude || echo "[ERROR] claude not found in PATH" >&2

echo "[DEBUG] ===== Running as agent ====="
echo "[DEBUG] whoami = $(whoami)"
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
fi

# 2. Run Claude
echo "[DEBUG] Starting Claude main task..."

claude "$TASK_PROMPT" \
  --print \
  --dangerously-skip-permissions \
  --output-format json \
  |& tee /host_output/claude_run_stdout.json

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
  git status --short || echo "[PATCH] git status failed"

  echo "------ [PATCH] git add --intent-to-add . ------"
  git add --intent-to-add . >/dev/null 2>&1 || echo "[PATCH] intent-to-add failed"

  echo "------ [PATCH] git status AFTER intent-to-add ------"
  git status --short || echo "[PATCH] git status failed"

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
