import unittest
from release_policy import choose_tag,identity,metadata

class ReleasePolicyTests(unittest.TestCase):
    def test_mobile_version_tag(self):
        self.assertEqual(choose_tag([],'158.0.2',2020000002),'v158.0.2')
    def test_rebuild_gets_separate_tag(self):
        old={'tag_name':'v158.0.2','body':metadata('158.0.2',2020000002)}
        self.assertEqual(choose_tag([old],'158.0.2',2020000003),'v158.0.2-build.2020000003')
        self.assertEqual(old['tag_name'],'v158.0.2')
    def test_duplicate_code_cannot_replace_assets(self):
        old={'tag_name':'v158.0','body':metadata('158.0',2020000001)}
        with self.assertRaises(ValueError):choose_tag([old],'158.0',2020000001)
    def test_legacy_release_identity(self):
        self.assertEqual(identity({'tag_name':'ruca-158.0-2020000001'}),('158.0',2020000001))
    def test_version_code_from_notes(self):
        self.assertEqual(identity({'tag_name':'v158.0','body':'versionCode 2020000001.'}),('158.0',2020000001))
    def test_rebuild_identity(self):
        self.assertEqual(identity({'tag_name':'v158.0-build.2020000005'}),('158.0',2020000005))
    def test_invalid_version_rejected(self):
        with self.assertRaises(ValueError):choose_tag([],'158.0; command',2020000005)

if __name__=='__main__':unittest.main()
