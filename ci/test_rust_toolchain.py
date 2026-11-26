import tempfile
import unittest
from pathlib import Path
from rust_toolchain import required_rust


class RustToolchainTests(unittest.TestCase):
    def test_reads_verified_source_not_old_hardcode(self):
        with tempfile.TemporaryDirectory() as tmp:
            util = Path(tmp) / 'python/mozboot/mozboot/util.py'
            util.parent.mkdir(parents=True)
            for version in ('1.90.0', '1.95.0', '1.96.0'):
                util.write_text(f'MINIMUM_RUST_VERSION = "{version}"\n')
                self.assertEqual(required_rust(tmp), version)
            util.write_text('MINIMUM_RUST_VERSION = "nightly"\n')
            with self.assertRaises(ValueError):
                required_rust(tmp)
