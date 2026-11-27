import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from extract_rootfs import extract, select_partition, sha256
from audit_rootfs import inventory
from prepare_probe import prepare, analyze, TARGET, SERVICE


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.image = self.path / 'test.img'
        self.image.write_bytes(b'fixture')
        self.g = MagicMock()
        self.g.list_devices.return_value = ['/dev/sda']
        self.g.part_get_parttype.return_value = 'gpt'
        self.g.list_partitions.return_value = ['/dev/sda1', '/dev/sda2']
        self.g.part_to_dev.return_value = '/dev/sda'
        self.g.part_to_partnum.side_effect = lambda p: int(p[-1])
        self.g.part_get_name.side_effect = lambda d, n: ['hassos-system0', 'hassos-system1'][n-1]
        self.g.vfs_type.return_value = 'erofs'
        self.g.is_file.return_value = True
        self.g.tar_out.side_effect = lambda root, out, **opts: Path(out).write_bytes(b'archive fixture')

    def test_extract_readonly(self):
        out = self.path / 'out'
        m = extract(self.image, sha256(self.image), out, 'A', lambda: self.g)
        self.g.add_drive_opts.assert_called_once_with(str(self.image.resolve()), format='raw', readonly=1)
        self.g.mount_ro.assert_called_once_with('/dev/sda1', '/')
        self.g.close.assert_called_once()
        self.assertEqual(m['rootfs_sha256'], sha256(out / 'rootfs.tar.gz'))
        self.assertTrue((out / 'manifest.json').is_file())

    def test_select_b(self):
        self.assertEqual(select_partition(self.g, 'B'), '/dev/sda2')

    def test_hash_mismatch(self):
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            extract(self.image, '0'*64, self.path / 'out', 'A', lambda: self.g)
        self.g.launch.assert_not_called()

    def test_missing_partition(self):
        self.g.part_get_name.side_effect = None
        self.g.part_get_name.return_value = 'unknown'
        with self.assertRaisesRegex(ValueError, 'found 0'):
            select_partition(self.g, 'A')

    def test_duplicate_partition(self):
        self.g.part_get_name.side_effect = None
        self.g.part_get_name.return_value = 'hassos-system0'
        with self.assertRaisesRegex(ValueError, 'found 2'):
            select_partition(self.g, 'A')

    def test_mount_failure_no_output(self):
        self.g.mount_ro.side_effect = RuntimeError('not supported')
        out = self.path / 'out'
        with self.assertRaises(RuntimeError):
            extract(self.image, sha256(self.image), out, 'A', lambda: self.g)
        self.g.close.assert_called_once()
        self.assertFalse(out.exists())

    def test_existing_output_preserved(self):
        out = self.path / 'out'
        out.mkdir()
        with self.assertRaises(FileExistsError):
            extract(self.image, sha256(self.image), out, 'A', lambda: self.g)
        self.g.launch.assert_not_called()

    def test_unexpected_filesystem(self):
        self.g.vfs_type.return_value = 'ext4'
        with self.assertRaisesRegex(ValueError, 'Unexpected'):
            extract(self.image, sha256(self.image), self.path / 'out', 'A', lambda: self.g)
        self.g.mount_ro.assert_not_called()


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name)
        self.archive = self.path / 'source.tar.gz'

    def fixture(self, entries):
        with tarfile.open(self.archive, 'w:gz') as t:
            for name, data in entries:
                m = tarfile.TarInfo(name)
                if isinstance(data, str):
                    m.type, m.linkname = tarfile.SYMTYPE, data
                    t.addfile(m)
                else:
                    m.size = len(data)
                    t.addfile(m, io.BytesIO(data))
        return self.archive

    def basic(self):
        return [('sbin/init', '/usr/lib/systemd/systemd'),
                ('usr/lib/systemd/systemd', b'fixture binary'),
                ('usr/lib/systemd/system/haos-wipe.service', b'ExecStart=/usr/bin/rauc status\n'),
                ('usr/lib/systemd/system-generators/systemd-fstab-generator', b'generator'),
                ('etc/fstab', b'LABEL=hassos-data /mnt/data ext4 defaults 0 0\n')]

    def test_inventory(self):
        p = self.fixture(self.basic())
        report = inventory(p)
        self.assertEqual(len(report['units']), 1)
        self.assertIn('boot_and_updates', report['matches'][0]['categories'])

    def test_path_traversal(self):
        p = self.fixture([('../unsafe', b'bad')])
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            inventory(p)
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            prepare(p, sha256(p), self.path / 'out')

    def test_links_not_followed(self):
        p = self.fixture([('etc/systemd/system/foo.service', '/usr/lib/systemd/system/example.service')])
        self.assertEqual(len(inventory(p)['links']), 1)

    def test_probe_masks_and_target(self):
        p = self.fixture(self.basic())
        out = self.path / 'out'
        report = prepare(p, sha256(p), out)
        self.assertIn('haos-wipe.service', report['masked_units'])
        with tarfile.open(out / 'haos-lxc-probe.tar.gz') as t:
            self.assertEqual(t.getmember('etc/systemd/system/haos-wipe.service').linkname, '/dev/null')
            self.assertEqual(t.getmember('etc/systemd/system-generators/systemd-fstab-generator').linkname, '/dev/null')
            self.assertEqual(t.getmember('etc/systemd/system/default.target').linkname, TARGET)
            self.assertIn(b'ConditionVirtualization=lxc', t.extractfile('etc/systemd/system/' + SERVICE).read())
            self.assertNotIn(b'hassos-data', t.extractfile('etc/fstab').read())
            self.assertEqual(t.extractfile('usr/lib/systemd/systemd').read(), b'fixture binary')
        self.assertEqual(report['template_sha256'], sha256(out / 'haos-lxc-probe.tar.gz'))

    def test_symlink_ancestor_rejected(self):
        p = self.fixture(self.basic() + [('etc/systemd', '/tmp')])
        with self.assertRaisesRegex(ValueError, 'ancestor'):
            prepare(p, sha256(p), self.path / 'out')
        self.assertFalse((self.path / 'out').exists())

    def test_probe_collision(self):
        p = self.fixture(self.basic() + [('usr/lib/systemd/system/' + TARGET, b'foreign')])
        with self.assertRaisesRegex(ValueError, 'collides'):
            prepare(p, sha256(p), self.path / 'out')

    def test_bad_digest(self):
        p = self.fixture(self.basic())
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            prepare(p, '0' * 64, self.path / 'out')

    def test_duplicates(self):
        p = self.fixture(self.basic() + [('etc/fstab', b'duplicate')])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            prepare(p, sha256(p), self.path / 'out')


if __name__ == '__main__':
    unittest.main()
