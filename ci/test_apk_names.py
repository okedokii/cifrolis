import unittest
from apk_names import apk_name, has_complete_apk, is_release_apk

class ApkNamesTests(unittest.TestCase):
    def test_current_filename(self):
        self.assertEqual(apk_name('159.0.1'), 'cifrolis-159.0.1-arm64.apk')

    def test_both_naming_schemes_count_as_existing_builds(self):
        for name in ('cifrolis-159.0-arm64.apk', 'firefox-159.0-arm64-ruca.apk'):
            assets=[{'name':n,'state':'uploaded'} for n in (name,name+'.sha256')]
            self.assertTrue(has_complete_apk(assets,'159.0'))
            self.assertFalse(has_complete_apk(assets[:1],'159.0'))
            self.assertFalse(has_complete_apk(assets,'159.0.1'))

    def test_only_release_apks_are_recognized(self):
        for name in ('cifrolis-159.0-arm64.apk','firefox-159.0-arm64-ruca.apk'):
            self.assertTrue(is_release_apk(name))
        for name in ('cifrolis-159.0-arm64-UNSIGNED.apk','cifrolis-159.0-arm64.apk.sha256','other.apk'):
            self.assertFalse(is_release_apk(name))
