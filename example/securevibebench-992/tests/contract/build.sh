#!/bin/bash
set -euo pipefail
unset CC CXX CFLAGS CXXFLAGS CPPFLAGS LDFLAGS
# Compile the actual CDF module; unused file-format entry points are discarded.
gcc -O1 -ffunction-sections -fdata-sections -DHAVE_CONFIG_H -I. -Isrc \
  src/cdf.c /tests/contract/cdf_cases.c -Wl,--gc-sections -o /tmp/svb-cdf-cases
