#!/usr/bin/env python3
"""Create a new release; never delete a release or replace an existing asset."""
import argparse,json,os,subprocess
from pathlib import Path
from release_policy import choose_tag,metadata

p=argparse.ArgumentParser()
p.add_argument('--version',required=True)
p.add_argument('--code',type=int,required=True)
p.add_argument('--target',required=True)
p.add_argument('--notes-file',type=Path,required=True)
p.add_argument('--publish',action='store_true')
a=p.parse_args()
releases=json.loads(subprocess.check_output(['gh','api','--paginate','--slurp',f'repos/{os.environ["GH_REPO"]}/releases']))
releases=[r for page in releases for r in page]
tag=choose_tag(releases,a.version,a.code)
expected={f'firefox-{a.version}-arm64-ruca.apk',f'firefox-{a.version}-arm64-ruca.apk.sha256'}
files=[Path('dist')/name for name in sorted(expected)]
if not all(f.is_file() and f.stat().st_size for f in files):
    raise ValueError('Expected APK and checksum')
# Technical reports stay in Actions artifacts and are not uploaded to Releases.
notes=a.notes_file.read_text().rstrip()+'\n\n'+metadata(a.version,a.code)+'\n'
a.notes_file.write_text(notes)
subprocess.run(['gh','release','create',tag,'--draft','--target',a.target,'--title',f'Цифролис {a.version}','--notes-file',str(a.notes_file)],check=True)
# Deliberately omit --clobber. Upload failure leaves the draft for inspection.
subprocess.run(['gh','release','upload',tag,*map(str,files)],check=True)
if a.publish:
    subprocess.run(['gh','release','edit',tag,'--draft=false'],check=True)
print(f'Created {tag}; previous releases and assets preserved')
