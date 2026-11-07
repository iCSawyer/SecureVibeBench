"""Toolchain downloads are safe across concurrent task preparation."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from threading import Barrier
import zipfile

from tools.image_build import toolchain


def test_concurrent_first_downloads_do_not_share_a_temporary_file(tmp_path, monkeypatch):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as archive:
        archive.writestr('uv-1.data/scripts/uv', b'fake uv executable')
    wheel = data.getvalue()
    lock = {'uv_version': '1', 'url': 'https://example.invalid/uv.whl',
            'sha256': hashlib.sha256(wheel).hexdigest(), 'python_version': '3.12'}
    (tmp_path / 'toolchain-lock.json').write_text(json.dumps(lock))
    monkeypatch.setattr(toolchain, '__file__', str(tmp_path / 'toolchain.py'))
    barrier = Barrier(2)
    def download(*args, **kwargs):
        barrier.wait(timeout=5)
        return io.BytesIO(wheel)
    monkeypatch.setattr(toolchain.urllib.request, 'urlopen', download)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(toolchain.copy_uv, tmp_path / ('uv-' + str(i)), tmp_path / 'cache') for i in range(2)]
        for future in futures:
            assert future.result() == lock
    assert (tmp_path / 'uv-0').read_bytes() == (tmp_path / 'uv-1').read_bytes() == b'fake uv executable'
    assert hashlib.sha256((tmp_path / 'cache/uv-1.whl').read_bytes()).hexdigest() == lock['sha256']
    assert not list((tmp_path / 'cache').glob('*.download'))
