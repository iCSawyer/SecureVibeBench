#!/bin/bash
set -euo pipefail
/opt/svb/python/bin/python3 - <<'PY'
from pathlib import Path
import re
path=Path('/src/build.sh')
original=path.read_text()
pattern=r'(?:\$LIB_FUZZING_ENGINE|-lFuzzingEngine)[\t ]+-lpthread[\t ]+-lz'
matches=list(re.finditer(pattern,original))
if len(matches)!=1:
    raise RuntimeError('Unknown lwan fuzz link command')
match=matches[0]
updated=original[:match.end()]+' -llua5.1'+original[match.end():]
logs=Path('/opt/svb/preparation')
(logs/'lwan-build-before.sh').write_text(original)
path.write_text(updated)
(logs/'lwan-build-after.sh').write_text(updated)
PY
