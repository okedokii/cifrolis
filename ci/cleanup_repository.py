#!/usr/bin/env python3
"""Apply requested release text cleanup; never modify the existing APK assets."""
import json,os,subprocess
from release_policy import identity,metadata

def api(path,*args):
    return json.loads(subprocess.check_output(['gh','api',path,*args]))
repo=os.environ['GH_REPO']
request=json.load(open('ci/cleanup-request.json'))

if request.get('remove_verification_reports'):
    pages=api(f'repos/{repo}/releases','--paginate','--slurp')
    for release in [r for page in pages for r in page]:
        before={a['id']:(a['name'],a['size'],a.get('digest')) for a in release['assets'] if a['name']!='verification.tar.gz'}
        for asset in release['assets']:
            if asset['name']=='verification.tar.gz':
                subprocess.run(['gh','api',f'repos/{repo}/releases/assets/{asset["id"]}','--method','DELETE'],check=True)
                print(f'Удалён verification.tar.gz из {release["tag_name"]}')
        after=api(f'repos/{repo}/releases/{release["id"]}')
        actual={a['id']:(a['name'],a['size'],a.get('digest')) for a in after['assets']}
        if actual!=before:
            raise ValueError('APK, checksum or another release asset changed unexpectedly')
    print('Выполнено. APK и контрольные суммы сохранены; отчёты остаются в Actions.')
    raise SystemExit(0)

path=f'repos/{repo}/releases/{request["release_id"]}'
r=api(path)
if r['tag_name']!=request['expected_tag']:
    raise ValueError('Release tag changed; inspect before editing')
version,code=identity(r)
def assets(r):
    return sorted((a['id'],a['name'],a['size'],a.get('digest')) for a in r['assets'])
before=assets(r)
body='Firefox для Android со встроенными сертификатами Минцифры.\n\nСкачайте APK из файлов релиза. Дополнительно устанавливать сертификаты в Android не требуется.\n\n'+metadata(version,code)+'\n'
with open('release-cleanup.json','w') as out:json.dump({'body':body},out)
updated=api(path,'--method','PATCH','--input','release-cleanup.json')
if assets(updated)!=before:
    raise ValueError('Unexpected release asset change')
print('Описание релиза обновлено. Файлы APK и отчётов сохранены без изменений.')
