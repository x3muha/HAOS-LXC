# HAOS-LXC — v0.0.2 (research)

Independent, unofficial adaptation of the upstream Home Assistant OS Buildroot userspace to Proxmox LXC. This project is not affiliated with Home Assistant, Open Home Foundation or Proxmox. It is **not** a supported HAOS installation.

## Current status

- Extract and inventory the original system filesystem from a fresh, verified raw HAOS disk image.
- Produce a deliberately restricted systemd boot-probe template locally. No Docker, Supervisor, networking, RAUC, physical-disk management or application services in this stage.
- Fixture tests, CI and a reproducible Proxmox smoke-test procedure.
- Actual HAOS image extraction and Proxmox boot are not yet validated.

The initial target is generic x86-64 HAOS 18.4. HAOS 18.5 is a Raspberry Pi-only release. Do not assume other releases are compatible. No HAOS binaries or derived templates are distributed in this repository. Never use a production image or CT, privileged LXC, host block devices, host sockets, host bind mounts or unconfined AppArmor.

## Build/test

See [German lab instructions](docs/lab-de.md) for exact commands. See [architecture](docs/architecture.md) for milestones, [test gates](docs/test-plan.md) and [third-party licensing](docs/licensing.md).

Run the fixture tests with Python 3.10+:

    python3 -m unittest discover -s tests -v
    sh -n tools/preflight.sh

These tests do not prove that the system boots. A release suitable for real home automation is not available.

Project code: Apache-2.0 (see LICENSE). Upstream: https://github.com/home-assistant/operating-system .
