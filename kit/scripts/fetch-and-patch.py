#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import subprocess

kit = Path(os.environ['FIREFOX_KIT_ROOT'])
work = Path(os.environ['FIREFOX_BUILD_ROOT'])
state = Path(os.environ['MOZBUILD_STATE_PATH'])
source = Path(os.environ['FIREFOX_SOURCE_DIR'])
downloads = work / 'downloads'
downloads.mkdir(parents=True, exist_ok=True)
manifest = json.loads((work / 'downloads.json').read_text())


def digest(path, algorithm):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def install(record, target_parent):
    target = target_parent / record['directory']
    marker = target_parent / ('.rebuild-' + record['name'] + '.json')
    identity = {key: record[key] for key in ('url', 'algorithm', 'digest')}
    if target.exists():
        if not marker.is_file() or json.loads(marker.read_text()) != identity:
            raise RuntimeError(f'{target} exists without the matching verified extraction marker. Use a fresh FIREFOX_BUILD_ROOT.')
        return
    archive = downloads / record['filename']
    if not archive.exists():
        partial = archive.with_suffix(archive.suffix + '.part')
        subprocess.run(['curl', '--fail', '--location', '--proto', '=https', '--tlsv1.2',
                        '--retry', '3', '--continue-at', '-', '--output', str(partial), record['url']], check=True)
        if digest(partial, record['algorithm']) != record['digest']:
            raise RuntimeError(f'Checksum mismatch: {partial}')
        partial.rename(archive)
    if archive.stat().st_size != record['size_bytes'] or digest(archive, record['algorithm']) != record['digest']:
        raise RuntimeError(f'Size or checksum mismatch: {archive}')
    target_parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['tar', '--extract', '--file', str(archive), '--directory', str(target_parent), '--no-same-owner'], check=True)
    if not target.is_dir():
        raise RuntimeError(f'Archive did not create expected directory: {target}')
    marker.write_text(json.dumps(identity, indent=2) + '\n')
    if os.environ.get('FIREFOX_KEEP_DOWNLOADS', '0') != '1':
        archive.unlink()


if 'source_git' in manifest:
    record = manifest['source_git']
    if source.exists():
        raise RuntimeError('Git source already exists; use a fresh FIREFOX_BUILD_ROOT')
    subprocess.run(['git', 'init', str(source)], check=True)
    subprocess.run(['git', 'remote', 'add', 'origin', record['repository']], cwd=source, check=True)
    subprocess.run(['git', 'fetch', '--depth', '1', 'origin', 'refs/tags/' + record['tag']], cwd=source, check=True)
    fetched = subprocess.check_output(['git', 'rev-parse', 'FETCH_HEAD^{commit}'], cwd=source, text=True).strip()
    if fetched != record['commit']:
        raise RuntimeError('Android release tag changed between resolution and fetch')
    subprocess.run(['git', 'checkout', '--detach', fetched], cwd=source, check=True)
    actual = (source / 'mobile/android/version.txt').read_text().strip()
    if actual != manifest['firefox_version']:
        raise RuntimeError(f'Android source version differs: {actual}')

for record in manifest['archives']:
    install(record, work if record['name'] == 'source' else state)

for name in ('build-configuration.patch', 'gradle-environment.patch', 'private-release.patch', 'manifest-initializer.patch', 'gkrust-low-memory.patch'):
    patch = kit / 'patches' / name
    command = ['patch', '--batch', '--fuzz=0', '-p1', '-i', str(patch)]
    forward = subprocess.run(command + ['--forward', '--dry-run'], cwd=source, capture_output=True, text=True)
    if forward.returncode == 0:
        subprocess.run(command + ['--forward'], cwd=source, check=True)
    else:
        reverse = subprocess.run(command + ['--reverse', '--dry-run'], cwd=source, capture_output=True, text=True)
        if reverse.returncode:
            raise RuntimeError(f'Patch cannot be applied or verified as already applied: {name}\n{forward.stdout}\n{forward.stderr}')

(source / 'build/gkrust-codegen-wrapper.sh').chmod(0o755)

runtime = state / 'clang/lib/clang/22/lib'
expected = runtime / 'wasi/libclang_rt.builtins-wasm32.a'
alias = runtime / 'wasm32-unknown-wasip1/libclang_rt.builtins.a'
if not expected.is_file():
    raise RuntimeError(f'Missing WASI compiler runtime: {expected}')
if not alias.exists():
    alias.parent.mkdir(parents=True, exist_ok=True)
    alias.symlink_to('../wasi/libclang_rt.builtins-wasm32.a')
print('Verified source, Clang and WASI extracted; exact patches applied.')
