#!/bin/bash
ARVO_ID="$1"
MODE="$2"
AGENT_NAME="$3"
CONTAINER_KEEP_ALIVE=$4
RUN_POC=$5
RUN_TEST=$6
RUN_SAST=$7
AI_MODEL=$8
JSON_PATH_DIR=$9
RESULTS_ROOT=${10}
TEMPLATE_ROOT=${11}
JSON_PATH="${JSON_PATH_DIR}/${ARVO_ID}.json"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

AGENT_IMAGE_NAME="${ARVO_ID}_${MODE}_${AGENT_NAME}"
echo "Starting run_instance.sh with parameters:"
eval "$(python "${SCRIPT_DIR}/my_utils/extract_info.py" "$JSON_PATH")"

echo "VIC: $VIC"
echo "PVIC: $PVIC"
echo "REPO_URL: $REPO_URL"
echo "ARVO_ID: $ARVO_ID"
if [ "$AGENT_NAME" == "sweagent" ]; then
  FIND_ENTRY_CWD_CLEARED="${FIND_ENTRY_CWD#/}"
else
  FIND_ENTRY_CWD_CLEARED="$FIND_ENTRY_CWD"
fi
echo "FIND_ENTRY_CWD: $FIND_ENTRY_CWD"
echo "TASK_DESCRIPTION: $TASK_DESCRIPTION"

bash "${SCRIPT_DIR}/evaluate_${AGENT_NAME}_on_arvo/run_instance.sh" "$ARVO_ID" "$MODE" "$FIND_ENTRY_CWD_CLEARED" "$PVIC" "$TASK_DESCRIPTION" "$AGENT_IMAGE_NAME" "$RESULTS_ROOT" "$AI_MODEL" "$TEMPLATE_ROOT"

echo "start patch_diff.py"
python "${SCRIPT_DIR}/my_utils/patch_diff.py" \
  --arvo-id "$ARVO_ID" \
  --mode "$MODE" \
  --repo-in "$FIND_ENTRY_CWD" \
  --vic "$VIC" \
  --pvic "$PVIC" \
  --repo-url "$REPO_URL"\
  --run-poc "$RUN_POC" \
  --run-test $RUN_TEST \
  --run-sast "$RUN_SAST" \
  --results-root "$RESULTS_ROOT" \
  --keep-alive "$CONTAINER_KEEP_ALIVE"
