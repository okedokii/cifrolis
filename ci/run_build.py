#!/usr/bin/env python3
"""Bound a build attempt and distinguish resource exhaustion from code errors."""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys


def resource_failure(returncode, text, oom_before=0, oom_after=0):
    return returncode in (124, 137, -signal.SIGKILL) or oom_after > oom_before or bool(re.search(
        r'out of memory|cannot allocate memory|LLVM ERROR:.*memory|'
        r'signal: 9, SIGKILL|killed signal terminated program|No space left on device',
        text, re.I))


def oom_count():
    try:
        values = dict(line.split() for line in Path('/sys/fs/cgroup/memory.events').read_text().splitlines())
        return int(values.get('oom_kill', 0))
    except (OSError, ValueError):
        return 0


def main():
    root = Path(__file__).resolve().parents[1]
    work = Path(os.environ['FIREFOX_BUILD_ROOT'])
    mode = os.environ['RUCA_LTO']
    if mode not in ('thin', 'none'):
        raise ValueError('Unsupported LTO mode')
    before = oom_count()
    proc = subprocess.Popen(['bash', str(root / 'ci/build.sh')], start_new_session=True)
    try:
        code = proc.wait(timeout=300 * 60)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
        code = 124
    tail = ''
    for path in sorted((work / 'logs').glob('*.log')):
        with path.open(errors='replace') as stream:
            stream.seek(max(0, path.stat().st_size - 65536))
            content = stream.read()
        tail += content + '\n'
        if code:
            print(f'--- {path.name} (last 40 lines) ---\n' + '\n'.join(content.splitlines()[-40:]))
    exhausted = resource_failure(code, tail, before, oom_count())
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write(f'resource_failure={str(bool(code and exhausted)).lower()}\n')
    if code == 0:
        # R8 must have run; disabling optimization would omit this mapping.
        mappings = list((work / 'obj-arm64/gradle/build/mobile/android/fenix/app/outputs/mapping/release').glob('mapping.txt'))
        if not mappings or not all(p.stat().st_size for p in mappings):
            raise RuntimeError('R8 mapping is missing; refusing to claim an optimized release')
        report = dict(lto=mode, rust_opt_level=2, r8=True)
        (root / 'dist').mkdir(exist_ok=True)
        (root / 'dist/optimization.json').write_text(json.dumps(report) + '\n')
    return code if code > 0 else (128 - code if code else 0)


if __name__ == '__main__':
    sys.exit(main())
