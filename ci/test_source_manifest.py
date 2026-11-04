import unittest

from source_manifest import validate_version


class MobileVersionTests(unittest.TestCase):
    def test_current_and_future_stable_releases(self):
        for version in ('159.0', '159.0.1', '159.1', '160.0', '160.0.2', '161.1', '200.0'):
            with self.subTest(version=version):
                self.assertEqual(validate_version(version), version)

    def test_reject_older_or_nonstable_releases(self):
        for version in ('158.0', '159', '159.0b1', '160.0b5', '161.0a1',
                        '160.0rc1', '160.00', '160.1.01', 'v160.0', '160.0;rm -rf /'):
            with self.subTest(version=version), self.assertRaises(ValueError):
                validate_version(version)


if __name__ == '__main__':
    unittest.main()
