#!/usr/bin/env python3
"""Normalize and publish the existing phone-tested draft; preserve all assets."""
import json,os,subprocess
from release_policy import metadata

def api(path,*args):
    return json.loads(subprocess.check_output(['gh','api',path,*args]))
repo=os.environ['GH_REPO']
request=json.load(open('ci/release-request.json'))
path=f'repos/{repo}/releases/{request["release_id"]}'
release=api(path)
if release['tag_name']!=request['expected_tag'] or not release['draft']:
    raise ValueError('Release changed or already published; refusing metadata migration')
def assets(value):
    return sorted((a['id'],a['name'],a['size'],a.get('digest')) for a in value['assets'])
before=assets(release)
expected={'firefox-158.0-arm64-ruca.apk','firefox-158.0-arm64-ruca.apk.sha256','verification.tar.gz'}
if {a['name'] for a in release['assets']}!=expected or not all(a['state']=='uploaded' for a in release['assets']):
    raise ValueError('Tested release assets incomplete')
body=release['body'].rstrip()+'\n\nВладелец подтвердил 28 октября 2026 года установку, работу браузера и корректность встроенных сертификатов на своём телефоне.\n\n'+metadata('158.0',2020000001)+'\n'
patch={'name':'Цифролис 158.0','tag_name':'v158.0','body':body,'draft':False}
with open('release-patch.json','w') as out:json.dump(patch,out)
updated=api(path,'--method','PATCH','--input','release-patch.json')
if assets(updated)!=before:
    raise ValueError('Release asset identity unexpectedly changed')
print(updated['html_url'])
print('Published phone-tested v158.0; existing APK, checksum and verification assets unchanged')
