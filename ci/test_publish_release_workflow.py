import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


class PublishReleaseWorkflowTests(unittest.TestCase):
    def invoke(self,publish,fail_upload=False,wrong_commit=False):
        script=Path(__file__).with_name('publish_release.py').resolve()
        calls=[]
        def read(args,**kwargs):
            if args[-1].endswith('/releases'):return b'[[]]'
            return json.dumps([{'ref':'refs/tags/v159.0','object':{'type':'commit','sha':('b' if wrong_commit else 'a')*40}}]).encode()
        def execute(args,**kwargs):
            calls.append(args)
            if fail_upload and args[:3]==['gh','release','upload']:
                raise subprocess.CalledProcessError(1,args)
        with tempfile.TemporaryDirectory() as tmp:
            previous=Path.cwd()
            try:
                os.chdir(tmp)
                Path('dist').mkdir()
                for name in ('cifrolis-159.0-arm64.apk','cifrolis-159.0-arm64.apk.sha256','verification.tar.gz'):
                    Path('dist',name).write_text('fixture')
                Path('notes.txt').write_text('Описание')
                args=[str(script),'--version','159.0','--code','2020000009','--tag','v159.0','--target','a'*40,'--notes-file','notes.txt']
                if publish:args.append('--publish')
                with patch.dict(os.environ,{'GH_REPO':'owner/repo'}),patch.object(sys,'argv',args),patch('subprocess.check_output',side_effect=read),patch('subprocess.run',side_effect=execute),contextlib.redirect_stdout(io.StringIO()):
                    if wrong_commit:
                        with self.assertRaises(ValueError):runpy.run_path(str(script),run_name='__main__')
                    elif fail_upload:
                        with self.assertRaises(subprocess.CalledProcessError):runpy.run_path(str(script),run_name='__main__')
                    else:runpy.run_path(str(script),run_name='__main__')
                self.assertTrue(Path('dist/verification.tar.gz').is_file())
            finally:os.chdir(previous)
        return calls

    def test_published_release_dispatches_fdroid_after_upload(self):
        calls=self.invoke(True)
        upload=next(i for i,c in enumerate(calls) if c[:3]==['gh','release','upload'])
        publish=next(i for i,c in enumerate(calls) if c[:3]==['gh','release','edit'])
        dispatch=next(i for i,c in enumerate(calls) if c[:4]==['gh','workflow','run','fdroid.yml'])
        self.assertLess(upload,publish)
        self.assertLess(publish,dispatch)
        self.assertEqual(calls[dispatch],['gh','workflow','run','fdroid.yml','--repo','owner/repo','--ref','main'])
        self.assertEqual(len(calls[upload][4:]),2)

    def test_uses_existing_tag_and_never_creates_it_at_publication(self):
        calls=self.invoke(False)
        create=next(c for c in calls if c[:3]==['gh','release','create'])
        self.assertIn('--verify-tag',create)
        self.assertFalse(any(c[:2]==['gh','api'] for c in calls))

    def test_wrong_source_tag_blocks_all_writes(self):
        self.assertEqual(self.invoke(True,wrong_commit=True),[])

    def test_draft_does_not_dispatch_fdroid(self):
        calls=self.invoke(False)
        self.assertFalse(any(c[:3]==['gh','workflow','run'] for c in calls))

    def test_failed_upload_does_not_publish_or_dispatch(self):
        calls=self.invoke(True,True)
        self.assertFalse(any(c[:3]==['gh','release','edit'] or c[:3]==['gh','workflow','run'] for c in calls))

if __name__=='__main__':unittest.main()
