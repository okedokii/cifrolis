"""Read the required Rust version from the verified Firefox source checkout."""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def required_rust(source):
    util = Path(source) / 'python/mozboot/mozboot/util.py'
    if not util.is_file():
        # Preflight/sign-only runs have not downloaded Firefox source.
        return json.loads((ROOT / 'kit/downloads.json').read_text())['bootstrap']['rust_toolchain']
    matches = re.findall(r'^MINIMUM_RUST_VERSION = "([0-9]+\.[0-9]+\.[0-9]+)"$', util.read_text(), re.M)
    if len(matches) != 1:
        raise ValueError('Cannot identify the upstream minimum Rust version')
    return matches[0]


if __name__ == '__main__':
    print(required_rust(sys.argv[1]))
