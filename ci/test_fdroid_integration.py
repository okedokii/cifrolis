"""Exercise real fdroidserver and Java signing without production secrets."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import fdroid_repository as repository


@unittest.skipUnless(all(shutil.which(tool) for tool in ['fdroid', 'keytool', 'jarsigner']),
                     'F-Droid and JDK signing tools are required')
class SigningIntegrationTests(unittest.TestCase):
    def test_signed_empty_repo_and_private_file_cleanup(self):
        source = Path(repository.__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'ci').mkdir()
            (root / 'assets').mkdir()
            shutil.copyfile(source / 'assets/icon.png', root / 'assets/icon.png')
            shutil.copytree(source / 'fdroid/metadata', root / 'fdroid/metadata')
            key = root / 'test.p12'
            password = 'integration-test-only'
            subprocess.run(['keytool', '-genkeypair', '-alias', 'test', '-keyalg', 'RSA',
                            '-keysize', '2048', '-validity', '2', '-dname', 'CN=Integration test',
                            '-keystore', str(key), '-storetype', 'PKCS12', '-storepass', password],
                           check=True, capture_output=True)
            certificate = subprocess.check_output(['keytool', '-exportcert', '-alias', 'test',
                                                  '-keystore', str(key), '-storepass', password])
            identity = dict(application_id=repository.APP_ID, key_alias='test',
                            signer_sha256=hashlib.sha256(certificate).hexdigest())
            (root / 'ci/signing-identity.json').write_text(json.dumps(identity))
            env = dict(GH_REPO='example/cifrolis', RUNNER_TEMP=str(root),
                       GITHUB_STEP_SUMMARY=str(root / 'summary.md'),
                       RUCA_KEYSTORE_PASSWORD=password,
                       RUCA_KEYSTORE_B64=base64.b64encode(key.read_bytes()).decode())
            # No production API or secrets: gh only lists an empty release collection.
            with (patch.dict(os.environ, env),
                  patch.object(repository, '__file__', str(root / 'ci/fdroid_repository.py')),
                  patch.object(repository, 'run', return_value='[[]]')):
                repository.main()
            public = root / 'public'
            for name in ['index-v1.jar', 'entry.jar']:
                signed = public / 'fdroid/repo' / name
                output = subprocess.check_output(['jarsigner', '-verify', str(signed)], text=True)
                self.assertIn('jar verified', output)
            self.assertFalse((root / 'cifrolis-fdroid').exists())
            self.assertFalse(list(public.rglob('*.p12')))
            self.assertFalse(list(public.rglob('config.yml')))


if __name__ == '__main__':
    unittest.main()
