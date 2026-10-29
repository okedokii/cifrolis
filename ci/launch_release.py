#!/usr/bin/env python3
"""Apply an owner-requested release reset once, then dispatch the build."""
import json
import os
from pathlib import Path
import subprocess
import urllib.request
from source_manifest import validate_version


def api(path, *args):
    return json.loads(subprocess.check_output(['gh', 'api', path, *args]))


def main():
    request = json.loads(Path('ci/launch-request.json').read_text())
    repo = os.environ['GH_REPO']
    with urllib.request.urlopen('https://product-details.mozilla.org/1.0/mobile_versions.json', timeout=60) as response:
        version = validate_version(json.load(response)['version'])
    if version != request['version']:
        raise ValueError('Latest Android stable changed; review the requested version before deleting anything')
    releases = [r for page in api(f'repos/{repo}/releases', '--paginate', '--slurp') for r in page]
    expected = request['delete_release']
    # A snapshot guard ensures this request cannot delete any newer release.
    if len(releases) != 1 or releases[0]['id'] != expected['id'] or releases[0]['tag_name'] != expected['tag']:
        raise ValueError('Existing releases differ from the owner-approved single-release snapshot')
    actual = sorted((a['id'], a['name']) for a in releases[0]['assets'])
    if actual != sorted((a['id'], a['name']) for a in expected['assets']):
        raise ValueError('Release assets changed since the removal request')
    # Verify the workflow exists before deleting the old release.
    api(f'repos/{repo}/actions/workflows/build.yml')
    subprocess.run(['gh', 'api', f'repos/{repo}/releases/{expected["id"]}', '--method', 'DELETE'], check=True)
    print(f'Deleted release {expected["tag"]} ({expected["id"]}); Git tag retained')
    subprocess.run(['gh', 'workflow', 'run', 'build.yml', '--repo', repo, '--ref', 'main',
                    '-f', f'version={version}', '-f', 'publish=true', '-f', 'unsigned=false'], check=True)
    print(f'Dispatched optimized Цифролис {version}; stable publication and F-Droid are enabled')


if __name__ == '__main__':
    main()
