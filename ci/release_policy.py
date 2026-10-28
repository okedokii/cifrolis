"""Release identity and append-only naming; understands legacy release tags."""
import json
import re

VERSION=r'[1-9][0-9]*\.[0-9]+(?:\.[0-9]+)?'
MARKER=re.compile(r'<!-- firefox-ruca (\{[^\n]+\}) -->')

def identity(release):
    body=release.get('body') or ''
    marker=MARKER.search(body)
    if marker:
        data=json.loads(marker[1])
        version=data['firefox_version']; code=int(data['version_code'])
    else:
        legacy=re.fullmatch(r'ruca-('+VERSION+r')-([0-9]+)',release['tag_name'])
        modern=re.fullmatch(r'v('+VERSION+r')(?:-build\.([0-9]+))?',release['tag_name'])
        if legacy:
            version,code=legacy[1],int(legacy[2])
        elif modern:
            code_match=re.search(r'\bversionCode[ :]+([0-9]+)',body)
            if not modern[2] and not code_match:
                raise ValueError('Missing versionCode on recognized release')
            version,code=modern[1],int(modern[2] or code_match[1])
        else:
            return None
    if not re.fullmatch(VERSION,version) or not 2016191386 < code <= 2100000000:
        raise ValueError('Invalid stored release identity')
    return version,code

def choose_tag(releases,version,code):
    if not re.fullmatch(VERSION,version) or not 2016191386 < code <= 2100000000:
        raise ValueError('Invalid new release identity')
    identities=[identity(r) for r in releases]
    if any(i and i[1]==code for i in identities):
        raise ValueError('This versionCode already has a release; existing assets will not be replaced')
    used={r['tag_name'] for r in releases}
    base=f'v{version}'
    tag=base if base not in used else f'{base}-build.{code}'
    if tag in used:
        raise ValueError('Release tag already exists; refusing to overwrite')
    return tag

def metadata(version,code):
    return '<!-- firefox-ruca '+json.dumps({'firefox_version':version,'version_code':code},separators=(',',':'))+' -->'
