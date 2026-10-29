"""Current APK names and compatibility with releases published before rebranding."""
import re

def apk_name(version):
    if not re.fullmatch(r'[1-9][0-9]*\.[0-9]+(?:\.[0-9]+)?', version):
        raise ValueError('Invalid APK version')
    return f'cifrolis-{version}-arm64.apk'

def accepted_names(version):
    return (apk_name(version), f'firefox-{version}-arm64-ruca.apk')

def is_release_apk(name):
    return bool(re.fullmatch(
        r'(?:cifrolis-[1-9][0-9]*\.[0-9]+(?:\.[0-9]+)?-arm64|'
        r'firefox-[1-9][0-9]*\.[0-9]+(?:\.[0-9]+)?-arm64-ruca)\.apk', name))

def has_complete_apk(assets, version):
    uploaded = {a['name'] for a in assets if a.get('state') == 'uploaded'}
    return any({name, name + '.sha256'} <= uploaded for name in accepted_names(version))
