#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
# This threshold is a conservative project guard, not a measured build requirement.
python3 - "$FIREFOX_BUILD_ROOT" <<'PY'
from pathlib import Path
import shutil,sys
p=Path(sys.argv[1]);p.mkdir(parents=True,exist_ok=True)
free=shutil.disk_usage(p).free
if free < 45 * 1024**3:
    raise SystemExit(f'Need at least 45 GiB free (project estimate); have {free/1024**3:.1f} GiB. Use a larger/self-hosted runner.')
PY
bash "$ROOT/kit/prepare.sh"
bash "$ROOT/kit/build.sh"
