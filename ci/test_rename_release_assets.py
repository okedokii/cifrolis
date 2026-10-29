import copy
import hashlib
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from rename_release_assets import checksum_text, migrate


class RenameAssetsTests(unittest.TestCase):
    def exercise(self, already=False, tampered=False, fail_upload=False):
        old='firefox-159.0-arm64-ruca.apk'
        new='cifrolis-159.0-arm64.apk'
        digest=hashlib.sha256(b'signed-apk').hexdigest()
        request=dict(release_id=1, tag='v159.0', version='159.0', apk_id=10,
                     apk_size=10, apk_sha256=digest, checksum_id=11,
                     checksum_digest='sha256:'+hashlib.sha256(checksum_text(digest,old).encode()).hexdigest())
        apk=dict(id=10,name=new if already else old,size=10,
                 digest='sha256:'+('0'*64 if tampered else digest),state='uploaded')
        checksum=checksum_text(digest,new if already else old)
        asset=dict(id=12 if already else 11,name=(new if already else old)+'.sha256',
                   size=len(checksum),digest='sha256:'+hashlib.sha256(checksum.encode()).hexdigest(),state='uploaded')
        release=dict(tag_name='v159.0',draft=False,assets=[apk,asset])
        contents={asset['name']:checksum}
        mutations=[]
        def api(repo,path,*args):
            if path=='releases/1':return copy.deepcopy(release)
            if path=='releases/assets/10':
                mutations.append('rename')
                apk['name']=new
                return copy.deepcopy(apk)
            raise AssertionError(path)
        def run(args,**kwargs):
            if args[1:3]==['release','download']:
                name=args[args.index('--pattern')+1]
                folder=Path(args[args.index('--dir')+1])
                (folder/name).write_text(contents[name])
            elif args[1:3]==['release','upload']:
                mutations.append('upload')
                if fail_upload:raise subprocess.CalledProcessError(1,args)
                file=Path(args[4])
                contents[file.name]=file.read_text()
                release['assets'].append(dict(id=12,name=file.name,size=file.stat().st_size,
                    digest='sha256:'+hashlib.sha256(file.read_bytes()).hexdigest(),state='uploaded'))
            elif args[1]=='api' and args[-1]=='DELETE':
                mutations.append('delete-old-checksum')
                release['assets'][:]=[a for a in release['assets'] if a['id']!=11]
            else:raise AssertionError(args)
        with patch('rename_release_assets.api',side_effect=api),patch('subprocess.run',side_effect=run):
            if tampered:
                with self.assertRaises(ValueError):migrate('owner/repo',request)
            elif fail_upload:
                with self.assertRaises(subprocess.CalledProcessError):migrate('owner/repo',request)
            else:migrate('owner/repo',request)
        return release,mutations,contents

    def test_rename_preserves_apk_and_replaces_checksum_after_upload(self):
        release,mutations,contents=self.exercise()
        self.assertEqual(mutations,['rename','upload','delete-old-checksum'])
        self.assertEqual([a['name'] for a in release['assets']],
                         ['cifrolis-159.0-arm64.apk','cifrolis-159.0-arm64.apk.sha256'])
        self.assertEqual(release['assets'][0]['id'],10)
        self.assertIn('  cifrolis-159.0-arm64.apk\n',contents['cifrolis-159.0-arm64.apk.sha256'])

    def test_already_renamed_is_read_only(self):
        _,mutations,_=self.exercise(already=True)
        self.assertEqual(mutations,[])

    def test_changed_apk_blocks_all_writes(self):
        _,mutations,_=self.exercise(tampered=True)
        self.assertEqual(mutations,[])

    def test_upload_failure_keeps_original_checksum(self):
        release,mutations,_=self.exercise(fail_upload=True)
        self.assertNotIn('delete-old-checksum',mutations)
        self.assertTrue(any(a['id']==11 for a in release['assets']))
