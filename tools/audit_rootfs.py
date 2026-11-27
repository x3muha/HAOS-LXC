#!/usr/bin/env python3
"""Static inventory of systemd units and boot/storage dependencies."""
import argparse
import json
from pathlib import PurePosixPath
import re
import tarfile

PATTERNS = {
    'physical_storage': r'/dev/(?:disk/|sd[a-z]|nvme|mmcblk)|hassos-(?:boot|system|kernel|data|overlay)|\b(?:mount|umount|mkfs|resize2fs|e2image|parted|sfdisk|blkid)\b',
    'boot_and_updates': r'\b(?:rauc|grub|bootloader|boot-slot)\b|/mnt/boot',
    'kernel_and_devices': r'\b(?:modprobe|udev|zram|swapon|swapoff|sysctl|apparmor)\b|/sys/|/proc/sys/',
    'network_and_dbus': r'NetworkManager|network-online|dbus|D-Bus',
    'docker_and_supervisor': r'\b(?:docker|containerd|supervisor|hassio|os-agent)\b',
    'persistent_data': r'/mnt/(?:data|overlay)|/var/lib/docker',
}
UNIT_SUFFIX = ('.service', '.mount', '.automount', '.target', '.socket', '.timer', '.path', '.swap', '.slice', '.conf')
UNIT_DIRS = ('etc/systemd/system/', 'usr/lib/systemd/system/', 'lib/systemd/system/')
MAX_UNIT_BYTES = 1024 * 1024


def normalize(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError(f'Unsafe archive path: {name!r}')
    return str(path)


def inventory(path):
    units, links, matches, skipped = [], [], [], []
    with tarfile.open(path, 'r:*') as tar:
        for member in tar:
            name = normalize(member.name)
            if not name.startswith(UNIT_DIRS) or not name.endswith(UNIT_SUFFIX):
                continue
            if member.issym() or member.islnk():
                links.append({'path': name, 'target': member.linkname})
                continue
            if not member.isfile() or member.size > MAX_UNIT_BYTES:
                skipped.append(name)
                continue
            f = tar.extractfile(member)
            if f is None:
                skipped.append(name)
                continue
            with f:
                lines = f.read(MAX_UNIT_BYTES + 1).decode('utf-8', errors='replace').splitlines()
            units.append(name)
            for n, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith(('#', ';')):
                    continue
                categories = [key for key, regex in PATTERNS.items() if re.search(regex, line, re.I)]
                if categories:
                    matches.append({'path': name, 'line': n, 'categories': categories, 'text': line})
    return {'schema': 1, 'status': 'static-analysis-not-runtime-validation',
            'units': sorted(units), 'links': links, 'matches': matches, 'skipped': skipped}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive')
    args = p.parse_args()
    print(json.dumps(inventory(args.archive), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
