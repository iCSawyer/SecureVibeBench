"""Remove credential values from completed native run artifacts."""
import json
import os
from pathlib import Path
import re
import shutil
import tempfile


def redact_artifacts(root, environment):
    values = {value for name, value in environment.items()
              if value and len(value) >= 8 and any(marker in name.upper()
              for marker in ('API_KEY', 'AUTH_TOKEN', 'ACCESS_TOKEN', 'SECRET_KEY'))}
    variants = {text.encode() for value in values for text in
                (value, json.dumps(value, ensure_ascii=True)[1:-1])}
    if not variants:
        return []
    pattern = re.compile(b'|'.join(re.escape(value) for value in sorted(variants, key=len, reverse=True)))
    overlap = max(map(len, variants)) - 1
    changed = []
    for path in sorted(Path(root).rglob('*')):
        if path.is_symlink() or not path.is_file():
            continue
        temporary = None
        replaced = False
        try:
            with path.open('rb') as source, tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as target:
                temporary = Path(target.name)
                carry = b''
                while True:
                    chunk = source.read(1024 * 1024)
                    data = carry + chunk
                    limit = max(0, len(data) - overlap) if chunk else len(data)
                    for match in pattern.finditer(data):
                        if match.start() < limit:
                            limit = max(limit, match.end())
                    output, count = pattern.subn(b'[REDACTED_CREDENTIAL]', data[:limit])
                    replaced |= count > 0
                    target.write(output)
                    carry = data[limit:]
                    if not chunk:
                        break
            if replaced:
                shutil.copymode(path, temporary)
                os.replace(temporary, path)
                changed.append(str(path.relative_to(root)))
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return changed
