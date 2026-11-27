#!/usr/bin/env python3
"""Build a restricted local boot probe, without unpacking as root.

No upstream service is intentionally started. This is NOT an isolation
boundary: only use a fresh, verified image in an isolated unprivileged lab CT.
"""
import argparse
import copy
import io
import json
from pathlib import Path, PurePosixPath
import tarfile
import tempfile
from extract_rootfs import sha256
from audit_rootfs import normalize

UNIT_DIRS = ('etc/systemd/system', 'usr/lib/systemd/system', 'lib/systemd/system',
             'usr/local/lib/systemd/system')
GEN_KINDS = ('system-generators', 'system-environment-generators')
GEN_BASES = ('etc/systemd', 'usr/lib/systemd', 'lib/systemd', 'usr/local/lib/systemd')
MASK_SUFFIXES = ('.service', '.socket', '.mount', '.automount', '.path', '.timer', '.swap')
UNIT_BASE = 'etc/systemd/system'
TARGET = 'haos-lxc-probe.target'
SERVICE = 'haos-lxc-probe.service'
MARKER = '/run/haos-lxc/boot-ok'
TARGET_TEXT = b'[Unit]\nDescription=HAOS-LXC isolated boot probe\nDefaultDependencies=no\nRequires=haos-lxc-probe.service\nAfter=haos-lxc-probe.service\n'
SERVICE_TEXT = b'[Unit]\nDescription=HAOS-LXC boot marker\nDefaultDependencies=no\nConditionVirtualization=lxc\n[Service]\nType=oneshot\nExecStart=/bin/sh -ec "mkdir -p /run/haos-lxc; echo boot-ok > /run/haos-lxc/boot-ok"\nRemainAfterExit=yes\n'


def entry(name, kind=tarfile.REGTYPE, data=b'', link=''):
    m = tarfile.TarInfo(name)
    m.type, m.linkname = kind, link
    m.mode = 0o755 if kind == tarfile.DIRTYPE else 0o644
    if kind == tarfile.SYMTYPE:
        m.mode = 0o777
    m.size = len(data)
    return m, data


def ancestors(name):
    return [str(p) for p in PurePosixPath(name).parents if str(p) != '.']


def analyze(members):
    index = {}
    for m in members:
        name = normalize(m.name)
        if name in index:
            raise ValueError(f'Duplicate archive path: {name}')
        if name != '.' and not name.startswith('dev/'):
            if not (m.isdir() or m.isfile() or m.issym() or m.islnk()):
                raise ValueError(f'Unexpected special archive member: {name}')
        index[name] = m
    for name, m in index.items():
        for p in ancestors(name):
            if p in index and not index[p].isdir():
                raise ValueError(f'Non-directory archive ancestor: {p}')
        if m.islnk():
            target = normalize(m.linkname)
            if target not in index or not index[target].isfile():
                raise ValueError(f'Hardlink target is not a regular archive member: {target}')
    if 'sbin/init' not in index and not ('sbin' in index and index['sbin'].issym() and 'usr/sbin/init' in index):
        raise ValueError('Missing expected system init path')
    if not any(p in index for p in ('usr/lib/systemd/systemd', 'lib/systemd/systemd')):
        raise ValueError('Missing systemd binary')
    replace = {}
    def put(name, kind=tarfile.REGTYPE, data=b'', link=''):
        if name in replace:
            raise ValueError(f'Conflicting generated path: {name}')
        if name in index and index[name].isdir() != (kind == tarfile.DIRTYPE):
            raise ValueError(f'Refusing to change directory into file or vice versa: {name}')
        replace[name] = entry(name, kind, data, link)
    masks = set()
    for name in index:
        for base in UNIT_DIRS:
            prefix = base + '/'
            if name.startswith(prefix):
                suffix = name[len(prefix):]
                if '/' not in suffix and suffix.endswith(MASK_SUFFIXES):
                    masks.add(suffix)
                if suffix.split('/')[0] in (TARGET, SERVICE, TARGET + '.d', SERVICE + '.d', TARGET + '.wants', TARGET + '.requires', SERVICE + '.wants', SERVICE + '.requires'):
                    raise ValueError(f'Upstream collides with probe namespace: {name}')
    for unit in sorted(masks):
        put(UNIT_BASE + '/' + unit, tarfile.SYMTYPE, link='/dev/null')
    generators = set()
    for name in index:
        for base in GEN_BASES:
            for kind in GEN_KINDS:
                prefix = base + '/' + kind + '/'
                if name.startswith(prefix):
                    tail = name[len(prefix):]
                    if '/' not in tail and not index[name].isdir():
                        generators.add((kind, tail))
    for kind, gen in sorted(generators):
        # A /dev/null mask in /etc takes precedence over vendor generators.
        put('etc/systemd/' + kind + '/' + gen, tarfile.SYMTYPE, link='/dev/null')
    put(UNIT_BASE + '/default.target', tarfile.SYMTYPE, link=TARGET)
    put(UNIT_BASE + '/' + TARGET, data=TARGET_TEXT)
    put(UNIT_BASE + '/' + SERVICE, data=SERVICE_TEXT)
    put('etc/fstab', data=b'# HAOS-LXC boot probe; no disk mounts\n')
    put('etc/machine-id')
    # Do not let unexpected links in the archive redirect generated paths.
    for name in list(replace):
        for p in reversed(ancestors(name)):
            if p in index:
                if not index[p].isdir():
                    raise ValueError(f'Generated path has non-directory ancestor: {p}')
            elif p not in replace:
                put(p, tarfile.DIRTYPE)
    for name, m in index.items():
        if m.islnk() and (normalize(m.linkname) in replace or normalize(m.linkname).startswith('dev/')):
            raise ValueError(f'Hardlink refers to modified member: {name}')
    return replace, sorted(masks), sorted(generators)


def prepare(source, expected, output):
    if not source.is_file() or sha256(source) != expected.lower():
        raise ValueError('Rootfs digest mismatch or missing archive')
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.probe-', dir=output.parent) as temp:
        stage = Path(temp) / 'result'
        stage.mkdir()
        dest = stage / 'haos-lxc-probe.tar.gz'
        with tarfile.open(source, 'r:*') as old:
            members = old.getmembers()
            changes, masks, generators = analyze(members)
            with tarfile.open(dest, 'w:gz', format=tarfile.PAX_FORMAT) as new:
                # Add missing real directories first; preserve existing metadata.
                for name, (m, data) in sorted(changes.items(), key=lambda x: (x[0].count('/'), x[0])):
                    if m.isdir():
                        new.addfile(m)
                for m in members:
                    name = normalize(m.name)
                    if name in changes or name.startswith('dev/'):
                        continue
                    # Guest absolute symlinks remain symlinks; never dereference them.
                    info = copy.copy(m)
                    f = old.extractfile(m) if m.isfile() else None
                    try:
                        new.addfile(info, f)
                    finally:
                        if f is not None:
                            f.close()
                for name, (m, data) in sorted(changes.items()):
                    if not m.isdir():
                        new.addfile(m, io.BytesIO(data) if data else None)
        report = {'schema': 1, 'status': 'boot-probe-only-not-validated',
                  'source_sha256': expected.lower(), 'template_sha256': sha256(dest),
                  'masked_units': masks, 'masked_generators': generators,
                  'modified_paths': sorted(changes), 'expected_marker': MARKER}
        (stage / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
        if output.exists():
            raise FileExistsError(output)
        stage.rename(output)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive', type=Path)
    p.add_argument('--sha256', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    try:
        print(json.dumps(prepare(a.archive, a.sha256, a.output), indent=2))
    except (ValueError, OSError, tarfile.TarError) as exc:
        p.exit(1, f'Probe preparation failed: {exc}\n')


if __name__ == '__main__':
    main()
