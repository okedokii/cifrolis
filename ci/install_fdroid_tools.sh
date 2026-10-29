#!/usr/bin/env bash
set -euo pipefail
sudo apt-get update
sudo apt-get install -y --no-install-recommends python3-venv aapt apksigner
python3 -m venv "$RUNNER_TEMP/fdroid-tools"
"$RUNNER_TEMP/fdroid-tools/bin/python" -m pip install --disable-pip-version-check \
  'fdroidserver==2.4.5' 'androguard==4.1.4'
printf '%s\n' "$RUNNER_TEMP/fdroid-tools/bin" >> "$GITHUB_PATH"
"$RUNNER_TEMP/fdroid-tools/bin/fdroid" --version
