#!/usr/bin/env python3
import os
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
work=Path(os.environ['FIREFOX_BUILD_ROOT'])
files=list((work/'obj-arm64/aarch64-linux-android/release/build').glob('trust-anchors-*/out/builtins.rs'))
if not files:
    raise RuntimeError('No generated Android trust-anchors builtins.rs; inspect changed upstream build layout')
for i, path in enumerate(sorted(files)):
    subprocess.run([str(work/'verify-venv/bin/python'),str(root/'kit/scripts/verify_generated_builtins.py'),str(path),
                    '--report',str(work/f'logs/generated-builtins-{i}.json')], check=True)
