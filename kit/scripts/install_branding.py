#!/usr/bin/env python3
"""Install the selected RU CA logo before compiling Fenix (Android 26+)."""
import argparse
import base64
import hashlib
from pathlib import Path
import re
import xml.etree.ElementTree as ET

LOGO_SHA256 = '551c8ffc150a1648b997ab1774e8cafa1dadd64aa629be97439538b48dac698d'
ANDROID = '{http://schemas.android.com/apk/res/android}'
ICON = '@mipmap/ruca_launcher'


def install(source_root):
    kit = Path(__file__).resolve().parents[1]
    encoded = (kit / 'branding/logo.png.b64').read_bytes()
    logo = base64.b64decode(b''.join(encoded.split()), validate=True)
    if hashlib.sha256(logo).hexdigest() != LOGO_SHA256:
        raise RuntimeError('Selected RU CA logo checksum mismatch')
    app = source_root / 'mobile/android/fenix/app'
    manifest = app / 'src/main/AndroidManifest.xml'
    text = manifest.read_text()
    application = ET.fromstring(text).find('application')
    if application is None:
        raise RuntimeError('Fenix application element is missing')
    for attribute, expected in [('icon', '@mipmap/ic_launcher'),
                                ('roundIcon', '@mipmap/ic_launcher_round')]:
        if application.get(ANDROID + attribute) not in (expected, ICON):
            raise RuntimeError(f'Unexpected Fenix application {attribute}; review branding')
    # Replace only application defaults, preserving optional user-selected icons.
    pattern = r'(<application\b[^>]*)(>)'
    def replace(match):
        tag = match[1]
        for attribute in ('icon', 'roundIcon'):
            tag, count = re.subn(r'(android:' + attribute + r'=\")[^\"]*(\")',
                                 lambda value: value[1] + ICON + value[2], tag)
            if count != 1:
                raise RuntimeError(f'Expected exactly one application {attribute}')
        return tag + match[2]
    updated, count = re.subn(pattern, replace, text, count=1)
    if count != 1:
        raise RuntimeError('Cannot locate Fenix application opening tag')
    res = app / 'src/release/res'
    files = {
        'drawable-nodpi/ruca_logo.png': logo,
        'drawable/ruca_launcher_foreground.xml': b'''<?xml version="1.0" encoding="utf-8"?>
<inset xmlns:android="http://schemas.android.com/apk/res/android"
    android:insetLeft="21%" android:insetTop="21%"
    android:insetRight="21%" android:insetBottom="21%">
    <bitmap android:src="@drawable/ruca_logo" android:gravity="fill"
        android:filter="true" />
</inset>
''',
        'mipmap-anydpi-v26/ruca_launcher.xml': b'''<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ruca_launcher_background" />
    <foreground android:drawable="@drawable/ruca_launcher_foreground" />
</adaptive-icon>
''',
        'values/ruca_branding.xml': b'''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="ruca_launcher_background">#F0F3FA</color>
</resources>
''',
    }
    for relative, content in files.items():
        target = res / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    manifest.write_text(updated)
    print(f'Installed RU CA logo variant 2: {LOGO_SHA256}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    install(parser.parse_args().source_root)
