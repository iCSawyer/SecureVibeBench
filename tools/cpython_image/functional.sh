#!/bin/bash
set -euo pipefail
cd /src/cpython3
export SVB_TEST_JOBS="${SVB_TEST_JOBS:-8}"
export PATH="/opt/svb/build-bin:$PATH"
if [ -f Makefile ]; then make distclean; fi
./configure
make -j"$SVB_TEST_JOBS"
# Preserve CPython's native resource defaults, excluding external networking.
make test TESTOPTS="-j$SVB_TEST_JOBS -uall,-largefile,-audio,-gui,-network --randseed=61721"
