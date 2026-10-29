#!/usr/bin/env python3
"""Remove only explicitly retired source branches already preserved by release tags."""
import json
import os
from pathlib import Path
import re
import subprocess


def api(repo, path):
    return json.loads(subprocess.check_output(['gh', 'api', f'repos/{repo}/{path}']))


def retire(repo, snapshots):
    for item in snapshots:
        branch, tag, sha = item['branch'], item['tag'], item['sha']
        if not re.fullmatch(r'build-source/[0-9]+\.[0-9]+(?:\.[0-9]+)?-[0-9]+', branch):
            raise ValueError('Only explicitly listed build-source branches can be retired')
        if not re.fullmatch(r'[0-9a-f]{40}', sha):
            raise ValueError('Invalid preserved source commit')
        matches = api(repo, 'git/matching-refs/heads/' + branch)
        exact = [ref for ref in matches if ref['ref'] == 'refs/heads/' + branch]
        if not exact:
            continue
        if len(exact) != 1 or exact[0]['object']['sha'] != sha:
            raise ValueError('Source branch changed; refusing to delete it')
        target = api(repo, 'git/ref/tags/' + tag)['object']
        if target.get('type') != 'commit' or target['sha'] != sha:
            raise ValueError('Release tag does not preserve the branch commit')
        release = api(repo, 'releases/tags/' + tag)
        if release['draft'] or release['tag_name'] != tag:
            raise ValueError('Expected an existing published release')
        subprocess.run(['gh', 'api', f'repos/{repo}/git/refs/heads/{branch}',
                        '--method', 'DELETE'], check=True)
        print(f'Retired {branch}; exact source preserved by {tag}')


if __name__ == '__main__':
    request = json.loads(Path('ci/cleanup-request.json').read_text())
    retire(os.environ['GH_REPO'], request.get('retired_build_sources', []))
