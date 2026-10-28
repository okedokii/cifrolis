#!/usr/bin/env python3
"""Build a signed binary F-Droid repo; only public output goes to Pages."""
import base64
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

APP_ID = 'io.github.okedokii.cifrolis'
MAX_VERSIONS = 3
MAX_SITE_BYTES = 900 * 1024 * 1024


def run(*args, **kwargs):
    return subprocess.check_output(list(args), text=True, **kwargs)


def release_candidates(releases):
    """Never use drafts, prereleases or unrelated release assets."""
    result = []
    for release in releases:
        if release.get('draft') or release.get('prerelease'):
            continue
        apks = [a for a in release.get('assets', [])
                if re.fullmatch(r'firefox-[0-9]+\.[0-9]+(?:\.[0-9]+)?-arm64-ruca\.apk', a['name'])]
        if not apks:
            continue
        if len(apks) != 1:
            raise ValueError('Expected one ARM64 APK per stable release')
        if apks[0].get('state') != 'uploaded':
            raise ValueError('Release APK upload is incomplete')
        result.append((release, apks[0]))
    return sorted(result, key=lambda item: item[0].get('published_at') or '', reverse=True)[:20]


def apk_identity(badging):
    match = re.search(r"^package: name='([^']+)' versionCode='([0-9]+)' versionName='([^']+)'", badging, re.M)
    if not match:
        raise ValueError('Cannot read APK identity')
    return match[1], int(match[2]), match[3]


def verify_digest(apk, expected):
    with apk.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if not re.fullmatch(r'[0-9a-fA-F]{64}', expected) or actual != expected.lower():
        raise ValueError('Release APK checksum does not match')


def verify_signer(output, expected):
    signers = re.findall(r'^Signer #[0-9]+ certificate SHA-256 digest: ([0-9a-fA-F]+)$', output, re.M)
    if [s.lower() for s in signers] != [expected.lower()]:
        raise ValueError('APK signing certificate differs from pinned identity')


def select_versions(verified):
    versions = {}
    for item in verified:
        code = item['code']
        if code <= 0:
            raise ValueError('Invalid APK versionCode')
        if code in versions:
            if versions[code]['sha256'] != item['sha256']:
                raise ValueError('Different APKs have the same versionCode')
            continue
        versions[code] = item
    return sorted(versions.values(), key=lambda item: item['code'], reverse=True)[:MAX_VERSIONS]


def main():
    os.umask(0o077)
    root = Path(__file__).resolve().parents[1]
    identity = json.loads((root / 'ci/signing-identity.json').read_text())
    if identity['application_id'] != APP_ID:
        raise ValueError('Unexpected application ID in pinned identity')
    repository = os.environ['GH_REPO']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Invalid GitHub repository')
    owner, name = repository.split('/')
    repo_url = f'https://{owner.lower()}.github.io/{name}/fdroid/repo'
    add_url = repo_url + '?fingerprint=' + identity['signer_sha256'].upper()
    work = Path(os.environ['RUNNER_TEMP']) / 'cifrolis-fdroid'
    public = root / 'public'
    if work.exists() or public.exists():
        raise ValueError('Use fresh working and public directories')
    work.mkdir(mode=0o700)
    try:
        # Keep private material outside public/ and never upload work/ as an artifact.
        password = os.environ['RUCA_KEYSTORE_PASSWORD']
        if not password or '\n' in password or '\r' in password:
            raise ValueError('Missing or invalid signing password')
        keystore = work / 'signing.p12'
        keystore.write_bytes(base64.b64decode(os.environ['RUCA_KEYSTORE_B64'], validate=True))
        password_file = work / 'password.txt'
        password_file.write_text(password + '\n')
        certificate = work / 'signer.der'
        subprocess.run(['keytool', '-exportcert', '-alias', identity['key_alias'],
                        '-keystore', str(keystore), '-storepass:file', str(password_file),
                        '-file', str(certificate)], check=True, capture_output=True)
        if hashlib.sha256(certificate.read_bytes()).hexdigest() != identity['signer_sha256']:
            raise ValueError('Repository signing key differs from pinned identity')

        pages = json.loads(run('gh', 'api', '--paginate', '--slurp', f'repos/{repository}/releases?per_page=100'))
        verified = []
        for index, (release, asset) in enumerate(release_candidates([r for page in pages for r in page])):
            download = work / f'download-{index}'
            download.mkdir()
            run('gh', 'release', 'download', '--repo', repository, '--dir', str(download),
                '--pattern', asset['name'], '--', release['tag_name'])
            apk = download / asset['name']
            package, code, version = apk_identity(run('aapt', 'dump', 'badging', str(apk)))
            if package != APP_ID:
                print(f'Skipping legacy package {package} from {release["tag_name"]}')
                shutil.rmtree(download)
                continue
            checksum_name = asset['name'] + '.sha256'
            if checksum_name not in {a['name'] for a in release['assets']}:
                raise ValueError('Published APK is missing its checksum')
            run('gh', 'release', 'download', '--repo', repository, '--dir', str(download),
                '--pattern', checksum_name, '--', release['tag_name'])
            checksum = (download / checksum_name).read_text().split()[0]
            verify_digest(apk, checksum)
            if asset.get('digest'):
                if asset['digest'] != 'sha256:' + checksum.lower():
                    raise ValueError('GitHub asset digest differs from checksum')
            verify_signer(run('apksigner', 'verify', '--print-certs', str(apk)), identity['signer_sha256'])
            verified.append(dict(path=apk, code=code, version=version, sha256=checksum.lower()))

        selected = select_versions(verified)
        binary_repo = work / 'repo'
        binary_repo.mkdir()
        shutil.copyfile(root / 'assets/icon.png', work / 'fdroid-icon.png')
        shutil.copytree(root / 'fdroid/metadata', work / 'metadata')
        for item in selected:
            shutil.copyfile(item['path'], binary_repo / f'{APP_ID}_{item["code"]}.apk')
        if selected:
            metadata = work / 'metadata' / f'{APP_ID}.yml'
            with metadata.open('a') as stream:
                stream.write('\nCurrentVersion: ' + json.dumps(selected[0]['version']) + '\n')
                stream.write(f'CurrentVersionCode: {selected[0]["code"]}\n')
        # JSON is valid YAML, including correctly escaped passwords.
        config = dict(repo_url=repo_url, repo_name='Цифролис',
                      repo_description='Неофициальные сборки Firefox для Android с сертификатами Минцифры.',
                      repo_keyalias=identity['key_alias'], keystore=str(keystore),
                      keystorepass=password, keypass=password,
                      archive_older=0, make_current_version_link=False)
        (work / 'config.yml').write_text(json.dumps(config, ensure_ascii=False))
        subprocess.run(['fdroid', 'update'], cwd=work, check=True)
        # Both old and modern clients need signed indexes, not just JSON.
        if not (binary_repo / 'index-v1.jar').is_file() or not (binary_repo / 'entry.jar').is_file():
            raise ValueError('F-Droid did not produce the signed repository indexes')
        shutil.copytree(binary_repo, public / 'fdroid/repo')
        (public / '.nojekyll').touch()
        notice = ('Доступных версий: ' + str(len(selected)) if selected else
                  'Ожидается первый опубликованный релиз с пакетом ' + APP_ID + '.')
        (public / 'index.html').write_text(
            '<!doctype html><html lang="ru"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Цифролис — F-Droid</title><main><h1>Цифролис</h1>'
            '<p>Неофициальный репозиторий F-Droid.</p><p>' + html.escape(notice) + '</p>'
            '<p><a href="' + html.escape(add_url, quote=True) + '">Добавить в F-Droid</a></p>'
            '<p>В F-Droid откройте настройки репозиториев и добавьте адрес:</p><p><code>'
            + html.escape(repo_url) + '</code></p><p>SHA-256 сертификата: <code>'
            + identity['signer_sha256'].upper() + '</code></p></main></html>')
        if sum(p.stat().st_size for p in public.rglob('*') if p.is_file()) > MAX_SITE_BYTES:
            raise ValueError('Repository exceeds the Pages size budget')
        summary = Path(os.environ['GITHUB_STEP_SUMMARY'])
        with summary.open('a') as stream:
            stream.write(f'### Цифролис F-Droid\n\n{notice}\n\n[Добавить репозиторий]({add_url})\n')
        print(f'Prepared signed repository: {len(selected)} versions; {repo_url}')
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
