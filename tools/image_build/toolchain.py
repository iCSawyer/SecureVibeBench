"""Prepare a pinned container toolchain without requiring uv on the host."""
import hashlib
import json
from pathlib import Path
import urllib.request
import tempfile
import zipfile


def copy_uv(destination, cache):
    lock=json.loads(Path(__file__).with_name('toolchain-lock.json').read_text())
    cache.mkdir(parents=True,exist_ok=True)
    wheel=cache/('uv-'+lock['uv_version']+'.whl')
    if not wheel.exists():
        with tempfile.NamedTemporaryFile(dir=cache, prefix='.uv-', suffix='.download', delete=False) as stream:
            temporary = Path(stream.name)
        try:
            with urllib.request.urlopen(lock['url'],timeout=120) as response, temporary.open('wb') as out:
                import shutil
                shutil.copyfileobj(response,out)
            if hashlib.sha256(temporary.read_bytes()).hexdigest()!=lock['sha256']:
                raise ValueError('uv download checksum mismatch')
            temporary.replace(wheel)
        finally:
            temporary.unlink(missing_ok=True)
    if hashlib.sha256(wheel.read_bytes()).hexdigest()!=lock['sha256']:
        raise ValueError('Cached uv checksum mismatch')
    with zipfile.ZipFile(wheel) as archive:
        matches=[name for name in archive.namelist() if name.endswith('.data/scripts/uv')]
        if len(matches)!=1:raise ValueError('Unexpected uv wheel layout')
        destination.write_bytes(archive.read(matches[0]))
    destination.chmod(0o755)
    return lock


def configure_python(dockerfile):
    """Keep the verifier runtime; migrate older recipes that installed an agent."""
    lines = dockerfile.read_text().splitlines()
    migrated = []
    for line in lines:
        if line.startswith('COPY svb/agent-requirements.lock ') or line == 'ENV UV_OFFLINE=1':
            continue
        if line.startswith('ENV ') and 'UV_CONSTRAINT=/opt/svb/agent-requirements.lock' in line:
            migrated.append('ENV PATH="/root/.local/bin:${PATH}" UV_PYTHON_INSTALL_DIR=/opt/svb/python-downloads')
            continue
        if line == 'COPY toolchain/python /opt/svb/python':
            continue
        if line.startswith('RUN uv python install 3.12.12 && '):
            migrated.append('RUN uv python install 3.12.12 && ln -s "$(dirname "$(dirname "$(uv python find 3.12.12)")")" /opt/svb/python')
            continue
        migrated.append(line)
    dockerfile.write_text('\n'.join(migrated) + '\n')



def configure_package_installation(dockerfile):
    """Use platform-compatible wheels on historical task operating systems."""
    source = dockerfile.read_text()
    policy = 'ENV UV_NO_BUILD=1'
    if policy in source.splitlines():
        return
    lines = source.splitlines()
    index = next((i for i, line in enumerate(lines) if line.startswith(('ENTRYPOINT ', 'CMD '))), len(lines))
    lines.insert(index, policy)
    dockerfile.write_text('\n'.join(lines) + '\n')
