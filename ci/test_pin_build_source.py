import json
import unittest
from unittest.mock import patch
from pin_build_source import pin, verify_tag
from release_policy import metadata


class PinBuildSourceTests(unittest.TestCase):
    sha = 'a' * 40
    code = 2020000002

    def exercise(self, refs=None, releases=None):
        refs = {} if refs is None else refs
        def read(args, **kwargs):
            path = args[-1]
            if path.endswith('/releases'):
                return json.dumps([releases or []]).encode()
            tag = path.split('/tags/')[-1]
            obj = refs.get(tag)
            return json.dumps([{'ref': 'refs/tags/' + tag, 'object': obj}] if obj else []).encode()
        def write(args, **kwargs):
            tag = next(a for a in args if a.startswith('ref=')).removeprefix('ref=refs/tags/')
            refs[tag] = {'type': 'commit', 'sha': self.sha}
        with patch('subprocess.check_output', side_effect=read), patch('subprocess.run', side_effect=write) as mutation:
            tag = pin('owner/repo', '159.0', self.code, self.sha)
        return tag, mutation

    def test_create_release_tag_without_a_branch(self):
        tag, write = self.exercise()
        self.assertEqual(tag, 'v159.0')
        args = write.call_args.args[0]
        self.assertIn('ref=refs/tags/v159.0', args)
        self.assertFalse(any('refs/heads/' in arg for arg in args))
        self.assertNotIn('--force', args)

    def test_same_tag_is_idempotent(self):
        tag, write = self.exercise({'v159.0': {'type': 'commit', 'sha': self.sha}})
        self.assertEqual(tag, 'v159.0')
        write.assert_not_called()

    def test_rebuild_gets_a_new_tag(self):
        old = {'tag_name': 'v159.0', 'body': metadata('159.0', self.code - 1)}
        tag, write = self.exercise(releases=[old])
        self.assertEqual(tag, f'v159.0-build.{self.code}')
        write.assert_called_once()

    def test_failed_build_tag_is_preserved(self):
        refs = {'v159.0': {'type': 'commit', 'sha': 'b' * 40}}
        tag, _ = self.exercise(refs)
        self.assertEqual(tag, f'v159.0-build.{self.code}')
        self.assertEqual(refs['v159.0']['sha'], 'b' * 40)

    def test_conflicting_build_tag_is_never_moved(self):
        refs = {tag: {'type': 'commit', 'sha': 'b' * 40}
                for tag in ('v159.0', f'v159.0-build.{self.code}')}
        with self.assertRaises(ValueError):
            self.exercise(refs)

    def test_published_version_code_is_rejected(self):
        old = {'tag_name': 'v159.0', 'body': metadata('159.0', self.code)}
        with self.assertRaises(ValueError):
            self.exercise(releases=[old])

    def test_tag_prefix_match_is_not_exact(self):
        data = [{'ref': 'refs/tags/v159.00', 'object': {'type': 'commit', 'sha': self.sha}}]
        with patch('subprocess.check_output', return_value=json.dumps(data).encode()):
            with self.assertRaises(ValueError):
                verify_tag('owner/repo', 'v159.0', self.sha)

    def test_wrong_commit_is_rejected(self):
        data = [{'ref': 'refs/tags/v159.0', 'object': {'type': 'commit', 'sha': 'b' * 40}}]
        with patch('subprocess.check_output', return_value=json.dumps(data).encode()):
            with self.assertRaises(ValueError):
                verify_tag('owner/repo', 'v159.0', self.sha)


if __name__ == '__main__':
    unittest.main()
