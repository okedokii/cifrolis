"""Read Mozilla's stable Android channel, with its official synced mirror as fallback."""
import json
import urllib.request
from source_manifest import validate_version

FEEDS = (
    'https://product-details.mozilla.org/1.0/mobile_versions.json',
    'https://raw.githubusercontent.com/mozilla-releng/product-details/production/public/1.0/mobile_versions.json',
)


def version_key(version):
    parts = tuple(map(int, validate_version(version).split('.')))
    return parts + (0,) * (3 - len(parts))


def latest_stable():
    errors = []
    for url in FEEDS:
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                data = json.load(response)
            version = data['version']
            if not isinstance(version, str):
                raise ValueError('Stable version field must be a string')
            print(f'Mozilla Android stable from {url}: {version!r}')
            return validate_version(version)
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append(f'{url}: {error}')
            print(f'Cannot read stable Android version: {errors[-1]}')
    raise RuntimeError('No valid stable Android version from Mozilla feeds: ' + '; '.join(errors))
