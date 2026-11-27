# Architecture

Keep upstream HAOS Buildroot userspace. The PVE host owns the kernel, time, devices and volume lifecycle; there is no GRUB, guest kernel, A/B disk boot, data disk expansion, or RAUC disk update in LXC.

1. Extract verified system partition and inventory dependencies (initial tools).
2. Boot probe: use a custom systemd target with an isolated marker service, mask vendor service activation and discovered generators. This is a deliberately restricted experiment, NOT a hard security boundary or functional HA installation.
3. Runtime profile: review actual units and scripts; enable D-Bus, isolated network configuration, and storage only when each is reviewed. Replace persistent overlay and data mounts with managed directories or volumes. Evaluate nested Docker and storage drivers under unprivileged LXC, without host devices/sockets or global security changes.
4. Supervisor: preserve legitimate health diagnostics; determine explicit LXC platform support, OS Agent and data initialization. No silent support-check bypass. Test Core, apps, backups and restoration.
5. OS updates: a host-side, explicitly authorized updater with verified versions, operation locks, consistent backup, readiness checks and rollback. Do not pass PVE credentials to the guest. Coordinate rootfs and data schema versions. UI integration later, never fake RAUC success.
6. License/SBOM and release gating before publishing any derived image.

Upstream layout and boot: https://contributors.home-assistant.io/os/operating-system/ and https://contributors.home-assistant.io/os/operating-system/partitions/ . Upstream explicitly does not support Supervisor inside LXC: https://www.home-assistant.io/more-info/unsupported/lxc/ .
