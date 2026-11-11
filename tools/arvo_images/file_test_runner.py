"""Report every upstream file fixture, including failures after make check stops."""
import os
from pathlib import Path
import subprocess


def report(name, code):
    print('SVB_FILE_CASE %s %s' % (name, 'PASS' if code == 0 else 'FAIL'), flush=True)
    return code != 0


def main():
    repo = Path.cwd()
    jobs = os.environ.get('CMAKE_BUILD_PARALLEL_LEVEL', '8')
    failed = report('upstream-make-check', subprocess.run(['make', '-j' + jobs, 'check']).returncode)
    tests = repo / 'tests'
    binary = tests / 'test'
    cases = sorted(tests.glob('*.testfile'))
    if not binary.is_file() or not cases:
        raise RuntimeError('Upstream test executable or fixtures are missing')
    default_magic = repo / 'magic/magic'
    environment = {**os.environ, 'TZ': 'UTC', 'MAGIC': str(default_magic)}
    failed |= report('default-magic', subprocess.run([str(binary)], cwd=tests, env=environment).returncode)
    for case in cases:
        magic = case.with_suffix('.magic')
        expected = case.with_suffix('.result')
        env = {**environment, 'MAGIC': str(magic if magic.is_file() else default_magic)}
        code = subprocess.run([str(binary), str(case), str(expected)], cwd=tests, env=env).returncode
        failed |= report(case.name, code)
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
