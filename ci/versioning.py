#!/usr/bin/env python3
import os
from pathlib import Path
from source_manifest import validate_version

def apply(source, version, code):
    validate_version(version)
    if not 2016191386 < code <= 2100000000:
        raise ValueError('versionCode must exceed existing APK and fit Android limit')
    p = Path(source) / 'mobile/android/fenix/app/build.gradle'
    s = p.read_text()
    old = '                output.versionName.set(versionName)\n                output.versionCode.set(versionCodeOverride)'
    new = (f'                output.versionName.set(buildType == "release" ? "{version}" : versionName)\n'
           f'                output.versionCode.set(buildType == "release" ? {code} : versionCodeOverride)')
    if s.count(old) != 1:
        raise ValueError('Versioning hook changed; review upstream build.gradle')
    p.write_text(s.replace(old, new))

if __name__ == '__main__':
    apply(os.environ['FIREFOX_SOURCE_DIR'], os.environ['FIREFOX_VERSION'], int(os.environ['RUCA_VERSION_CODE']))
