#!/usr/bin/env python3
"""Restore only the validated unsigned APK and public reports for signing."""
import hashlib,json,os,shutil,tarfile
from pathlib import Path, PurePosixPath
from source_manifest import validate_version

artifact=Path('trial-input').resolve()
work=Path(os.environ['FIREFOX_BUILD_ROOT']);work.mkdir(parents=True,exist_ok=True)
with tarfile.open(artifact/'verification.tar.gz') as archive:
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if (path.is_absolute() or not path.parts or path.parts[0] != 'verification'
                or '..' in path.parts or not (member.isdir() or member.isfile())
                or (len(path.parts) == 1 and not member.isdir())):
            raise ValueError(f'Unexpected verification archive path or type: {member.name}')
    archive.extractall(work,filter='data')
report=json.loads((work/'verification/manifest-check.json').read_text())
version=validate_version(report['version_name'])
code=int(report['version_code'])
if report['status']!='passed' or report['package']!='io.github.okedokii.cifrolis' or not 2016191386 < code <= 2100000000:
    raise ValueError('Invalid unsigned trial identity or manifest report')
apks=list(artifact.glob('*.apk'))
if len(apks)!=1:
    raise ValueError('Expected exactly one unsigned trial APK')
with apks[0].open('rb') as stream:
    if hashlib.file_digest(stream,'sha256').hexdigest()!=report['apk_sha256']:
        raise ValueError('Unsigned APK differs from validated trial report')
(work/'unsigned-apk.path').write_text(str(apks[0])+'\n')
shutil.copyfile(work/'verification/downloads.json',work/'downloads.json')
logs=work/'logs';logs.mkdir(exist_ok=True)
for p in (work/'verification').glob('generated-builtins-*.json'):
    if json.loads(p.read_text())['status']!='passed':
        raise ValueError('Generated trust-anchors table failed validation')
    shutil.copyfile(p,logs/p.name)
if not list(logs.glob('generated-builtins-*.json')):
    raise ValueError('Generated trust-anchors report missing')
shutil.copyfile(work/'verification/source-certificates.json',logs/'source-certificates.json')
with open(os.environ['GITHUB_ENV'],'a') as env:
    env.write(f'FIREFOX_VERSION={version}\nRUCA_VERSION_CODE={code}\n')
print(f'Validated trial restored: Android {version}, versionCode {code}')
