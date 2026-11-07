"""The historical freeze test must not bypass the container's build budget."""
from pathlib import Path
import runpy
import sys

import pytest


def test_nested_make_job_requests_are_bounded(tmp_path, monkeypatch):
    import os
    script=Path(__file__).parents[1]/'tools/cpython_image/make'
    monkeypatch.setenv('SVB_TEST_JOBS','8')
    monkeypatch.setenv('SVB_LOG_DIR',str(tmp_path))
    monkeypatch.setattr(sys,'argv',['make','-C','build','-j149','--jobs=224','test'])
    seen=[]
    def execute(binary, arguments):
        seen.extend(arguments)
        raise SystemExit(0)
    monkeypatch.setattr(os,'execv',execute)
    with pytest.raises(SystemExit):runpy.run_path(str(script),run_name='__main__')
    assert seen==['/usr/bin/make','-j8','-C','build','test']
    assert (tmp_path/'make-jobs.jsonl').is_file()
