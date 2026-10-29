import hashlib
from pathlib import Path
import tempfile
import unittest

from fdroid_repository import (APP_ID, apk_identity, release_candidates,
                               select_versions, verify_digest, verify_signer)


class RepositoryTests(unittest.TestCase):
    def release(self, **changes):
        value = dict(draft=False, prerelease=False, published_at='2026-10-28',
                     assets=[dict(name='firefox-158.0-arm64-ruca.apk', state='uploaded')])
        value.update(changes)
        return value

    def test_only_published_stable_apks(self):
        stable = self.release()
        self.assertEqual([r for r, a in release_candidates([
            self.release(draft=True), self.release(prerelease=True),
            self.release(assets=[dict(name='verification.tar.gz')]), stable])], [stable])

    def test_rebranded_apk_is_indexed(self):
        release=self.release(assets=[dict(name='cifrolis-159.0-arm64.apk',state='uploaded')])
        self.assertEqual(release_candidates([release])[0][1]['name'],'cifrolis-159.0-arm64.apk')

    def test_unsigned_apk_is_not_indexed(self):
        self.assertEqual(release_candidates([self.release(assets=[
            dict(name='cifrolis-159.0-arm64-UNSIGNED.apk',state='uploaded')])]),[])

    def test_incomplete_upload_rejected(self):
        release = self.release()
        release['assets'][0]['state'] = 'new'
        with self.assertRaises(ValueError):
            release_candidates([release])

    def test_manifest_identity_is_actual_apk_identity(self):
        self.assertEqual(apk_identity(
            f"package: name='{APP_ID}' versionCode='2020000002' versionName='158.0' platformBuildVersionName='16'\n"),
            (APP_ID, 2020000002, '158.0'))
        with self.assertRaises(ValueError):
            apk_identity('not an APK')

    def test_keeps_highest_three_codes_not_release_order(self):
        items = [dict(code=n, sha256=str(n)) for n in [4, 1, 2, 5, 3]]
        self.assertEqual([i['code'] for i in select_versions(items)], [5, 4, 3])

    def test_conflicting_version_code_is_rejected(self):
        with self.assertRaises(ValueError):
            select_versions([dict(code=1, sha256='a'), dict(code=1, sha256='b')])

    def test_invalid_signature_and_extra_signer_are_rejected(self):
        line = 'Signer #1 certificate SHA-256 digest: abc\n'
        verify_signer(line, 'abc')
        for output in ['', line.replace('abc', 'def'), line + line.replace('#1', '#2')]:
            with self.assertRaises(ValueError):
                verify_signer(output, 'abc')

    def test_tampered_download_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            apk = Path(tmp) / 'app.apk'
            apk.write_bytes(b'original')
            digest = hashlib.sha256(apk.read_bytes()).hexdigest()
            verify_digest(apk, digest)
            apk.write_bytes(b'tampered')
            with self.assertRaises(ValueError):
                verify_digest(apk, digest)


if __name__ == '__main__':
    unittest.main()
