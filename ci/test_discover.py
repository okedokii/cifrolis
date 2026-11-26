import io
import json
import unittest
from unittest.mock import patch

from discover import decision, requested_version
from mobile_versions import FEEDS, latest_stable, version_key
from release_policy import metadata


def release(version, code, draft=False):
    apk = f'cifrolis-{version}-arm64.apk'
    return dict(tag_name=f'v{version}', body=metadata(version, code),
                draft=draft, assets=[dict(name=name, state='uploaded')
                                    for name in (apk, apk + '.sha256')])


class DiscoverTests(unittest.TestCase):
    @patch('discover.latest_stable', return_value='161.0')
    def test_schedule_ignores_false_expression(self, latest):
        self.assertEqual(requested_version('schedule', 'false'), '161.0')
        latest.assert_called_once_with()

    @patch('discover.latest_stable', return_value='161.0')
    def test_manual_blank_uses_feed(self, latest):
        self.assertEqual(requested_version('workflow_dispatch', ''), '161.0')
        latest.assert_called_once_with()

    @patch('discover.latest_stable')
    def test_manual_explicit_and_invalid(self, latest):
        self.assertEqual(requested_version('workflow_dispatch', '161.0'), '161.0')
        with self.assertRaises(ValueError):
            requested_version('workflow_dispatch', 'false')
        latest.assert_not_called()

    def test_new_major_and_patch_are_built_once(self):
        previous = [release('159.0.1', 2020000010)]
        self.assertEqual(decision(previous, '161.0', 'schedule', 55), (True, 2020000055))
        previous.append(release('161.0', 2020000055))
        self.assertFalse(decision(previous, '161.0', 'schedule', 56)[0])
        self.assertTrue(decision(previous, '161.0.1', 'schedule', 56)[0])
        self.assertFalse(decision(previous, '160.0.1', 'schedule', 56)[0])

    def test_complete_draft_stops_scheduled_rebuild(self):
        self.assertFalse(decision([release('161.0', 2020000055, draft=True)],
                                  '161.0', 'schedule', 56)[0])

    def test_version_comparison(self):
        self.assertGreater(version_key('161.0.10'), version_key('161.0.2'))
        self.assertEqual(version_key('161.0'), version_key('161.0.0'))

    @patch('mobile_versions.urllib.request.urlopen')
    def test_primary_and_official_mirror(self, urlopen):
        urlopen.side_effect = [io.BytesIO(b'{"version":"162.0b1"}'),
                               io.BytesIO(b'{"version":"161.0"}')]
        self.assertEqual(latest_stable(), '161.0')
        self.assertEqual([c.args[0] for c in urlopen.call_args_list], list(FEEDS))

    @patch('mobile_versions.urllib.request.urlopen')
    def test_invalid_feeds_fail_closed(self, urlopen):
        urlopen.side_effect = [io.BytesIO(b'{"version":false}'),
                               io.BytesIO(b'{"version":"162.0a1"}')]
        with self.assertRaises(RuntimeError):
            latest_stable()


if __name__ == '__main__':
    unittest.main()
