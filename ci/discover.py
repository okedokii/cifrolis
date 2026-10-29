#!/usr/bin/env python3
import json
import os
import re
import subprocess
import urllib.request
from source_manifest import validate_version
from release_policy import identity
from apk_names import has_complete_apk

version = os.environ.get('REQUESTED_VERSION', '')
if not version:
    with urllib.request.urlopen('https://product-details.mozilla.org/1.0/mobile_versions.json', timeout=60) as r:
        version = json.load(r)['version']
validate_version(version)
# Inspect all releases, including drafts, so a successful draft stops retries.
result = subprocess.run(['gh', 'api', '--paginate', '--slurp', f'repos/{os.environ["GITHUB_REPOSITORY"]}/releases'],
                        text=True, capture_output=True, check=True)
releases = [r for page in json.loads(result.stdout) for r in page]
already = any(identity(r) is not None and identity(r)[0] == version and
              has_complete_apk(r.get('assets', []), version)
              for r in releases)
manual = os.environ['GITHUB_EVENT_NAME'] == 'workflow_dispatch'
build = manual or not already
code = 2020000000 + int(os.environ['GITHUB_RUN_NUMBER'])
previous = [i[1] for r in releases if (i := identity(r)) is not None]
if build and previous and code <= max(previous):
    raise ValueError('versionCode would not increase. Preserve workflow run counter or review versionCode base before migration.')
if code > 2100000000:
    raise ValueError('versionCode range exhausted')
with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
    output.write(f'version={version}\nbuild={str(build).lower()}\ncode={code}\n')
print(f'Android stable={version}; already built={already}; build={build}; versionCode={code}')
