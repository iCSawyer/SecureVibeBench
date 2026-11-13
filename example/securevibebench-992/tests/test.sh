#!/bin/bash
set -euo pipefail
exec /opt/svb/python/bin/python3 -I /tests/_svb/differential_runtime.py verify
