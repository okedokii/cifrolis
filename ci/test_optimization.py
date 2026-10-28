import unittest
from run_build import resource_failure


class ResourceRetryTests(unittest.TestCase):
    def test_resource_errors_retry(self):
        for code, log in [(124, ''), (137, ''), (-9, ''),
                          (1, 'LLVM ERROR: out of memory'),
                          (101, 'signal: 9, SIGKILL: kill'),
                          (1, 'No space left on device')]:
            self.assertTrue(resource_failure(code, log))
        self.assertTrue(resource_failure(1, '', 0, 1))

    def test_source_and_configuration_errors_do_not_retry(self):
        for log in ['error[E0308]: mismatched types', 'Patch cannot be applied',
                    'Missing signing key', 'R8: Missing class example.Class']:
            self.assertFalse(resource_failure(1, log))


if __name__ == '__main__':
    unittest.main()
