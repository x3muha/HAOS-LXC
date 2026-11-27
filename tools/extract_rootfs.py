#!/usr/bin/env python3
"""Read-only extraction from a fresh, verified HAOS raw image."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def select_partition(guest, slot):
    devices = guest.list_devices()
    if len(devices) != 1 or guest.part_get_parttype(devices[0]) != 'gpt':
        raise ValueError('Expected one GPT raw disk image')
    wanted = 'hassos-system' + {'A': '0', 'B': '1'}[slot]
    matches = [p for p in guest.list_partitions()
               if guest.part_get_name(guest.part_to_dev(p), guest.part_to_partnum(p)) == wanted]
    if len(matches) != 1:
        raise ValueError(f'Expected exactly one GPT partition named {wanted}; found {len(matches)}')
    return matches[0]


def extract(image, expected, output, slot, guest_factory=None):
    if not re.fullmatch(r'[0-9a-fA-F]{64}', expected):
        raise ValueError('Expected SHA256 must have 64 hexadecimal characters')
    if not image.is_file():
        raise ValueError('Input must be a regular raw disk image file, not a block device')
    if output.exists():
        raise FileExistsError(f'Output already exists: {output}')
    actual = sha256(image)
    if actual != expected.lower():
        raise ValueError('Image SHA256 mismatch')
    if guest_factory is None:
        try:
            import guestfs
        except ImportError as exc:
            raise RuntimeError('Install python3-guestfs and use the system Python interpreter') from exc
        guest_factory = lambda: guestfs.GuestFS(python_return_dict=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.haos-lxc-', dir=output.parent) as temp:
        stage = Path(temp) / 'result'
        stage.mkdir()
        archive = stage / 'rootfs.tar.gz'
        guest = guest_factory()
        try:
            guest.add_drive_opts(str(image.resolve()), format='raw', readonly=1)
            guest.launch()
            part = select_partition(guest, slot)
            filesystem = guest.vfs_type(part)
            if filesystem not in {'erofs', 'squashfs'}:
                raise ValueError(f'Unexpected system filesystem: {filesystem}')
            guest.mount_ro(part, '/')
            if not guest.is_file('/usr/lib/os-release', followsymlinks=True) and not guest.is_file('/etc/os-release', followsymlinks=True):
                raise ValueError('No os-release found')
            guest.tar_out('/', str(archive), compress='gzip', numericowner=True,
                          xattrs=True, acls=True, selinux=True)
            guest.umount_all()
        finally:
            guest.close()
        manifest = {'schema': 1, 'status': 'unmodified-system-only-not-bootable-lxc',
                    'input_image': image.name, 'input_sha256': actual,
                    'slot': slot, 'partition': part, 'filesystem': filesystem,
                    'rootfs_sha256': sha256(archive)}
        (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        if output.exists():
            raise FileExistsError(f'Output already exists: {output}')
        stage.rename(output)
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('image', type=Path)
    p.add_argument('--sha256', required=True, help='SHA256 of the verified UNCOMPRESSED image')
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--slot', choices=['A', 'B'], default='A')
    a = p.parse_args()
    try:
        print(json.dumps(extract(a.image, a.sha256, a.output, a.slot), indent=2))
    except (OSError, RuntimeError, ValueError) as exc:
        p.exit(1, f'Extraction failed: {exc}\n')


if __name__ == '__main__':
    main()
