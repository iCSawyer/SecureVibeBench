#!/bin/bash
# Evaluation runs on the Harbor host so the original evaluator can start its
# original, isolated ARVO containers. There is no replacement in-container score.
cat >&2 <<'MESSAGE'
SecureVibeBench requires its host-side Harbor verifier:
  --verifier dev.harbor_verifier:SecureVibeBenchVerifier
Run Harbor from the repository root with that directory on PYTHONPATH.
See dev/README.md. No benchmark score was computed by this fallback script.
MESSAGE
exit 2
