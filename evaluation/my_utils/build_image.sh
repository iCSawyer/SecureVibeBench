#!/bin/bash
set -euo pipefail

ARVO_ID="$1"
MODE="$2"
AGENT_NAME="$3"
AGENT_IMAGE_NAME="$4"
TEMPLATE_PATH="$5"

# Resolve paths relative to the evaluation/ directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EVAL_DIR="$(dirname "$SCRIPT_DIR")"

TEMPLATE_ROOT="${EVAL_DIR}/evaluate_${AGENT_NAME}_on_arvo"
TEMPLATE_FILE="${TEMPLATE_ROOT}/Dockerfile.template"
DOCKERFILE_NAME="${TEMPLATE_PATH}/Dockerfile.${AGENT_IMAGE_NAME}"

mkdir -p "$TEMPLATE_PATH"

HASH_FILE="${TEMPLATE_ROOT}/Dockerfile.template.hash"

build_image () {
  local IMAGE_PATH="${EVAL_DIR}/my_utils/arvo_images"
  local RESOLVE_IMAGE_SCRIPT="${EVAL_DIR}/my_utils/resolve_image.py"
  local BASE_FROM
  BASE_FROM="$(python "$RESOLVE_IMAGE_SCRIPT" "${ARVO_ID}-${MODE}" "$IMAGE_PATH")"
  echo "[INFO] Resolved base: $BASE_FROM"

  export IMAGE_NAME="$BASE_FROM"
  envsubst '${IMAGE_NAME}' < "$TEMPLATE_FILE" > "$DOCKERFILE_NAME"
  echo "[INFO] Dockerfile rendered: $DOCKERFILE_NAME"

  echo "[INFO] Building final image: $AGENT_IMAGE_NAME"
  docker build -f "$DOCKERFILE_NAME" -t "$AGENT_IMAGE_NAME" "$TEMPLATE_ROOT"
}


if [[ ! -f "$TEMPLATE_FILE" ]]; then
  echo "[ERROR] Template not found: $TEMPLATE_FILE"
  exit 1
fi

CURRENT_TPL_HASH="$(sha256sum "$TEMPLATE_FILE" | awk '{print $1}')"
SAVED_TPL_HASH=""
if [[ -f "$HASH_FILE" ]]; then
  SAVED_TPL_HASH="$(tr -d ' \t\r\n' < "$HASH_FILE" || true)"
fi

if [[ -z "$SAVED_TPL_HASH" ]]; then
  echo "[INFO] Hash file missing/empty. Recording current template hash."
  echo "$CURRENT_TPL_HASH" > "$HASH_FILE"
  SAVED_TPL_HASH="$CURRENT_TPL_HASH"
fi

if [[ "$SAVED_TPL_HASH" != "$CURRENT_TPL_HASH" ]]; then
  echo "[INFO] Template hash changed → rebuild & save tar."
  build_image
  echo "$CURRENT_TPL_HASH" > "$HASH_FILE"
else
  echo "[INFO] Template hash unchanged."
fi

if docker image inspect "$AGENT_IMAGE_NAME" >/dev/null 2>&1; then
  echo "[INFO] Final image exists locally → use it."
  export IMAGE_NAME="n132/arvo:${ARVO_ID}-${MODE}"
  envsubst '${IMAGE_NAME}' < "$TEMPLATE_FILE" > "$DOCKERFILE_NAME"
  echo "[INFO] Dockerfile rendered: $DOCKERFILE_NAME"
else
  echo "[INFO] Image missing → build."
  build_image
fi

echo "[INFO] Ready. Image: $AGENT_IMAGE_NAME"
