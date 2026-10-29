import unittest
from unittest.mock import patch
from retire_build_source import retire


class RetireBuildSourceTests(unittest.TestCase):
    item = {'branch': 'build-source/159.0-2020000002', 'tag': 'v159.0', 'sha': 'a' * 40}

    def responses(self, branch_sha=None, tag_sha=None):
        return [
            [{'ref': 'refs/heads/' + self.item['branch'],
              'object': {'sha': branch_sha or self.item['sha']}}],
            {'object': {'type': 'commit', 'sha': tag_sha or self.item['sha']}},
            {'tag_name': 'v159.0', 'draft': False},
        ]

    def test_delete_only_branch_preserved_by_release_tag(self):
        with patch('retire_build_source.api', side_effect=self.responses()), patch('subprocess.run') as write:
            retire('owner/repo', [self.item])
        self.assertEqual(write.call_args.args[0], [
            'gh', 'api', 'repos/owner/repo/git/refs/heads/' + self.item['branch'], '--method', 'DELETE'])

    def test_changed_branch_is_preserved(self):
        with patch('retire_build_source.api', side_effect=self.responses(branch_sha='b'*40)), patch('subprocess.run') as write:
            with self.assertRaises(ValueError):
                retire('owner/repo', [self.item])
            write.assert_not_called()

    def test_wrong_tag_is_preserved(self):
        with patch('retire_build_source.api', side_effect=self.responses(tag_sha='b'*40)), patch('subprocess.run') as write:
            with self.assertRaises(ValueError):
                retire('owner/repo', [self.item])
            write.assert_not_called()

    def test_missing_branch_is_idempotent(self):
        with patch('retire_build_source.api', return_value=[]), patch('subprocess.run') as write:
            retire('owner/repo', [self.item])
            write.assert_not_called()

    def test_main_cannot_be_deleted(self):
        with patch('subprocess.run') as write:
            with self.assertRaises(ValueError):
                retire('owner/repo', [dict(self.item, branch='main')])
            write.assert_not_called()
