#!/usr/bin/env python3
"""Remove a redundant optimization sentence from all existing release notes.

Only changes release descriptions, not releases, tags, files or assets.
"""
import json
import os
import subprocess


PHRASE = 'Оптимизация: Rust opt-level=2, R8; ThinLTO.'


def clean(body):
    if PHRASE not in body:
        return body
    # Preserve the surrounding paragraphs and machine-readable release marker.
    for newline in ('\r\n', '\n'):
        body = body.replace(newline + newline + PHRASE + newline, newline)
    return body.replace(PHRASE, '')


def main():
    repo = os.environ['GH_REPO']
    pages = json.loads(subprocess.check_output(
        ['gh', 'api', '--paginate', '--slurp', f'repos/{repo}/releases']))
    releases = [item for page in pages for item in page]
    for release in releases:
        old = release.get('body') or ''
        new = clean(old)
        if old == new:
            print(f"Unchanged: {release['tag_name']}")
            continue
        subprocess.run(['gh', 'api', '--method', 'PATCH',
                        f"repos/{repo}/releases/{release['id']}",
                        '-f', f'body={new}'], check=True, capture_output=True, text=True)
        print(f"Updated: {release['tag_name']}")


if __name__ == '__main__':
    main()
