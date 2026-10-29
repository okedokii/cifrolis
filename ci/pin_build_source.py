#!/usr/bin/env python3
"""Reserve a release tag before compilation; never move an existing tag."""
import json
import os
import re
import subprocess
from release_policy import choose_tag


def read_api(repo, path):
    return json.loads(subprocess.check_output(['gh', 'api', f'repos/{repo}/{path}']))


def tag_ref(repo, tag):
    matches = read_api(repo, f'git/matching-refs/tags/{tag}')
    exact = [item for item in matches if item['ref'] == f'refs/tags/{tag}']
    if len(exact) > 1:
        raise ValueError('Ambiguous release tag')
    return exact[0]['object'] if exact else None


def verify_tag(repo, tag, sha):
    target = tag_ref(repo, tag)
    if not target or target.get('type') != 'commit' or target['sha'] != sha:
        raise ValueError('Release tag does not point to the exact build commit')


def pin(repo, version, code, sha):
    code = int(code)
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Invalid source commit')
    pages = json.loads(subprocess.check_output([
        'gh', 'api', '--paginate', '--slurp', f'repos/{repo}/releases']))
    releases = [release for page in pages for release in page]
    tag = choose_tag(releases, version, code)
    target = tag_ref(repo, tag)
    # A failed build may already have reserved the plain version tag.
    # Keep it intact and give a later build its own tag.
    if target and (target.get('type') != 'commit' or target['sha'] != sha) and tag == f'v{version}':
        tag = f'v{version}-build.{code}'
        target = tag_ref(repo, tag)
    if any(release['tag_name'] == tag for release in releases):
        raise ValueError('Release already exists; refusing to overwrite it')
    if target:
        if target.get('type') != 'commit' or target['sha'] != sha:
            raise ValueError('Release tag already points elsewhere; refusing to replace it')
    else:
        subprocess.run(['gh', 'api', f'repos/{repo}/git/refs', '--method', 'POST',
                        '-f', f'ref=refs/tags/{tag}', '-f', f'sha={sha}'], check=True)
    verify_tag(repo, tag, sha)
    print(f'Build source retained: refs/tags/{tag} -> {sha}')
    return tag


if __name__ == '__main__':
    tag = pin(os.environ['GH_REPO'], os.environ['FIREFOX_VERSION'],
              os.environ['RUCA_VERSION_CODE'], os.environ['GITHUB_SHA'])
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write(f'tag={tag}\n')
