#!/bin/bash
set -euo pipefail
/opt/svb/python/bin/python3 - <<'PY'
import json
from pathlib import Path
config=json.loads(Path('/opt/svb/task.json').read_text())
path=Path('/src/build.sh')
original=path.read_text()
updated=original
if str(config['localid']) in {'20702','48736'}:
    needle='$LIB_FUZZING_ENGINE ./src/.libs/libmagic.a'
    if updated.count(needle)!=1:
        raise RuntimeError('Unknown file fuzz link command')
    updated=updated.replace(needle,needle+' -lz -lbz2 -llzma')
if str(config['localid'])=='59438':
    if updated.count('mkdir pocs_all')!=1:
        raise RuntimeError('Unknown file corpus preparation command')
    updated=updated.replace('mkdir pocs_all','mkdir -p pocs_all')
logs=Path('/opt/svb/preparation')
(logs/'file-build-before.sh').write_text(original)
path.write_text(updated)
(logs/'file-build-after.sh').write_text(updated)
PY
