#!/bin/sh
# Read-only inspection; run only inside the disposable test CT.
set -eu
virt=$(systemd-detect-virt --container 2>/dev/null || true)
if [ "$virt" != lxc ]; then
    echo 'Not detected as LXC; refusing to run.' >&2
    exit 1
fi
printf 'Virtualization: %s\n' "$virt"
printf 'Kernel: '; uname -r
printf 'Architecture: '; uname -m
printf '\nUID mapping:\n'; cat /proc/self/uid_map
printf '\nPID 1: '; cat /proc/1/comm
printf '\nMounts (selected):\n'
for path in / /sys/fs/cgroup /var/lib/docker /mnt/data; do
    if [ -e "$path" ]; then findmnt -n -o TARGET,FSTYPE,OPTIONS -T "$path" || true; fi
done
printf '\nCgroup controllers:\n'; cat /sys/fs/cgroup/cgroup.controllers 2>/dev/null || true
printf '\nAppArmor profile:\n'; cat /proc/self/attr/current 2>/dev/null || true
printf '\nCapabilities:\n'; grep -E '^Cap(Inh|Prm|Eff|Bnd|Amb):' /proc/self/status || true
printf '\nDocker version (local client):\n'; docker --version 2>/dev/null || true
printf '\nD-Bus sockets:\n'; ls -ld /run/dbus/system_bus_socket /var/run/dbus/system_bus_socket 2>/dev/null || true
printf '\nTools:\n'
for name in systemctl docker containerd nmcli busctl rauc; do
    command -v "$name" || true
done
printf '\nRead-only report finished. No host changes made.\n'
