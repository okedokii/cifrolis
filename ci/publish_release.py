#!/usr/bin/env python3
"""Create a new release; never delete a release or replace an existing asset."""
import argparse,json,os,subprocess
from pathlib import Path
from release_policy import choose_tag,metadata
from pin_build_source import pin,verify_tag
from apk_names import apk_name

p=argparse.ArgumentParser()
p.add_argument('--tag')
p.add_argument('--version',required=True)
p.add_argument('--code',type=int,required=True)
p.add_argument('--target',required=True)
p.add_argument('--notes-file',type=Path,required=True)
p.add_argument('--publish',action='store_true')
a=p.parse_args()
releases=json.loads(subprocess.check_output(['gh','api','--paginate','--slurp',f'repos/{os.environ["GH_REPO"]}/releases']))
releases=[r for page in releases for r in page]
choose_tag(releases,a.version,a.code)  # Reject duplicate versionCodes before any write.
tag=a.tag or pin(os.environ['GH_REPO'],a.version,a.code,a.target)
if tag not in {f'v{a.version}',f'v{a.version}-build.{a.code}'} or any(r['tag_name']==tag for r in releases):
    raise ValueError('Invalid or already published release tag')
verify_tag(os.environ['GH_REPO'],tag,a.target)
name=apk_name(a.version)
expected={name,name+'.sha256'}
files=[Path('dist')/name for name in sorted(expected)]
if not all(f.is_file() and f.stat().st_size for f in files):
    raise ValueError('Expected APK and checksum')
# Technical reports stay in Actions artifacts and are not uploaded to Releases.
notes=a.notes_file.read_text().rstrip()
optimization=Path('dist/optimization.json')
if optimization.is_file():
    mode=json.loads(optimization.read_text())
    label='ThinLTO' if mode['lto']=='thin' else 'без LTO после ограничения ресурсов runner'
    notes+='\n\nОптимизация: Rust opt-level=2, R8; '+label+'.'
notes+='\n\n'+metadata(a.version,a.code)+'\n'
a.notes_file.write_text(notes)
subprocess.run(['gh','release','create',tag,'--draft','--verify-tag','--target',a.target,'--title',f'v{a.version}','--notes-file',str(a.notes_file)],check=True)
# Deliberately omit --clobber. Upload failure leaves the draft for inspection.
subprocess.run(['gh','release','upload',tag,*map(str,files)],check=True)
if a.publish:
    subprocess.run(['gh','release','edit',tag,'--draft=false'],check=True)
    # Releases created by GITHUB_TOKEN do not trigger release-event workflows.
    subprocess.run(['gh','workflow','run','fdroid.yml','--repo',os.environ['GH_REPO'],'--ref','main'],check=True)
    print('Обновление репозитория F-Droid запущено после публикации релиза')
print(f'Created {tag}; previous releases and assets preserved')
