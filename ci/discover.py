#!/usr/bin/env python3
import json
import os
import subprocess
from source_manifest import validate_version
from release_policy import identity
from apk_names import has_complete_apk
from mobile_versions import latest_stable, version_key


def requested_version(event, requested):
    # Schedule has no workflow_dispatch inputs. Never interpret an expression's
    # boolean false (serialized as a string by Actions) as a version.
    if event == 'schedule' or not requested:
        return latest_stable()
    return validate_version(requested)


def decision(releases, version, event, run_number):
    known = [(r, identity(r)) for r in releases if not r.get('prerelease')]
    already = any(i is not None and i[0] == version and
                  has_complete_apk(r.get('assets', []), version)
                  for r, i in known)
    # Keep complete drafts for explicit manual review, as before.
    # A stale Mozilla mirror must not trigger an automatic downgrade.
    published = [i[0] for r, i in known if i and not r.get('draft') and
                 has_complete_apk(r.get('assets', []), i[0])]
    stale = bool(published and version_key(version) < max(map(version_key, published)))
    build = event == 'workflow_dispatch' or (not already and not stale)
    code = 2020000000 + run_number
    previous = [i[1] for r in releases if (i := identity(r)) is not None]
    if build and previous and code <= max(previous):
        raise ValueError('versionCode would not increase. Preserve workflow run counter or review versionCode base before migration.')
    if code > 2100000000:
        raise ValueError('versionCode range exhausted')
    print(f'Android stable={version}; already built={already}; stale={stale}; build={build}; versionCode={code}')
    return build, code


def main():
    event = os.environ['GITHUB_EVENT_NAME']
    version = requested_version(event, os.environ.get('REQUESTED_VERSION', ''))
    result = subprocess.run(['gh', 'api', '--paginate', '--slurp', f'repos/{os.environ["GITHUB_REPOSITORY"]}/releases'],
                            text=True, capture_output=True, check=True)
    releases = [r for page in json.loads(result.stdout) for r in page]
    build, code = decision(releases, version, event, int(os.environ['GITHUB_RUN_NUMBER']))
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write(f'version={version}\nbuild={str(build).lower()}\ncode={code}\n')


if __name__ == '__main__':
    main()
