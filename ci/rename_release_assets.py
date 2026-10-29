#!/usr/bin/env python3
"""Apply an explicit asset-name migration without changing the signed APK."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from apk_names import apk_name


def api(repo, path, *args):
    return json.loads(subprocess.check_output(['gh', 'api', f'repos/{repo}/{path}', *args]))


def checksum_text(digest, name):
    return f'{digest}  {name}\n'


def validate_apk(asset, request):
    if (asset['id'] != request['apk_id'] or asset['size'] != request['apk_size']
            or asset.get('digest') != 'sha256:' + request['apk_sha256']
            or asset['state'] != 'uploaded'):
        raise ValueError('Published APK differs from the approved snapshot')


def migrate(repo, request):
    release_id = request['release_id']
    release = api(repo, f'releases/{release_id}')
    if release['tag_name'] != request['tag'] or release['draft']:
        raise ValueError('Expected the approved published release')
    old_name = f'firefox-{request["version"]}-arm64-ruca.apk'
    new_name = apk_name(request['version'])
    apks = [a for a in release['assets'] if a['id'] == request['apk_id']]
    if len(apks) != 1 or apks[0]['name'] not in (old_name, new_name):
        raise ValueError('APK asset identity or name changed')
    validate_apk(apks[0], request)
    old_checksums = [a for a in release['assets'] if a['id'] == request['checksum_id']]
    if old_checksums and (old_checksums[0]['name'] != old_name + '.sha256'
                          or old_checksums[0].get('digest') != request['checksum_digest']):
        raise ValueError('Original checksum asset changed')
    target_name = new_name + '.sha256'
    expected = checksum_text(request['apk_sha256'], new_name)
    checksum_digest = 'sha256:' + hashlib.sha256(expected.encode()).hexdigest()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        # Keep the original checksum until a verified replacement is uploaded.
        if old_checksums:
            subprocess.run(['gh', 'release', 'download', '--repo', repo, '--dir', directory,
                            '--pattern', old_name + '.sha256', '--', request['tag']], check=True)
            original = (root / (old_name + '.sha256')).read_text()
            if original != checksum_text(request['apk_sha256'], old_name):
                raise ValueError('Original checksum contents differ from the APK snapshot')
        if apks[0]['name'] != new_name:
            updated = api(repo, f'releases/assets/{request["apk_id"]}', '--method', 'PATCH',
                          '-f', 'name=' + new_name)
            validate_apk(updated, request)
            if updated['name'] != new_name:
                raise ValueError('APK rename failed')
        targets = [a for a in release['assets'] if a['name'] == target_name]
        if not targets:
            (root / target_name).write_text(expected)
            subprocess.run(['gh', 'release', 'upload', request['tag'], str(root / target_name),
                            '--repo', repo], check=True)
        current = api(repo, f'releases/{release_id}')
        targets = [a for a in current['assets'] if a['name'] == target_name]
        if (len(targets) != 1 or targets[0].get('digest') != checksum_digest
                or targets[0]['state'] != 'uploaded'):
            raise ValueError('Replacement checksum was not uploaded correctly')
        verify_dir = root / 'verify'
        verify_dir.mkdir()
        subprocess.run(['gh', 'release', 'download', '--repo', repo, '--dir', str(verify_dir),
                        '--pattern', target_name, '--', request['tag']], check=True)
        if (verify_dir / target_name).read_text() != expected:
            raise ValueError('Downloaded replacement checksum is incorrect')
        if old_checksums:
            subprocess.run(['gh', 'api', f'repos/{repo}/releases/assets/{request["checksum_id"]}',
                            '--method', 'DELETE'], check=True)
    final = api(repo, f'releases/{release_id}')
    untouched = lambda r: {(a['id'], a['name'], a['size'], a.get('digest'))
                          for a in r['assets']
                          if a['id'] not in (request['apk_id'], request['checksum_id'])
                          and a['name'] != target_name}
    if untouched(final) != untouched(release):
        raise ValueError('An unrelated release asset changed')
    final_apk = next(a for a in final['assets'] if a['id'] == request['apk_id'])
    validate_apk(final_apk, request)
    if final_apk['name'] != new_name or any(a['name'] == old_name + '.sha256' for a in final['assets']):
        raise ValueError('Asset migration is incomplete')
    print(f'Renamed signed APK without changing bytes: {new_name}')


if __name__ == '__main__':
    request = json.loads(Path('ci/cleanup-request.json').read_text())
    migration = request.get('rename_release_assets')
    if migration:
        repo = os.environ['GH_REPO']
        migrate(repo, migration)
        subprocess.run(['gh', 'workflow', 'run', 'fdroid.yml', '--repo', repo, '--ref', 'main'], check=True)
